import csv
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook, load_workbook
from pypdf import PdfReader

from auditoria.models import Evento
from cobros.models import Cargo, ConceptoCobro, Pago
from solicitudes import motor
from solicitudes.models import Solicitud
from titulares.models import Familia, LotePadron, Titular

from .banco_ayudas import cuenta_principal
from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo, verificar_sumas

ENCABEZADO = ["Alumno", "Grupo", "Tutor", "Celular", "Correo", "Colegiatura", "Libros"]
FILAS = [
    ["Luis Pérez Gómez", "1A", "Marta Gómez", "55 1111 2222", "marta@example.com", "2500", ""],
    ["Sara Pérez Gómez", "2B", "Marta Gómez", "5511112222", "", "", "-300.50"],
    ["Juan", "1A", "", "5533334444", "", "", ""],
    ["Luis Pérez Gómez", "1A", "Marta Gómez", "5511112222", "", "", ""],
    ["Ana Prueba", "3C", "Otra Persona", "5599990000", "", "", ""],
    ["=cmd|' /C calc'!A0 Ruiz", "1A", "Rosa Ruiz", "5577778888", "correo-malo", "abc", ""],
    ["Pedro Ruiz Soto", "1B", "Rosa Ruiz", "5577778888", "", "100", ""],
    ["<b>Eva</b> Ruiz Soto", "2A", "Rosa Ruiz", "5577778888", "", "", ""],
]


def xlsx(filas):
    libro_xlsx = Workbook()
    hoja = libro_xlsx.active
    hoja.append(["Padrón del ciclo"])
    hoja.append(ENCABEZADO)
    for fila in filas:
        hoja.append(fila)
    memoria = io.BytesIO()
    libro_xlsx.save(memoria)
    return memoria.getvalue()


@pytest.fixture
def base(personas):
    preparar_conceptos()
    cuenta_principal()
    existente = titular_activo(personas["op"], personas["sup"], "Ana")
    return personas, existente


def revisar(c, contenido, nombre="padron.xlsx", columnas=None):
    r = c.post(reverse("configuracion:padron_subir"), {"archivo": SimpleUploadedFile(nombre, contenido)})
    assert r.status_code == 302, r.content.decode()[-1500:]
    pagina = c.get(r.url)
    return r.url, pagina


def test_importacion_completa_con_familias_saldos_y_duplicados(base):
    personas, existente = base
    c = cliente(personas["dir"])
    url, pagina = revisar(c, xlsx(FILAS))
    formulario = pagina.context["formulario"]
    colegiatura = ConceptoCobro.objects.get(nombre="Colegiatura")
    libros = ConceptoCobro.objects.get(nombre="Libros")
    assert formulario["nombre_completo"].initial == "0" and formulario["responsable"].initial == "2" and formulario["telefono"].initial == "3"
    assert formulario[f"saldo_{colegiatura.pk}"].initial == "5" and formulario[f"saldo_{libros.pk}"].initial == "6"
    datos = {"paso": "revisar", "nombre_completo": "0", "agrupacion": "1", "responsable": "2", "telefono": "3", "correo": "4", f"saldo_{colegiatura.pk}": "5", f"saldo_{libros.pk}": "6"}
    previa = c.post(url, datos)
    analisis = previa.context["analisis"]
    situacion = [("E" if f["errores"] else "D" if f["duplicado"] else "A") for f in analisis["filas"]]
    assert situacion == ["A", "A", "E", "D", "D", "E", "A", "A"]
    assert Titular.objects.count() == 1 and not LotePadron.objects.exists()
    html = previa.content.decode()
    assert "<b>Eva</b>" not in html and "&lt;b&gt;Eva" in html
    marta = next(i for i, f in enumerate(analisis["familias"]) if f["responsable"] == "Marta Gómez")
    rosa = next(i for i, f in enumerate(analisis["familias"]) if f["responsable"] == "Rosa Ruiz")
    respuesta = c.post(url, {"paso": "confirmar", "familia": [str(marta)]})
    assert respuesta.status_code == 302
    lote = LotePadron.objects.get()
    assert (lote.creados, lote.familias, lote.duplicados, lote.con_error, lote.cargos, lote.a_favor) == (4, 1, 2, 2, 2, 1)
    luis = Titular.objects.get(nombre="Luis", apellidos="Pérez Gómez")
    sara = Titular.objects.get(nombre="Sara")
    pedro = Titular.objects.get(nombre="Pedro")
    assert luis.estado == Titular.ACTIVO and luis.familia == sara.familia and luis.familia is not None
    assert pedro.familia is None and Familia.objects.filter(nombre="Rosa Ruiz").count() == 0 and rosa is not None
    assert Cargo.objects.get(titular=luis, origen=Cargo.SALDO_INICIAL).importe_final == 250000
    assert Cargo.objects.get(titular=pedro, origen=Cargo.SALDO_INICIAL).importe_final == 10000
    a_favor = Pago.objects.get(titular=sara, medio=Pago.SALDO_INICIAL)
    assert a_favor.importe == 30050 and a_favor.recibo.serie == "S" and a_favor.turno_id is None
    assert Evento.objects.filter(accion="alta_importada").count() == 4 and Evento.objects.filter(accion="padron_importado").exists()
    assert c.post(url, {"paso": "confirmar"}).status_code == 404
    verificar_sumas()

    salida = c.get(reverse("configuracion:padron_matriculas", args=[lote.pk, "csv"])).content.decode("utf-8-sig")
    renglones = list(csv.reader(io.StringIO(salida)))
    assert renglones[0][0] == "Matrícula" and len(renglones) == 5
    assert all(r[0].isdigit() for r in renglones[1:])
    assert any(r[2] == "Ruiz Soto" and r[1].startswith("&lt;") is False for r in renglones[1:])
    hoja = load_workbook(io.BytesIO(c.get(reverse("configuracion:padron_matriculas", args=[lote.pk, "xlsx"])).content)).active
    assert [c.value for c in hoja[1]][0] == "Matrícula" and hoja.max_row == 5
    fichas = c.get(reverse("configuracion:padron_fichas", args=[lote.pk])).content
    lector = PdfReader(io.BytesIO(fichas))
    assert len(lector.pages) == 4 and luis.matricula_formateada in lector.pages[0].extract_text()


