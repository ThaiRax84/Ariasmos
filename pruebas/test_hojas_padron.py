from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from auditoria.models import Evento
from cobros.models import Cargo
from cuentas.models import PermisoRol, Rol
from solicitudes import motor
from solicitudes.models import Solicitud
from titulares import contactos, padron
from titulares.models import LotePadron, Titular

from .conftest import cliente, nuevo_usuario
from .libro_ayudas import preparar_conceptos, titular_activo

COLUMNAS = {"paso": "revisar", "matricula": "0", "nombre_completo": "1", "agrupacion": "2", "responsable": "3", "telefono": "4", "saldo_total": "5"}


@pytest.fixture
def base(personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    beto = titular_activo(personas["op"], personas["sup"], "Beto")
    return personas, ana, beto


def csv_de(*filas):
    return ("Matrícula,Alumno,Grupo,Tutor,Celular,Saldo\n" + "\n".join(",".join(f) for f in filas) + "\n").encode()


def subir(c, contenido, columnas=None):
    respuesta = c.post(reverse("configuracion:padron_subir"), {"archivo": SimpleUploadedFile("hoja.csv", contenido)})
    assert respuesta.status_code == 302, respuesta.content.decode()[-1500:]
    url = respuesta.url
    from cobros.models import ConceptoCobro

    datos = dict(COLUMNAS if columnas is None else columnas)
    if "saldo_total" in datos:
        datos["concepto_saldo_total"] = ConceptoCobro.objects.get(nombre="Inscripción").pk
    previa = c.post(url, datos)
    return url, previa


def hojas_guardadas():
    carpeta = padron.carpeta_hojas()
    return sorted(p.name for p in Path(carpeta).iterdir())


def test_hoja_mixta_de_operacion_se_vuelve_una_solicitud_y_nada_cambia_antes(base, django_capture_on_commit_callbacks):
    personas, ana, beto = base
    matricula_ana = ana.matricula
    c = cliente(personas["op"])
    contenido = csv_de(
        [ana.matricula, "Ana Prueba", "3B", "Marta Nueva", "5512345678", ""],
        ["", "Carla Díaz León", "1A", "Rosa Díaz", "5598765432", "500"],
        ["9999999", "Nadie", "1A", "", "", ""],
        [beto.matricula, "", "", "", "", "300"],
    )
    url, previa = subir(c, contenido)
    analisis = previa.context["analisis"]
    tipos = [(f["tipo"], bool(f["errores"]), f["duplicado"]) for f in analisis["filas"]]
    assert tipos == [("cambio", False, ""), ("alta", False, ""), ("cambio", True, ""), ("cambio", False, "sin cambios")]
    assert "no existe" in analisis["filas"][2]["errores"][0]
    assert "los saldos no cambian" in analisis["filas"][3]["avisos"][0]
    assert previa.context["resumen"]["altas"] == 1 and previa.context["resumen"]["cambios"] == 1
    respuesta = c.post(url, {"paso": "confirmar"})
    solicitud = Solicitud.objects.get(accion="importacion_padron")
    assert respuesta.url == reverse("solicitudes:detalle", args=[solicitud.pk])
    assert solicitud.estado == Solicitud.PENDIENTE and solicitud.titular is None
    assert (solicitud.datos["altas"], solicitud.datos["cambios"]) == (1, 1)
    assert not LotePadron.objects.exists() and not Titular.objects.filter(nombre="Carla").exists()
    ana.refresh_from_db()
    assert ana.agrupacion is None and contactos.principal(ana).nombre == "Resp"
    assert hojas_guardadas() == [solicitud.datos["hoja"]]
    with pytest.raises(motor.ErrorSolicitud):
        motor.aprobar(solicitud, personas["op"])
    detalle = cliente(personas["sup"]).get(reverse("solicitudes:detalle", args=[solicitud.pk])).content.decode()
    assert "Detalle de la hoja" in detalle and "Marta Nueva" in detalle and "Carla" in detalle
    with django_capture_on_commit_callbacks(execute=True):
        motor.aprobar(solicitud, personas["sup"])
    lote = LotePadron.objects.get()
    assert (lote.creados, lote.actualizados, lote.saltados, lote.solicitud_id, lote.autorizado_por) == (1, 1, 0, solicitud.pk, personas["sup"])
    ana.refresh_from_db()
    assert str(ana.agrupacion) == "3B" and contactos.principal(ana).nombre == "Marta Nueva"
    assert ana.matricula == matricula_ana and ana.estado == Titular.ACTIVO
    beto.refresh_from_db()
    assert not Cargo.objects.filter(titular=beto, origen=Cargo.SALDO_INICIAL).exists()
    evento = Evento.objects.get(accion="titular_actualizado_por_hoja")
    assert evento.titular == ana.pk and evento.datos["solicito"] == str(personas["op"]) and evento.datos["aprobo"] == str(personas["sup"])
    assert hojas_guardadas() == []


def test_matricula_saldo_y_estado_nunca_cambian_desde_la_hoja(base):
    personas, ana, beto = base
    antes = (ana.matricula, ana.estado, Cargo.objects.filter(titular=ana).count())
    contenido = "Matrícula,Estado,Saldo,Grupo\n" + f"{ana.matricula},baja,1000,2C\n"
    url, previa = subir(cliente(personas["dir"]), contenido.encode(), {"paso": "revisar", "matricula": "0", "saldo_total": "2", "agrupacion": "3"})
    fila = previa.context["analisis"]["filas"][0]
    assert set(fila["cambios"]) == {"agrupacion"} and fila["avisos"]
    cliente(personas["dir"]).post(url, {"paso": "confirmar"})
    ana.refresh_from_db()
    assert (ana.matricula, ana.estado, Cargo.objects.filter(titular=ana).count()) == antes
    assert str(ana.agrupacion) == "2C"


def test_lo_que_cambio_entre_subir_y_aprobar_se_salta(base):
    personas, ana, beto = base
    contenido = csv_de([ana.matricula, "", "4A", "", "", ""], [beto.matricula, "", "4B", "", "", ""])
    url, _ = subir(cliente(personas["op"]), contenido)
    cliente(personas["op"]).post(url, {"paso": "confirmar"})
    solicitud = Solicitud.objects.get(accion="importacion_padron")
    from titulares.models import Agrupacion

    Titular.objects.filter(pk=ana.pk).update(agrupacion=Agrupacion.objects.create(nombre="Otro"))
    motor.aprobar(solicitud, personas["sup"])
    lote = LotePadron.objects.get()
    assert lote.actualizados == 1 and lote.saltados == 1 and "cambió desde que se subió" in lote.resultado["saltados"][0]
    ana.refresh_from_db()
    beto.refresh_from_db()
    assert str(ana.agrupacion) == "Otro" and str(beto.agrupacion) == "4B"


def test_cambio_de_nombre_en_la_hoja_respeta_la_aprobacion(base):
    personas, ana, _ = base
    importadora = Rol.objects.create(nombre="Importadora", requiere_totp=True)
    for permiso in ("importar_padron", "ver_titulares"):
        PermisoRol.objects.create(rol=importadora, permiso=permiso)
    persona = nuevo_usuario("importadora", importadora)
    url, _ = subir(cliente(persona), csv_de([ana.matricula, "Ana María Prueba", "", "", "", ""]))
    respuesta = cliente(persona).post(url, {"paso": "confirmar"})
    solicitud = Solicitud.objects.get(accion="importacion_padron")
    assert "solicitudes" in respuesta.url and solicitud.datos["nombres"] == 1
    assert Evento.objects.filter(accion="solicitud_obligatoria").exists()
    motor.aprobar(solicitud, personas["dir"])
    ana.refresh_from_db()
    assert (ana.nombre, ana.apellidos) == ("Ana", "María Prueba")


def test_direccion_aplica_directo_y_rechazo_borra_la_hoja(base, django_capture_on_commit_callbacks):
    personas, ana, _ = base
    url, _ = subir(cliente(personas["dir"]), csv_de([ana.matricula, "", "5A", "", "", ""]))
    with django_capture_on_commit_callbacks(execute=True):
        respuesta = cliente(personas["dir"]).post(url, {"paso": "confirmar"})
    lote = LotePadron.objects.get()
    assert respuesta.url == reverse("configuracion:padron_lote", args=[lote.pk]) and lote.actualizados == 1 and lote.solicitud is None
    assert hojas_guardadas() == []
    url, _ = subir(cliente(personas["op"]), csv_de([ana.matricula, "", "6A", "", "", ""]))
    cliente(personas["op"]).post(url, {"paso": "confirmar"})
    solicitud = Solicitud.objects.get(accion="importacion_padron")
    assert len(hojas_guardadas()) == 1
    with django_capture_on_commit_callbacks(execute=True):
        motor.rechazar(solicitud, personas["sup"], "no")
    assert hojas_guardadas() == []
    ana.refresh_from_db()
    assert str(ana.agrupacion) == "5A"


def test_la_hoja_caducada_se_borra(base, django_capture_on_commit_callbacks):
    from datetime import timedelta

    from django.utils import timezone

    personas, ana, _ = base
    url, _ = subir(cliente(personas["op"]), csv_de([ana.matricula, "", "7A", "", "", ""]))
    cliente(personas["op"]).post(url, {"paso": "confirmar"})
    Solicitud.objects.filter(accion="importacion_padron").update(caduca_en=timezone.now() - timedelta(minutes=1))
    with django_capture_on_commit_callbacks(execute=True):
        motor.caducar_vencidas()
    assert hojas_guardadas() == []


def test_hoja_alterada_no_se_aplica(base):
    personas, ana, _ = base
    url, _ = subir(cliente(personas["op"]), csv_de([ana.matricula, "", "8A", "", "", ""]))
    cliente(personas["op"]).post(url, {"paso": "confirmar"})
    solicitud = Solicitud.objects.get(accion="importacion_padron")
    ruta = padron.carpeta_hojas() / solicitud.datos["hoja"]
    ruta.write_text(ruta.read_text().replace("8A", "9Z"))
    with pytest.raises(motor.ErrorSolicitud):
        motor.aprobar(solicitud, personas["sup"])
    ana.refresh_from_db()
    assert ana.agrupacion is None


def test_formulas_y_celdas_maliciosas_son_texto(base):
    personas, ana, _ = base
    contenido = csv_de([ana.matricula, "", "=HYPERLINK(\"http://x\")", "<script>alert(1)</script>", "", ""])
    url, previa = subir(cliente(personas["dir"]), contenido)
    html = previa.content.decode()
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    cliente(personas["dir"]).post(url, {"paso": "confirmar"})
    ana.refresh_from_db()
    assert str(ana.agrupacion) == '=HYPERLINK("http://x")'
    lote = LotePadron.objects.get()
    assert cliente(personas["dir"]).get(reverse("configuracion:padron_lote", args=[lote.pk])).status_code == 200


def test_quien_no_ve_datos_no_ve_los_valores_anteriores(base):
    personas, ana, _ = base
    Titular.objects.filter(pk=ana.pk).update(notas="")
    solo_hoja = Rol.objects.create(nombre="Solo hoja")
    PermisoRol.objects.create(rol=solo_hoja, permiso="solicitar_importacion_padron")
    persona = nuevo_usuario("solo_hoja", solo_hoja)
    url, previa = subir(cliente(persona), csv_de([ana.matricula, "", "9B", "Persona Nueva", "", "100"], ["", "Dora Luna Sol", "1A", "", "", "250"]))
    html = previa.content.decode()
    assert "Persona Nueva" in html and "Resp →" not in html and "$250" not in html and "<th>Saldos</th>" not in html
    assert previa.context["ve_datos"] is False


def test_permisos_de_la_hoja(base):
    personas, _, _ = base
    nadie = nuevo_usuario("nadie", Rol.objects.create(nombre="Sin hoja"))
    assert cliente(nadie).get(reverse("configuracion:padron_subir")).status_code == 403
    assert cliente(personas["op"]).get(reverse("configuracion:padron_subir")).status_code == 200
    lista = cliente(personas["op"]).get(reverse("titulares:lista")).content.decode()
    assert "Importar o actualizar desde una hoja" in lista
