import os
import re
from io import BytesIO
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import get_resolver, reverse
from PIL import Image, PngImagePlugin

from caja import comprobantes, retiros
from caja import servicios as caja
from caja.models import Caja, MotivoRetiro, RetiroCaja
from cobros import libro
from cobros.models import Pago
from configuracion.models import Parametro
from solicitudes import motor
from solicitudes.models import Solicitud

from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo
from .test_retiros import topes

HUELLAS = ("5,555.57", "5555.57", "555557", "6,333.34", "6333.34", "633334")


def rutas():
    def andar(r, ns="", pre=""):
        for p in r.url_patterns:
            if hasattr(p, "url_patterns"):
                yield from andar(p, ns + (p.namespace + ":" if p.namespace else ""), pre + str(p.pattern))
            else:
                yield ns + (p.name or "?"), pre + str(p.pattern)
    return list(andar(get_resolver()))


@pytest.fixture
def escena(personas):
    preparar_conceptos()
    topes()
    Parametro.objects.update_or_create(clave="control_denominaciones", defaults={"valor": "0"})
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    turno = caja.abrir_turno(personas["op"], Caja.objects.get_or_create(nombre="Caja 1")[0], 77777)
    p1 = libro.registrar_pago(ana, 123456, Pago.EFECTIVO, personas["op"], turno=turno)
    p2 = libro.registrar_pago(ana, 432101, Pago.EFECTIVO, personas["op"], turno=turno)
    return personas, ana, turno, MotivoRetiro.objects.get(nombre="Compra de insumos"), (p1, p2)


def barrer(c, turno, extra_pks):
    fugas, errores = [], []
    for nombre, patron in rutas():
        url = "/" + patron.replace("^", "").replace("$", "")
        if "<" in url:
            candidatos = [re.sub(r"<[^>]+>", str(pk), url) for pk in extra_pks]
        else:
            candidatos = [url]
        for u in candidatos:
            if "salir" in u or "admin" in u:
                continue
            try:
                r = c.get(u)
            except Exception as error:
                errores.append((u, repr(error)[:120]))
                continue
            if r.status_code >= 500:
                errores.append((u, r.status_code))
            cuerpo = b"".join(r.streaming_content) if getattr(r, "streaming", False) else r.content
            texto = cuerpo.decode("utf-8", "ignore")
            for h in HUELLAS:
                if h in texto:
                    fugas.append((u, h))
    return fugas, errores


def test_barrido_no_revela_lo_esperado_con_turno_abierto(escena):
    personas, ana, turno, motivo, pagos = escena
    c = cliente(personas["op"])
    fugas, errores = barrer(c, turno, [turno.pk, ana.pk, pagos[0].pk, 1, 2])
    assert fugas == []
    assert errores == []


def test_barrido_no_revela_lo_esperado_en_arqueo(escena):
    personas, ana, turno, motivo, pagos = escena
    r = caja.primer_conteo(turno, personas["op"], {"100": 1})
    assert not r.cerrado
    c = cliente(personas["op"])
    fugas, errores = barrer(c, turno, [turno.pk, ana.pk, pagos[0].pk, 1, 2])
    assert fugas == []
    assert errores == []
    for u in (reverse("caja:cerrar", args=[turno.pk]), reverse("caja:reconteo", args=[turno.pk])):
        r = c.post(u, {"d_100": "5", "nota": "", "accion": "reconteo"}, follow=True)
        t = r.content.decode()
        assert not any(h in t for h in HUELLAS)


def test_mensajes_de_error_no_revelan(escena):
    personas, ana, turno, motivo, pagos = escena
    c = cliente(personas["op"])
    r = c.post(reverse("caja:retiro_nuevo"), {"importe": "9999.00", "motivo": motivo.pk, "nota": "x"}, follow=True)
    t = r.content.decode()
    assert not any(h in t for h in HUELLAS)
    r = c.post(reverse("caja:entrega"), {"destino": personas["sup"].pk, "importe": "99999.00", "nota": ""}, follow=True)
    t = r.content.decode()
    assert not any(h in t for h in HUELLAS), t[:400]
    r = c.post(reverse("caja:deposito"), {"importe": "99999.00"}, follow=True)
    assert not any(h in r.content.decode() for h in HUELLAS)


