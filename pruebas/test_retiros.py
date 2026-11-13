import hashlib
import os
import re
from io import BytesIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from PIL import Image
from pypdf import PdfWriter
from pypdf.actions import JavaScript
from reportlab.pdfgen import canvas

from auditoria.models import Evento
from caja import comprobantes, retiros
from caja import servicios as caja
from caja.models import ComprobanteRetiro, MotivoRetiro, MovimientoPiezas, RegistroInmutable, RetiroCaja, ReversionRetiro, Turno
from cobros import libro
from cobros.models import Pago
from configuracion.models import Parametro, hoy_negocio
from cortes import calculo
from cortes.models import DIARIO, Corte
from solicitudes import motor
from solicitudes.models import Solicitud

from .conftest import cliente, codigo_actual
from .libro_ayudas import preparar_conceptos, titular_activo, turno_de


def topes(individual=100000, periodo=300000, cantidad=5, tipo="dia"):
    for clave, valor in (("tope_retiro_individual", individual), ("tope_retiros_periodo", periodo), ("maximo_retiros_periodo", cantidad), ("periodo_retiros", tipo)):
        Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})


@pytest.fixture
def base(personas):
    preparar_conceptos()
    topes()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 200000, Pago.EFECTIVO, personas["op"], turno=turno)
    return personas, ana, turno, MotivoRetiro.objects.get(nombre="Compra de insumos")


def jpeg_con_ubicacion():
    imagen = Image.new("RGB", (40, 30), (200, 10, 10))
    exif = Image.Exif()
    exif[0x010F] = "Fabricante ficticio"
    exif[0x8825] = {1: "N", 2: (19.0, 26.0, 0.0), 3: "W", 4: (99.0, 8.0, 0.0)}
    salida = BytesIO()
    imagen.save(salida, format="JPEG", exif=exif)
    return salida.getvalue()


def png():
    salida = BytesIO()
    Image.new("RGBA", (20, 20), (0, 0, 255, 128)).save(salida, format="PNG")
    return salida.getvalue()


def pdf_sano():
    salida = BytesIO()
    hoja = canvas.Canvas(salida)
    hoja.drawString(72, 720, "Ticket de compra ficticio")
    hoja.showPage()
    hoja.save()
    return salida.getvalue()


def pdf_crudo(extra_catalogo="", extra_pagina="", objetos=()):
    cuerpos = [
        f"<< /Type /Catalog /Pages 2 0 R {extra_catalogo} >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] {extra_pagina} >>",
        *objetos,
    ]
    salida = b"%PDF-1.4\n"
    posiciones = []
    for numero, cuerpo in enumerate(cuerpos, start=1):
        posiciones.append(len(salida))
        salida += f"{numero} 0 obj\n{cuerpo}\nendobj\n".encode("latin-1")
    inicio = len(salida)
    salida += f"xref\n0 {len(cuerpos) + 1}\n0000000000 65535 f \n".encode("latin-1")
    for posicion in posiciones:
        salida += f"{posicion:010d} 00000 n \n".encode("latin-1")
    salida += f"trailer\n<< /Size {len(cuerpos) + 1} /Root 1 0 R >>\nstartxref\n{inicio}\n%%EOF\n".encode("latin-1")
    return salida


def pdf_con_js_comprimido():
    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    escritor.add_open_action(JavaScript("app.alert('hola');"))
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def pdf_con_adjunto():
    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    escritor.add_attachment("nota.txt", b"contenido")
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def pdf_cifrado():
    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    escritor.encrypt("clave")
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def test_dentro_de_los_topes_se_registra_y_sale_del_esperado(base):
    personas, ana, turno, motivo = base
    resultado = retiros.registrar_retiro(personas["op"], 30000, motivo, "Papelería")
    retiro = resultado.retiro
    assert retiro is not None and resultado.solicitud is None and str(retiro) == "R-1"
    assert caja.esperado_de(turno) == 170000 and caja.custodia(personas["op"]) == 170000
    assert retiro.revision == RetiroCaja.POR_REVISAR and retiro.comprobante == RetiroCaja.PENDIENTE
    assert retiros.registrar_retiro(personas["op"], 1000, motivo).retiro.folio == 2
    assert Evento.objects.filter(accion="retiro_registrado").count() == 2
    retiro.importe = 1
    with pytest.raises(RegistroInmutable):
        retiro.save()
    with pytest.raises(RegistroInmutable):
        RetiroCaja.objects.filter(pk=retiro.pk).update(importe=1)
    with pytest.raises(Exception):
        RetiroCaja.objects.filter(pk=retiro.pk).delete()


