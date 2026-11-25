import base64
import hashlib
import json

import pytest
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Evento
from cobros import libro
from cobros.models import ConceptoCobro, Pago
from configuracion import trabajador
from licencias import servicios as licencias
from mensajes import servicios, variables
from mensajes.models import Envio, PlantillaMensaje
from titulares.models import CampoContacto, Contacto
from titulares.servicios import crear_titular

from .conftest import cliente
from .libro_ayudas import preparar_conceptos
from .test_licencias import Central

ID_CENTRAL = "6f1c1c1e-2f6c-4a3b-9a55-0d2f4d8f7a10"


class CentralFalso:
    def __init__(self, monkeypatch):
        self.llamadas = []
        self.respuestas = {
            "mensajes_enviar": {"resultado": "aceptado", "id": ID_CENTRAL}
        }
        monkeypatch.setattr(licencias, "servicios_disponibles", lambda: True)
        monkeypatch.setattr(licencias, "pedir", self.pedir)

    def pedir(self, ruta, accion, datos, adjunto=None):
        self.llamadas.append((accion, datos, adjunto))
        respuesta = self.respuestas.get(accion)
        return (200, dict(respuesta)) if respuesta is not None else (0, {})


@pytest.fixture
def escenario(personas, monkeypatch):
    preparar_conceptos()
    telefono = CampoContacto.objects.filter(tipo=CampoContacto.TELEFONO).first()
    ana = crear_titular(
        personas["dir"],
        {"nombre": "Ana", "apellidos": "Zamora"},
        contacto={"nombre": "Rosa", "valores": {str(telefono.pk): "5512345678"}},
    )
    Contacto.objects.filter(titular=ana).update(acepta_whatsapp=True)
    libro.crear_cargo(
        ana,
        ConceptoCobro.objects.get(nombre="Inscripción"),
        777700,
        timezone.now().date(),
        "manual",
    )
    recibo = libro.registrar_pago(ana, 500000, Pago.BANCO, personas["op"]).recibo
    PlantillaMensaje.objects.filter(clave="recibo").update(estado="aprobada")
    return recibo, CentralFalso(monkeypatch), personas


def _enviar(personas, recibo, usuario="op", **datos):
    return cliente(personas[usuario]).post(
        reverse("mensajes:enviar_recibo", args=[recibo.pk]), datos
    )


def test_pedir_firma_la_peticion_de_servicio_y_sin_activar_no_llama(
    tmp_path, monkeypatch, db, settings
):
    central = Central(tmp_path, monkeypatch)
    settings.CENTRAL_URL = "https://central.invalid"
    central.respuestas = [
        lambda cuerpo: (
            200,
            {
                "resultado": "ok",
                "acuse": central.acuse(cuerpo),
                "adjunto": cuerpo.get("adjunto"),
            },
        )
    ]
    assert licencias.pedir("/v1/mensajes/estado", "mensajes_estado", {}) == (0, {})
    assert len(central.respuestas) == 1
    licencias.Instalacion.objects.filter(pk=1).update(activada=True)
    estado, respuesta = licencias.pedir(
        "/v1/mensajes/enviar", "mensajes_enviar", {"clave_envio": "x"}, b"%PDF-1"
    )
    carga = json.loads(
        base64.b64decode(
            json.loads(json.dumps({"c": respuesta["acuse"]["carga"]}))["c"]
        )
    )
    assert estado == 200 and carga["tipo"] == "acuse"
    assert base64.b64decode(respuesta["adjunto"]) == b"%PDF-1"


def test_el_recibo_se_manda_una_sola_vez_y_la_baja_quita_el_boton(escenario):
    recibo, central, personas = escenario
    pantalla = (
        cliente(personas["op"])
        .get(reverse("cobros:recibo", args=[recibo.pk]))
        .content.decode()
    )
    assert "Mandar por WhatsApp" in pantalla and "terminado en 5678" in pantalla
    assert _enviar(personas, recibo).status_code == 302
    assert _enviar(personas, recibo).status_code == 302
    ((_, datos, adjunto),) = central.llamadas
    assert (
        Envio.objects.count() == 1 and datos["clave_envio"] == f"recibo-{recibo.pk}-1"
    )
    assert (
        adjunto.startswith(b"%PDF-")
        and datos["adjunto_sha256"] == hashlib.sha256(adjunto).hexdigest()
    )
    assert (
        datos["destino"] == "+525512345678"
        and datos["valores"]["importe"] == "$5,000.00 MXN"
    )
    assert "5512345678" not in json.dumps(
        list(Evento.objects.filter(accion="whatsapp_enviado").values("datos"))
    )
    central.respuestas["mensajes_consultar"] = {
        "mensajes": [{"id": ID_CENTRAL, "estado": "entregado", "error": ""}],
        "bajas": [datos["clave_envio"]],
    }
    assert servicios.actualizar_estados() == 1
    assert (
        Envio.objects.get().estado == "entregado"
        and Contacto.objects.get().baja_whatsapp
    )
    assert (
        "Mandar por WhatsApp"
        not in cliente(personas["op"])
        .get(reverse("cobros:recibo", args=[recibo.pk]))
        .content.decode()
    )