def test_barrido_supervision_con_turno_propio(escena):
    personas, ana, turno, motivo, pagos = escena
    sup = personas["sup"]
    t2 = caja.abrir_turno(sup, Caja.objects.get_or_create(nombre="Caja 2")[0], 44444)
    libro.registrar_pago(ana, 111111, Pago.EFECTIVO, sup, turno=t2)
    libro.registrar_pago(ana, 222222, Pago.EFECTIVO, sup, turno=t2)
    c = cliente(sup)
    propias = ("3,333.33", "3333.33", "333333", "3,777.77", "3777.77", "377777")
    fugas = []
    for nombre, patron in rutas():
        url = "/" + patron.replace("^", "").replace("$", "")
        for u in ([re.sub(r"<[^>]+>", str(pk), url) for pk in (t2.pk, turno.pk, ana.pk, 1, 2, 3, 4)] if "<" in url else [url]):
            if "salir" in u or "admin" in u:
                continue
            r = c.get(u)
            assert r.status_code < 500, u
            cuerpo = b"".join(r.streaming_content) if getattr(r, "streaming", False) else r.content
            for h in propias:
                if h in cuerpo.decode("utf-8", "ignore"):
                    fugas.append((u, h))
    assert fugas == []


def test_solicitud_de_retiro_no_la_aprueba_quien_la_pide(escena):
    personas, ana, turno, motivo, pagos = escena
    topes(individual=1000)
    r = retiros.registrar_retiro(personas["op"], 50000, motivo, "x")
    assert r.solicitud is not None
    with pytest.raises(Exception):
        motor.aprobar(r.solicitud, personas["op"])
    assert RetiroCaja.objects.count() == 0
    c2 = cliente(personas["op2"])
    resp = c2.get(reverse("solicitudes:detalle", args=[r.solicitud.pk]))
    motor.aprobar(r.solicitud, personas["sup"])
    assert RetiroCaja.objects.count() == 1
    with pytest.raises(Exception):
        motor.aprobar(Solicitud.objects.get(pk=r.solicitud.pk), personas["sup2"])
    assert RetiroCaja.objects.count() == 1


def test_supervision_no_se_autoriza_su_retiro(escena):
    personas, ana, turno, motivo, pagos = escena
    sup = personas["sup"]
    t2 = caja.abrir_turno(sup, Caja.objects.get_or_create(nombre="Caja 2")[0], 0)
    libro.registrar_pago(ana, 100000, Pago.EFECTIVO, sup, turno=t2)
    topes(individual=1000)
    r = retiros.registrar_retiro(sup, 50000, motivo, "x")
    assert r.solicitud is not None and r.retiro is None
    with pytest.raises(Exception):
        motor.aprobar(r.solicitud, sup)
    assert RetiroCaja.objects.count() == 0


def test_idor_retiros_y_comprobantes(escena):
    personas, ana, turno, motivo, pagos = escena
    r = retiros.registrar_retiro(personas["op"], 10000, motivo, "x", archivo=jpeg()).retiro
    c2 = cliente(personas["op2"])
    for nombre in ("caja:retiro", "caja:retiro_descargar"):
        assert c2.get(reverse(nombre, args=[r.pk])).status_code == 403
    r2 = retiros.registrar_retiro(personas["op"], 10000, motivo, "y").retiro
    resp = c2.post(reverse("caja:retiro_comprobante", args=[r2.pk]), {"archivo": SimpleUploadedFile("a.jpg", jpeg())})
    assert resp.status_code == 403
    resp = c2.post(reverse("caja:retiro_sin_comprobante", args=[r2.pk]), {"motivo": "no"})
    assert resp.status_code == 403
    c = cliente(personas["op"])
    assert c.post(reverse("caja:retiro_revisar", args=[r.pk]), {"resultado": "revisado"}).status_code == 403
    r2.refresh_from_db(); r.refresh_from_db()
    assert r2.comprobante == RetiroCaja.PENDIENTE and r.revision == RetiroCaja.POR_REVISAR