@pytest.mark.parametrize(
    "importe, previos, motivo_esperado",
    [(100001, [], "importe_individual"), (60000, [100000, 100000, 50000], "importe_periodo"), (100, [100] * 5, "cantidad_periodo")],
    ids=["individual", "periodo", "cantidad"],
)
def test_fuera_de_topes_se_vuelve_solicitud(base, importe, previos, motivo_esperado):
    personas, ana, turno, motivo = base
    libro.registrar_pago(ana, 400000, Pago.EFECTIVO, personas["op"], turno=turno)
    for previo in previos:
        assert retiros.registrar_retiro(personas["op"], previo, motivo).retiro is not None
    resultado = retiros.registrar_retiro(personas["op"], importe, motivo, "Grande")
    assert resultado.retiro is None and resultado.solicitud is not None and motivo_esperado in resultado.motivos
    solicitud = resultado.solicitud
    assert solicitud.accion == "retiro_caja" and solicitud.titular is None and solicitud.solicitante == personas["op"]
    with pytest.raises(motor.ErrorSolicitud):
        motor.aprobar(solicitud, personas["op"])
    motor.aprobar(solicitud, personas["sup"])
    retiro = RetiroCaja.objects.get(solicitud=solicitud)
    assert retiro.autorizado_por == personas["sup"] and retiro.registrado_por == personas["op"] and retiro.turno == turno


def test_supervision_tampoco_rebasa_topes_sin_otra_persona(base):
    personas, ana, turno, motivo = base
    turno_sup = turno_de(personas["sup"], "Caja 2")
    libro.registrar_pago(ana, 500000, Pago.EFECTIVO, personas["sup"], turno=turno_sup)
    resultado = retiros.registrar_retiro(personas["sup"], 200000, motivo)
    assert resultado.solicitud is not None and resultado.retiro is None
    with pytest.raises(motor.ErrorSolicitud):
        motor.aprobar(resultado.solicitud, personas["sup"])
    with pytest.raises(motor.ErrorSolicitud):
        motor.autorizar_con_codigo(resultado.solicitud, personas["sup"], personas["sup"], codigo_actual(personas["sup"]))
    motor.autorizar_con_codigo(resultado.solicitud, personas["sup"], personas["dir"], codigo_actual(personas["dir"]))
    assert RetiroCaja.objects.get().autorizado_por == personas["dir"]


def test_topes_por_caja_y_periodo_semanal(base):
    personas, ana, turno, motivo = base
    topes(periodo=150000, tipo="semana")
    primero = retiros.registrar_retiro(personas["op"], 100000, motivo).retiro
    retiros.sin_comprobante(primero, personas["op"], "sin ticket")
    caja.cerrar_turno(turno, personas["op"], {"100000": 1}, "conteo")
    nuevo = turno_de(personas["op"])
    libro.registrar_pago(ana, 200000, Pago.EFECTIVO, personas["op"], turno=nuevo)
    assert retiros.registrar_retiro(personas["op"], 60000, motivo).solicitud is not None
    otro = turno_de(personas["op2"], "Caja 2")
    libro.registrar_pago(ana, 200000, Pago.EFECTIVO, personas["op2"], turno=otro)
    assert retiros.registrar_retiro(personas["op2"], 60000, motivo).retiro is not None