def test_nombre_y_apellidos_separados_y_saldo_total(base):
    personas, _ = base
    c = cliente(personas["dir"])
    contenido = "Apellidos,Nombre(s),Teléfono,Adeudo\nGómez Ruiz,Carla,5512340000,1000\nDíaz,Mario,5512340001,\n".encode()
    url, pagina = revisar(c, contenido, "padron.csv")
    formulario = pagina.context["formulario"]
    assert formulario["apellidos"].initial == "0" and formulario["nombre"].initial == "1" and formulario["saldo_total"].initial == "3"
    sin_concepto = c.post(url, {"paso": "revisar", "apellidos": "0", "nombre": "1", "telefono": "2", "saldo_total": "3"})
    assert "concepto" in sin_concepto.content.decode() and sin_concepto.context["analisis"] is None
    concepto = ConceptoCobro.objects.get(nombre="Inscripción")
    c.post(url, {"paso": "revisar", "apellidos": "0", "nombre": "1", "telefono": "2", "saldo_total": "3", "concepto_saldo_total": concepto.pk})
    c.post(url, {"paso": "confirmar"})
    carla = Titular.objects.get(nombre="Carla")
    assert carla.apellidos == "Gómez Ruiz" and Cargo.objects.get(titular=carla, origen=Cargo.SALDO_INICIAL).concepto == concepto


def test_reversion_del_saldo_inicial_solo_por_flujos_normales(base):
    personas, _ = base
    c = cliente(personas["dir"])
    url, _ = revisar(c, "Nombre completo,Celular,Saldo\nRuth Díaz León,5512000000,-100\n".encode(), "p.csv")
    concepto = ConceptoCobro.objects.get(nombre="Inscripción")
    c.post(url, {"paso": "revisar", "nombre_completo": "0", "telefono": "1", "saldo_total": "2", "concepto_saldo_total": concepto.pk})
    c.post(url, {"paso": "confirmar"})
    pago = Pago.objects.get(medio=Pago.SALDO_INICIAL)
    cliente(personas["dir"]).post(reverse("cobros:revertir", args=[pago.pk]), {"motivo": "saldo capturado por error"})
    pago.refresh_from_db()
    assert not hasattr(pago, "reversion")
    solicitud = Solicitud.objects.get(accion="revertir_pago", estado=Solicitud.PENDIENTE)
    with pytest.raises(motor.ErrorSolicitud):
        motor.aprobar(solicitud, personas["dir"])
    motor.aprobar(solicitud, personas["sup"])
    pago.refresh_from_db()
    assert hasattr(pago, "reversion")
    verificar_sumas()


def test_padron_exige_permiso_y_reingreso(base):
    personas, _ = base
    assert cliente(personas["sup"]).get(reverse("configuracion:padron_subir")).status_code == 403
    sin_reingreso = cliente(personas["dir"], reingreso=False).get(reverse("configuracion:padron_subir"))
    assert sin_reingreso.status_code == 302 and "confirmar" in sin_reingreso.url


def test_padron_hostil(base):
    personas, _ = base
    c = cliente(personas["dir"])
    from .test_banco import bomba_zip, xlsx_con_dimension_falsa

    for contenido, nombre in ((bomba_zip(), "p.xlsx"), (xlsx_con_dimension_falsa(), "p.xlsx"), (b"%PDF-1.4", "p.pdf"), (b"\x00\x01binario", "p.csv")):
        r = c.post(reverse("configuracion:padron_subir"), {"archivo": SimpleUploadedFile(nombre, contenido)})
        assert r.status_code == 200
    assert not LotePadron.objects.exists()
    filas = "\n".join(["Nombre completo,Celular"] + [f"Persona Número {i},55{i:08d}" for i in range(20001)]).encode()
    r = c.post(reverse("configuracion:padron_subir"), {"archivo": SimpleUploadedFile("p.csv", filas)})
    assert r.status_code == 200 and "filas" in r.content.decode()


def test_estado_de_cuenta_pdf_titular_y_familia(base):
    from .libro_ayudas import familia_con_dos

    personas, existente = base
    familia, ana, beto = familia_con_dos(personas["op"], personas["sup"])
    Titular.objects.filter(pk=ana.pk).update(nombre="<script>Ana</script>")
    c = cliente(personas["op"])
    r = c.get(reverse("titulares:estado_pdf", args=[ana.pk]))
    assert r["Content-Type"] == "application/pdf"
    texto = PdfReader(io.BytesIO(r.content)).pages[0].extract_text()
    assert ana.matricula_formateada in texto and "<script>Ana</script>" in texto
    r = c.get(reverse("titulares:familia_estado_pdf", args=[familia.pk]))
    texto = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert ana.matricula_formateada in texto and beto.matricula_formateada in texto
    assert Evento.objects.filter(accion="estado_de_cuenta_emitido").count() == 3
    from cuentas.models import Usuario

    sin_permiso = Usuario.objects.create_user("sinrol", "Contrasena-de-prueba-2026", nombre="Sin rol")
    assert cliente(sin_permiso).get(reverse("titulares:estado_pdf", args=[ana.pk])).status_code == 403