def jpeg(extra=b""):
    s = BytesIO()
    Image.new("RGB", (30, 30), (1, 2, 3)).save(s, format="JPEG")
    return s.getvalue() + extra


def test_poliglotas_y_metadatos_se_pierden():
    marca = b"<script>alert(document.domain)</script>"
    tipo, limpio = comprobantes.preparar(jpeg(marca))
    assert marca not in limpio
    s = BytesIO()
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", marca.decode())
    info.add_itxt("XML:com.adobe.xmp", "<x>" + marca.decode() + "</x>")
    exif = Image.Exif(); exif[0x010F] = "MARCAEXIF"
    Image.new("RGB", (30, 30)).save(s, format="PNG", pnginfo=info, exif=exif, icc_profile=b"ICCMARCA" * 20)
    tipo, limpio = comprobantes.preparar(s.getvalue() + marca)
    assert marca not in limpio and b"MARCAEXIF" not in limpio and b"ICCMARCA" not in limpio
    s = BytesIO()
    Image.new("RGB", (30, 30)).save(s, format="JPEG", icc_profile=b"ICCMARCA" * 20, comment=marca)
    tipo, limpio = comprobantes.preparar(s.getvalue())
    assert marca not in limpio and b"ICCMARCA" not in limpio


@pytest.mark.parametrize("contenido", [
    b"%PDF-1.4\n<html><script>alert(1)</script></html>",
    b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
    b"\x89PNG\r\n\x1a\n<html>",
    b"\xff\xd8\xff<html><script>",
    b"GIF89a<script>",
    b"MZ\x90\x00",
])
def test_contenidos_falsos_se_rechazan(contenido):
    with pytest.raises(comprobantes.ComprobanteInvalido):
        comprobantes.preparar(contenido)


def test_pdf_con_nombres_escapados_se_rechaza():
    from .test_retiros import pdf_crudo
    for extra in ("/Open#41ction << /S /#4AavaScript /#4AS (app.alert(1)) >>", "/#41#41 << /O << /S /JavaScript /JS (1) >> >>"):
        with pytest.raises(comprobantes.ComprobanteInvalido):
            comprobantes.preparar(pdf_crudo(extra_catalogo=extra))


def test_imagen_enorme_se_rechaza_rapido():
    import time
    s = BytesIO()
    Image.new("1", (30000, 30000)).save(s, format="PNG")
    inicio = time.time()
    with pytest.raises(comprobantes.ComprobanteInvalido):
        comprobantes.preparar(s.getvalue())
    assert time.time() - inicio < 5


def test_verificar_recibo_entradas_raras(escena):
    personas, ana, turno, motivo, pagos = escena
    c = cliente(personas["op"])
    url = reverse("cobros:verificar")
    for entrada in ("AR1|A|99999999999999999999999|X", "AR1|||", "AR1|١|٢|AAAAA-AAAAA", "AR1|" + "A" * 5000, "AR1|R|1|" + "\x00", "|" * 50):
        r = c.get(url, {"codigo": entrada, "folio": "A-1"})
        assert r.status_code < 500, entrada
        r = c.post(url, {"codigo": entrada, "folio": "A-1"})
        assert r.status_code < 500, entrada