def test_sin_efectivo_suficiente_rechaza_sin_decir_cuanto_y_al_tercero_pide_autorizacion(base):
    personas, ana, turno, motivo = base
    op = cliente(personas["op"])
    datos = {"importe": "2000.01", "motivo": motivo.pk, "nota": ""}
    topes(individual=1000000, periodo=10000000, cantidad=100)
    for intento in range(3):
        respuesta = op.post(reverse("caja:retiro_nuevo"), datos)
        texto = respuesta.content.decode()
        assert respuesta.status_code == 200 and "no tiene ese efectivo" in texto
        assert "2,000.00" not in texto and "200000" not in texto
    assert not RetiroCaja.objects.exists()
    assert Evento.objects.filter(accion="retiro_rechazado").count() == 3
    turno.refresh_from_db()
    assert turno.rechazos_retiro == 3
    respuesta = op.post(reverse("caja:retiro_nuevo"), {"importe": "10", "motivo": motivo.pk})
    solicitud = Solicitud.objects.get(accion="retiro_caja")
    assert respuesta.url == reverse("solicitudes:detalle", args=[solicitud.pk]) and "rechazos" in solicitud.datos["excede"]
    grande = Solicitud.objects.create(accion="retiro_caja", titular=None, solicitante=personas["op"], caduca_en=solicitud.caduca_en, datos={**solicitud.datos, "importe": 300000, "ficha": "otra-ficha"})
    with pytest.raises(motor.ErrorSolicitud, match="no tiene efectivo suficiente"):
        motor.aprobar(grande, personas["sup"])
    assert not RetiroCaja.objects.exists()


def test_retiro_no_sale_del_fondo(base):
    personas, ana, turno, motivo = base
    caja.cerrar_turno(turno, personas["op"], {"100000": 2}, "")
    caja.abrir_turno(personas["op"], turno.caja, 50000)
    assert retiros.registrar_retiro(personas["op"], 100, motivo).rechazado