def test_sin_consentimiento_ni_permiso_ni_recibo_ajeno_no_se_llama_a_central(escenario):
    recibo, central, personas = escenario
    Contacto.objects.update(acepta_whatsapp=False)
    assert (
        "Pedir permiso para mandar por WhatsApp"
        in cliente(personas["dir"])
        .get(reverse("cobros:recibo", args=[recibo.pk]))
        .content.decode()
    )
    _enviar(personas, recibo)
    Contacto.objects.update(acepta_whatsapp=True)
    assert _enviar(personas, recibo, "op2").status_code == 403
    assert _enviar(personas, recibo, "sup").status_code == 302
    from cuentas.models import PermisoRol

    PermisoRol.objects.filter(
        rol=personas["sup"].rol, permiso="enviar_whatsapp"
    ).delete()
    assert _enviar(personas, recibo, "sup2").status_code == 403
    assert len(central.llamadas) == 1 and Envio.objects.count() == 1


def test_plantillas_rechazan_datos_ajenos_y_se_muestran_escapadas(escenario):
    _, central, personas = escenario
    central.respuestas["mensajes_plantilla"] = {
        "resultado": "en_revision",
        "motivo": "",
    }
    for texto in (
        "Hola [nombre], mira [secreto]",
        "[nombre] hola",
        "Hola [nombre][folio] adiós",
        "Hola {{1}} adiós",
    ):
        with pytest.raises(ValueError):
            servicios.guardar_plantilla("recibo", "Recibo", texto, personas["dir"])
    guardada = servicios.guardar_plantilla(
        "recibo", "Recibo <b>", "Hola [nombre] <script>x</script>", personas["dir"]
    )
    assert (
        guardada.estado == "en_revision"
        and central.llamadas[-1][1]["con_documento"] is True
    )
    central.respuestas["mensajes_estado"] = {
        "conectado": True,
        "numero_final": "0000",
        "plantillas": [],
        "enviados_mes": 0,
        "tope": 5,
        "tope_maximo": 9,
    }
    pantalla = cliente(personas["dir"]).get(reverse("mensajes:panel")).content.decode()
    assert (
        "<script>x" not in pantalla
        and "&lt;script&gt;" in pantalla
        and "terminado en 0000" in pantalla
    )
    assert variables.rellenar("Hola [nombre]", variables.EJEMPLOS) == "Hola María"


def test_sin_central_el_panel_lo_explica_y_ni_el_trabajador_ni_el_recibo_fallan(
    personas, db, monkeypatch, settings
):
    def no_debe_llamarse(*argumentos):
        raise AssertionError("se llamó a Central")

    monkeypatch.setattr(licencias.cliente, "enviar", no_debe_llamarse)
    settings.CENTRAL_URL = ""
    assert servicios.estado() == {"disponible": False}
    assert (
        "todavía no está disponible"
        in cliente(personas["dir"]).get(reverse("mensajes:panel")).content.decode()
    )
    assert all(
        exito
        for nombre, exito, _ in trabajador.ejecutar_ciclo()
        if nombre == "mensajes"
    )


def test_respuesta_sin_acuse_valido_no_cuenta_como_respuesta(
    tmp_path, monkeypatch, db, settings
):
    central = Central(tmp_path, monkeypatch)
    settings.CENTRAL_URL = "https://central.invalid"
    licencias.Instalacion.objects.filter(pk=1).update(activada=True)
    central.respuestas = [
        lambda cuerpo: (200, {"resultado": "aceptado"}),
        lambda cuerpo: (200, {"resultado": "aceptado", "acuse": {"carga": "x"}}),
    ]
    for _ in central.respuestas[:]:
        assert licencias.pedir("/v1/mensajes/estado", "mensajes_estado", {}) == (0, {})


def test_si_no_se_sabe_si_salio_se_reintenta_con_la_misma_clave(escenario):
    recibo, central, personas = escenario
    central.respuestas.clear()
    assert _enviar(personas, recibo).status_code == 302
    envio = Envio.objects.get()
    assert envio.estado == Envio.INCIERTO and "no se cobra doble" in envio.motivo
    central.respuestas["mensajes_enviar"] = {"resultado": "repetido", "id": ID_CENTRAL}
    assert _enviar(personas, recibo).status_code == 302
    assert [c[1]["clave_envio"] for c in central.llamadas] == [envio.clave_envio] * 2
    envio.refresh_from_db()
    assert envio.estado == Envio.ACEPTADO and Envio.objects.count() == 1