def test_carpeta_no_escribe_fuera_por_una_subcarpeta_enlazada(escena, tmp_path):
    from auditoria.models import Evento
    from banco import carpeta
    from configuracion.models import Negocio

    base = tmp_path / "banco"
    base.mkdir()
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (base / "procesados").mkdir()
    os.symlink(fuera, base / "rechazados")
    Negocio.objects.filter(pk=1).update(carpeta_banco=str(base))
    (base / "malo.exe").write_bytes(b"MZ")
    informe = carpeta.revisar()
    assert informe.get("bloqueada")
    assert list(fuera.iterdir()) == []
    assert (base / "malo.exe").exists()
    assert Evento.objects.filter(accion="carpeta_banco_bloqueada").count() == 1
    carpeta.revisar()
    assert Evento.objects.filter(accion="carpeta_banco_bloqueada").count() == 1
    os.unlink(base / "rechazados")
    informe = carpeta.revisar()
    assert not informe.get("bloqueada") and informe["rechazados"] == 1
    assert list(fuera.iterdir()) == []


def test_carpeta_no_puede_ser_la_de_entrega_de_cortes_ni_la_de_respaldo(escena, tmp_path):
    from banco import carpeta
    from configuracion.models import Negocio
    from cortes.models import Destino

    entrega = tmp_path / "audit"
    entrega.mkdir()
    Destino.objects.create(nombre="Luna", ruta=str(entrega))
    respaldo = tmp_path / "respaldo"
    respaldo.mkdir()
    Negocio.objects.filter(pk=1).update(carpeta_respaldo=str(respaldo))
    for ruta in (entrega, entrega / "banco", tmp_path, respaldo, respaldo / "x"):
        with pytest.raises(carpeta.ErrorCarpeta):
            carpeta.validar_carpeta(str(ruta))
    libre = tmp_path / "banco"
    assert carpeta.validar_carpeta(str(libre)) == str(libre)


def test_los_topes_tambien_cuentan_por_persona_al_cambiar_de_caja(escena):
    personas, ana, turno, motivo, pagos = escena
    topes(individual=100000, periodo=30000, cantidad=5)
    primero = retiros.registrar_retiro(personas["op"], 30000, motivo, "a").retiro
    retiros.sin_comprobante(primero, personas["op"], "sin ticket")
    caja.cerrar_turno(turno, personas["op"], {"100": 1}, "cierre")
    otro = caja.abrir_turno(personas["op"], Caja.objects.get_or_create(nombre="Caja 2")[0], 0)
    libro.registrar_pago(ana, 50000, Pago.EFECTIVO, personas["op"], turno=otro)
    resultado = retiros.registrar_retiro(personas["op"], 1000, motivo, "b")
    assert resultado.retiro is None and resultado.solicitud is not None
    assert "importe_periodo" in resultado.motivos


def test_cerrar_sin_nota_no_sirve_de_sonda_del_esperado(escena):
    personas, ana, turno, motivo, pagos = escena
    arqueo = caja.cerrar_turno(turno, personas["op"], {"100": 1}, "")
    assert arqueo.supera_umbral and arqueo.contado == 100
    with pytest.raises(caja.ErrorCaja):
        caja.cerrar_turno(turno, personas["op"], {"100": 2}, "")


def test_hora_del_calendario_no_admite_salto_de_linea():
    from cortes import calendario

    with pytest.raises(calendario.CalendarioInvalido):
        calendario.validar({"0": "18:00\n"})


def test_comprobante_que_no_se_registra_no_deja_archivo(escena, settings):
    personas, ana, turno, motivo, pagos = escena
    retiro = retiros.registrar_retiro(personas["op"], 10000, motivo, "x", archivo=jpeg()).retiro
    carpeta_comprobantes = Path(settings.RUTA_COMPROBANTES)
    antes = sorted(p.name for p in carpeta_comprobantes.iterdir())
    with pytest.raises(caja.ErrorCaja):
        retiros.adjuntar_preparado(retiro, personas["op"], comprobantes.preparar(jpeg()))
    assert sorted(p.name for p in carpeta_comprobantes.iterdir()) == antes