def test_topes_simultaneos_no_se_rebasan(transactional_db):
    import threading

    from django.db import connection

    from .conftest import configurar, nuevo_usuario

    roles = configurar("escuela")
    preparar_conceptos()
    topes(individual=100000, periodo=30000, cantidad=100)
    sup = nuevo_usuario("supervision", roles["Supervisión"])
    op = nuevo_usuario("operacion", roles["Operación"])
    ana = titular_activo(op, sup, "Ana")
    turno = turno_de(op)
    libro.registrar_pago(ana, 500000, Pago.EFECTIVO, op, turno=turno)
    motivo = MotivoRetiro.objects.first()
    barrera = threading.Barrier(6)
    errores = []

    def retirar():
        try:
            barrera.wait()
            retiros.registrar_retiro(op, 10000, motivo.pk)
        except Exception as error:
            errores.append(error)
        finally:
            connection.close()

    hilos = [threading.Thread(target=retirar) for _ in range(6)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert not errores, errores
    assert RetiroCaja.objects.count() == 3 and Solicitud.objects.filter(accion="retiro_caja").count() == 3
    assert sum(RetiroCaja.objects.values_list("importe", flat=True)) == 30000
    assert sorted(RetiroCaja.objects.values_list("folio", flat=True)) == [1, 2, 3]


def test_comprobante_jpeg_se_recodifica_sin_ubicacion_y_se_guarda_fuera(base):
    personas, ana, turno, motivo = base
    original = jpeg_con_ubicacion()
    assert Image.open(BytesIO(original)).getexif().get(0x8825)
    retiro = retiros.registrar_retiro(personas["op"], 5000, motivo, archivo=original).retiro
    retiro.refresh_from_db()
    archivo = retiro.archivo_comprobante
    assert retiro.comprobante == RetiroCaja.ADJUNTO and archivo.tipo == "jpeg"
    assert re.fullmatch(r"[0-9a-f]{32}\.jpg", archivo.archivo)
    ruta = Path(settings.RUTA_COMPROBANTES) / archivo.archivo
    guardado = ruta.read_bytes()
    assert guardado != original and hashlib.sha256(guardado).hexdigest() == archivo.sha256
    assert not Image.open(BytesIO(guardado)).getexif() and b"Fabricante ficticio" not in guardado
    assert not str(ruta.resolve()).startswith(str((Path(settings.RAIZ) / "sistema" / "estaticos").resolve()))
    evento = Evento.objects.get(accion="comprobante_adjuntado")
    assert evento.datos["sha256"] == archivo.sha256
    if os.name != "nt":
        assert oct(ruta.stat().st_mode & 0o777) == "0o600"


@pytest.mark.parametrize("contenido, tipo", [(png(), "png"), (pdf_sano(), "pdf")], ids=["png", "pdf"])
def test_comprobantes_validos(base, contenido, tipo):
    personas, ana, turno, motivo = base
    retiro = retiros.registrar_retiro(personas["op"], 5000, motivo).retiro
    retiros.adjuntar(retiro, personas["op"], contenido)
    assert ComprobanteRetiro.objects.get().tipo == tipo


MALICIOSOS = {
    "html": b"<html><script>alert(1)</script></html>",
    "svg": b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
    "ejecutable": b"MZ\x90\x00" + b"\x00" * 100,
    "jpeg_falso": b"\xff\xd8\xff\xe0" + b"no es una imagen" * 10,
    "png_falso": b"\x89PNG\r\n\x1a\n" + b"basura" * 10,
    "pdf_dañado": b"%PDF-1.7\n basura sin estructura",
    "pdf_javascript": pdf_crudo("/OpenAction 4 0 R", "", ["<< /S /JavaScript /JS (app.alert(1)) >>"]),
    "pdf_javascript_escapado": pdf_crudo("/Names << /J#61vaScript 4 0 R >>", "", ["<< /Names [(x) 5 0 R] >>", "<< /S /J#61vaScript /J#53 (app.alert(1)) >>"]),
    "pdf_lanzar": pdf_crudo("", "/Annots [4 0 R]", ["<< /Type /Annot /Subtype /Link /Rect [0 0 10 10] /A << /S /Launch /F (cmd.exe) >> >>"]),
    "pdf_comprimido_js": pdf_con_js_comprimido(),
    "pdf_adjunto": pdf_con_adjunto(),
    "pdf_cifrado": pdf_cifrado(),
    "vacio": b"",
}


@pytest.mark.parametrize("nombre", sorted(MALICIOSOS))
def test_comprobantes_maliciosos_se_rechazan(base, nombre):
    personas, ana, turno, motivo = base
    retiro = retiros.registrar_retiro(personas["op"], 5000, motivo).retiro
    with pytest.raises(comprobantes.ComprobanteInvalido):
        retiros.adjuntar(retiro, personas["op"], MALICIOSOS[nombre])
    retiro.refresh_from_db()
    assert retiro.comprobante == RetiroCaja.PENDIENTE and not ComprobanteRetiro.objects.exists()
    assert not any(Path(settings.RUTA_COMPROBANTES).glob("*")) if Path(settings.RUTA_COMPROBANTES).exists() else True


@pytest.mark.parametrize("nombre", ["pdf_javascript", "pdf_javascript_escapado", "pdf_lanzar", "pdf_comprimido_js", "pdf_adjunto"])
def test_el_recorrido_de_objetos_detecta_contenido_activo_sin_la_revision_cruda(monkeypatch, nombre):
    import re as modulo_re

    monkeypatch.setattr(comprobantes, "CRUDO_ACTIVO", modulo_re.compile(rb"(?!x)x"))
    with pytest.raises(comprobantes.ComprobanteInvalido, match="activo"):
        comprobantes.preparar(MALICIOSOS[nombre])
    assert comprobantes.preparar(pdf_sano())[0] == "pdf"


def test_imagen_gigante_y_archivo_grande_se_rechazan(base):
    personas, ana, turno, motivo = base
    salida = BytesIO()
    Image.new("1", (7000, 7000)).save(salida, format="PNG")
    with pytest.raises(comprobantes.ComprobanteInvalido, match="demasiado grande"):
        comprobantes.preparar(salida.getvalue())
    with pytest.raises(comprobantes.ComprobanteInvalido, match="5 MB"):
        comprobantes.preparar(b"%PDF-1.4\n" + b"0" * (5 * 1024 * 1024))


def test_tipo_por_contenido_no_por_nombre(base):
    personas, ana, turno, motivo = base
    op = cliente(personas["op"])
    retiro = retiros.registrar_retiro(personas["op"], 5000, motivo).retiro
    disfrazado = SimpleUploadedFile("ticket.jpg", MALICIOSOS["html"], content_type="image/jpeg")
    op.post(reverse("caja:retiro_comprobante", args=[retiro.pk]), {"archivo": disfrazado})
    assert not ComprobanteRetiro.objects.exists() and Evento.objects.filter(accion="comprobante_rechazado").exists()
    pdf_como_png = SimpleUploadedFile("ticket.png", pdf_sano(), content_type="image/png")
    op.post(reverse("caja:retiro_comprobante", args=[retiro.pk]), {"archivo": pdf_como_png})
    assert ComprobanteRetiro.objects.get().tipo == "pdf" and ComprobanteRetiro.objects.get().archivo.endswith(".pdf")


def test_descarga_con_cabeceras_y_permisos(base):
    personas, ana, turno, motivo = base
    retiro = retiros.registrar_retiro(personas["op"], 5000, motivo, archivo=pdf_sano()).retiro
    url = reverse("caja:retiro_descargar", args=[retiro.pk])
    respuesta = cliente(personas["op"]).get(url)
    assert respuesta.status_code == 200 and respuesta["Content-Type"] == "application/pdf"
    assert respuesta["Content-Disposition"].startswith("attachment;") and respuesta["X-Content-Type-Options"] == "nosniff" and respuesta["Content-Security-Policy"] == "sandbox"
    assert cliente(personas["sup"]).get(url).status_code == 200
    assert cliente(personas["dir"]).get(url).status_code == 200
    assert cliente(personas["op2"]).get(url).status_code == 403
    assert cliente(personas["op2"]).get(reverse("caja:retiro", args=[retiro.pk])).status_code == 403
    assert reverse("caja:retiro", args=[retiro.pk]) not in cliente(personas["op2"]).get(reverse("caja:retiros")).content.decode()
    assert cliente().get(url).status_code == 302
    ruta = Path(settings.RUTA_COMPROBANTES) / retiro.archivo_comprobante.archivo
    ruta.write_bytes(b"%PDF-1.4 alterado")
    alterado = cliente(personas["sup"]).get(url)
    assert alterado.status_code == 302 and Evento.objects.filter(accion="comprobante_alterado").exists()


def test_turno_no_cierra_con_comprobantes_pendientes(base):
    personas, ana, turno, motivo = base
    retiro = retiros.registrar_retiro(personas["op"], 5000, motivo).retiro
    op = cliente(personas["op"])
    pagina = op.get(reverse("caja:cerrar", args=[turno.pk])).content.decode()
    assert "comprobante pendiente" in pagina and 'name="d_100000"' not in pagina
    op.post(reverse("caja:cerrar", args=[turno.pk]), {"d_100000": 1})
    with pytest.raises(caja.ErrorCaja):
        caja.primer_conteo(turno, personas["op"], {"100000": 1})
    assert Turno.objects.get(pk=turno.pk).abierto
    with pytest.raises(caja.ErrorCaja):
        retiros.sin_comprobante(retiro, personas["op"], "")
    with pytest.raises(caja.ErrorCaja):
        retiros.sin_comprobante(retiro, personas["op2"], "no hubo")
    op.post(reverse("caja:retiro_sin_comprobante", args=[retiro.pk]), {"motivo": "El proveedor no dio ticket"})
    retiro.refresh_from_db()
    assert retiro.comprobante == RetiroCaja.SIN_COMPROBANTE
    assert "declarado sin comprobante" in cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    resultado = caja.primer_conteo(turno, personas["op"], {"100000": 1, "50000": 1, "20000": 2, "5000": 1})
    assert resultado.cerrado


def test_revision_por_otra_persona(base):
    personas, ana, turno, motivo = base
    retiro = retiros.registrar_retiro(personas["op"], 5000, motivo).retiro
    assert cliente(personas["op"]).post(reverse("caja:retiro_revisar", args=[retiro.pk]), {"resultado": "revisado"}).status_code == 403
    turno_sup = turno_de(personas["sup"], "Caja 2")
    libro.registrar_pago(ana, 50000, Pago.EFECTIVO, personas["sup"], turno=turno_sup)
    propio = retiros.registrar_retiro(personas["sup"], 1000, motivo).retiro
    assert cliente(personas["sup"]).post(reverse("caja:retiro_revisar", args=[propio.pk]), {"resultado": "revisado"}).status_code == 403
    with pytest.raises(retiros.RevisionPropia):
        retiros.revisar(propio, personas["sup"], RetiroCaja.REVISADO)
    with pytest.raises(IntegrityError), transaction.atomic():
        RetiroCaja.objects.filter(pk=propio.pk).update(revision=RetiroCaja.REVISADO, revisado_por=personas["sup"])
    with pytest.raises(caja.ErrorCaja):
        retiros.revisar(retiro, personas["sup"], RetiroCaja.OBSERVADO, "")
    cliente(personas["sup"]).post(reverse("caja:retiro_revisar", args=[retiro.pk]), {"resultado": "observado", "nota": "Falta factura"})
    retiro.refresh_from_db()
    assert (retiro.revision, retiro.revisado_por, retiro.nota_revision) == (RetiroCaja.OBSERVADO, personas["sup"], "Falta factura")
    with pytest.raises(caja.ErrorCaja):
        retiros.revisar(retiro, personas["dir"], RetiroCaja.REVISADO)


def test_reversion_solo_por_solicitud_y_regresa_al_turno_de_quien_la_pide(base):
    personas, ana, turno, motivo = base
    retiro = retiros.registrar_retiro(personas["op"], 30000, motivo).retiro
    op = cliente(personas["op"])
    respuesta = op.post(reverse("caja:retiro_revertir", args=[retiro.pk]), {"motivo": "Se devolvió la compra"})
    solicitud = Solicitud.objects.get(accion="revertir_retiro")
    assert respuesta.url == reverse("solicitudes:detalle", args=[solicitud.pk]) and not ReversionRetiro.objects.exists()
    turno_op2 = turno_de(personas["op2"], "Caja 2")
    with pytest.raises(motor.ErrorSolicitud):
        motor.ejecutar("revertir_retiro", personas["dir"], None, {"retiro": retiro.pk, "motivo": "otra"})
    motor.aprobar(solicitud, personas["sup"])
    reversion = ReversionRetiro.objects.get()
    assert reversion.turno == turno and reversion.autorizada_por == personas["sup"]
    assert caja.esperado_de(turno) == 200000 and caja.custodia(personas["op"]) == 200000
    segunda = retiros.registrar_retiro(personas["op"], 1000, motivo).retiro
    motor.ejecutar("revertir_retiro", personas["op2"], None, {"retiro": segunda.pk, "motivo": "error"})
    pendiente = Solicitud.objects.get(accion="revertir_retiro", estado="pendiente")
    with pytest.raises(motor.ErrorSolicitud, match="él mismo"):
        motor.aprobar(pendiente, personas["op"])
    motor.aprobar(pendiente, personas["sup"])
    assert ReversionRetiro.objects.get(retiro=segunda).turno == turno_op2
    assert caja.esperado_de(turno_op2) == 1000


def test_retiros_en_corte_diario_y_mayor(base):
    personas, ana, turno, motivo = base
    retiros.registrar_retiro(personas["op"], 30000, motivo, "Papelería", archivo=png())
    caja.cerrar_turno(turno, personas["op"], {"100000": 1, "50000": 1, "20000": 1}, "")
    corte = Corte.objects.get(tipo=DIARIO)
    filas = {s["clave"]: s["filas"] for s in corte.cifras["secciones"]}
    assert filas["retiros"][0]["folio"] == "R-1" and filas["retiros"][0]["importe"] == 30000 and corte.cifras["totales"]["total_retirado"] == 30000
    assert corte.cifras["totales"]["esperado"] == 170000 and corte.cifras["totales"]["diferencia"] == 0
    hoy = hoy_negocio()
    mayor = calculo.cifras_mayor(hoy.replace(day=1), hoy)
    assert next(s for s in mayor["secciones"] if s["clave"] == "retiros")["filas"][0]["motivo"] == "Compra de insumos"
    assert mayor["totales"]["efectivo_cuadra"] and mayor["totales"]["efectivo_retirado_neto"] == 30000


def test_mayor_no_cuenta_turnos_abiertos(base):
    personas, ana, turno, motivo = base
    hoy = hoy_negocio()
    totales = calculo.cifras_mayor(hoy.replace(day=1), hoy)["totales"]
    assert totales["efectivo_en_custodia"] == 0 and totales["efectivo_cobrado_neto"] == 0 and totales["efectivo_cuadra"]


def test_piezas_del_retiro_cuando_hay_control(base):
    personas, ana, turno, motivo = base
    Parametro.objects.update_or_create(clave="control_denominaciones", defaults={"valor": "1"})
    with pytest.raises(caja.ErrorCaja, match="exactamente"):
        retiros.registrar_retiro(personas["op"], 30000, motivo, piezas={"20000": 1})
    retiro = retiros.registrar_retiro(personas["op"], 30000, motivo, piezas={"20000": 1, "10000": 1}).retiro
    assert {(m.denominacion, m.piezas) for m in MovimientoPiezas.objects.filter(retiro=retiro)} == {(20000, -1), (10000, -1)}


def test_avisos_de_tope_y_sin_revisar(base):
    personas, ana, turno, motivo = base
    topes(periodo=100000, cantidad=10)
    retiros.registrar_retiro(personas["op"], 80000, motivo)
    texto = cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    assert "ya usó" in texto and "800.00" in texto
    assert "ya usó" not in cliente(personas["op"]).get(reverse("inicio")).content.decode()


def test_comprobantes_viajan_en_el_respaldo(base, tmp_path):
    from respaldos import servicios as respaldos

    personas, ana, turno, motivo = base
    retiro = retiros.registrar_retiro(personas["op"], 5000, motivo, archivo=png()).retiro
    from configuracion.models import Negocio

    Negocio.objects.filter(pk=1).update(carpeta_respaldo=str(tmp_path / "respaldos"))
    registro = respaldos.respaldar()
    assert registro.resultado == registro.CORRECTO, registro.mensaje
    destino = tmp_path / "abierto"
    destino.mkdir()
    extraidos = respaldos.abrir(Path(tmp_path / "respaldos" / registro.archivo), respaldos.clave_respaldo(), str(destino))
    revision = respaldos.verificar_paquete(extraidos)
    nombre = retiro.archivo_comprobante.archivo
    assert revision["manifiesto"]["comprobantes"] == {nombre: retiro.archivo_comprobante.sha256}
    assert (destino / "comprobantes" / nombre).read_bytes() == (Path(settings.RUTA_COMPROBANTES) / nombre).read_bytes()
    (destino / "comprobantes" / nombre).write_bytes(b"alterado")
    with pytest.raises(respaldos.ErrorRespaldo):
        respaldos.verificar_paquete(extraidos)
