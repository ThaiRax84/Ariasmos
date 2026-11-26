import base64
import contextlib
import hashlib
import json
import uuid

import pytest
from django.conf import settings
from django.urls import reverse

from auditoria.models import Evento
from cobros import libro
from configuracion import trabajador
from configuracion.models import hoy_negocio
from cuentas.models import PermisoRol
from licencias import cliente as cliente_central
from licencias import servicios as licencias
from licencias.models import Instalacion
from mensajes import servicios as mensajes
from mensajes.models import Envio, PlantillaMensaje
from pruebas.conftest import cliente
from pruebas.libro_ayudas import preparar_conceptos, titular_activo, turno_de
from selladas.producto.test_licencia_producto import central, hora, licencia, local  # noqa: F401  fixtures de la fase 12
from selladas.producto.test_vuelta2_producto import acuse, carga_de
from titulares.models import CampoContacto, Contacto

TELEFONO = "55 1234 5678"
DESTINO = "+525512345678"
HOSTIL = "<script>alert('plantilla')</script>"
ENVIAR = "/v1/mensajes/enviar"


def plantilla_de_central(clave="recibo", estado="aprobada", texto="Hola [nombre], te mandamos tu recibo [folio].", motivo=""):
    return {"clave": clave, "nombre": clave.capitalize(), "texto": texto, "con_documento": clave == "recibo", "estado": estado, "motivo": motivo}


class CentralFalso:
    def __init__(self, privada, hora):
        self.privada = privada
        self.hora = hora
        self.llamadas = []
        self.plantillas = [plantilla_de_central()]
        self.resultado_envio = "aceptado"
        self.bajas = []
        self.ids = {}

    def __call__(self, ruta, cuerpo):
        if not settings.CENTRAL_URL:
            raise cliente_central.SinConexion("sin dirección de Central")
        self.llamadas.append((ruta, cuerpo))
        carga = carga_de(cuerpo)
        respuesta = self.responder(ruta, carga["datos"])
        respuesta["acuse"] = acuse(self.privada, carga["instalacion"], carga["sello"], self.hora.momento)
        return 200, respuesta

    def responder(self, ruta, datos):
        if ruta == "/v1/mensajes/estado":
            return {"conectado": True, "numero_final": "1111", "plantillas": self.plantillas, "enviados_mes": len(self.ids), "tope": 500, "tope_maximo": 500}
        if ruta == ENVIAR:
            if self.resultado_envio != "aceptado":
                return {"resultado": self.resultado_envio, "id": None}
            if datos["clave_envio"] in self.ids:
                return {"resultado": "repetido", "id": self.ids[datos["clave_envio"]]}
            self.ids[datos["clave_envio"]] = str(uuid.uuid4())
            return {"resultado": "aceptado", "id": self.ids[datos["clave_envio"]]}
        if ruta == "/v1/mensajes/consultar":
            return {"mensajes": [{"id": i, "estado": "entregado", "error": ""} for i in datos["ids"]], "bajas": list(self.bajas)}
        if ruta == "/v1/mensajes/plantilla":
            return {"resultado": "en_revision", "motivo": ""}
        if ruta == "/v1/mensajes/tope":
            return {"resultado": "guardado"}
        raise AssertionError(f"ruta inesperada {ruta}")

    def rutas(self):
        return [ruta for ruta, _ in self.llamadas]

    def envios(self):
        return [cuerpo for ruta, cuerpo in self.llamadas if ruta == ENVIAR]


@pytest.fixture
def falso(central, hora, monkeypatch):
    simulado = CentralFalso(central, hora)
    monkeypatch.setattr(cliente_central, "enviar", simulado)
    return simulado


@pytest.fixture
def gente(personas):
    preparar_conceptos()
    personas["turnos"] = {"op": turno_de(personas["op"]), "op2": turno_de(personas["op2"], "Caja 2")}
    return personas


@pytest.fixture
def whatsapp(central, hora, local, falso, gente):
    licencias.instalar(licencia(central, local.huella, hora.momento))
    Instalacion.objects.update(activada=True)
    PlantillaMensaje.objects.filter(clave="recibo").update(estado="aprobada")
    return falso


def recibo_de(gente, nombre, quien="op", acepta=True, telefono=TELEFONO):
    titular = titular_activo(gente["op"], gente["sup"], nombre)
    campo = CampoContacto.objects.get(tipo=CampoContacto.TELEFONO)
    contacto = titular.contactos.get(principal=True)
    Contacto.objects.filter(pk=contacto.pk).update(valores={str(campo.pk): telefono} if telefono else {}, acepta_whatsapp=acepta)
    turno = gente["turnos"].get(quien)
    pago = libro.registrar_pago(titular, 125000, "efectivo" if turno else "banco", gente[quien], turno=turno)
    return pago.recibo, contacto


def url_envio(recibo):
    return reverse("mensajes:enviar_recibo", args=[recibo.pk])


def ofrece_boton(c, recibo):
    respuesta = c.get(reverse("cobros:recibo", args=[recibo.pk]))
    assert respuesta.status_code == 200
    return url_envio(recibo) in respuesta.content.decode()


def enviados_con_exito():
    return Envio.objects.exclude(estado="no_enviado")


def comprobar_envio(cuerpo, recibo):
    datos = carga_de(cuerpo)["datos"]
    assert carga_de(cuerpo)["accion"] == "mensajes_enviar"
    assert (datos["clave_envio"], datos["plantilla"], datos["destino"]) == (f"recibo-{recibo.pk}-1", "recibo", DESTINO)
    adjunto = base64.b64decode(cuerpo["adjunto"])
    assert adjunto.startswith(b"%PDF-") and hashlib.sha256(adjunto).hexdigest() == datos["adjunto_sha256"]


def test_6_tras_la_baja_el_programa_marca_el_contacto_y_quita_el_boton(whatsapp, gente):
    op = cliente(gente["op"])
    recibo, contacto = recibo_de(gente, "Ana")
    assert ofrece_boton(op, recibo)
    op.post(url_envio(recibo))
    assert len(whatsapp.envios()) == 1 and Envio.objects.get(recibo=recibo).estado == "aceptado"

    whatsapp.bajas = [f"recibo-{recibo.pk}-1"]
    mensajes.actualizar_estados()
    assert "/v1/mensajes/consultar" in whatsapp.rutas()
    assert Contacto.objects.get(pk=contacto.pk).baja_whatsapp
    assert not ofrece_boton(op, recibo)
    op.post(url_envio(recibo))
    assert len(whatsapp.envios()) == 1

    otro, otro_contacto = recibo_de(gente, "Beto")
    assert ofrece_boton(op, otro)
    whatsapp.resultado_envio = "baja"
    op.post(url_envio(otro))
    assert len(whatsapp.envios()) == 2
    assert Envio.objects.get(recibo=otro).estado == "no_enviado"
    assert Contacto.objects.get(pk=otro_contacto.pk).baja_whatsapp
    assert not ofrece_boton(op, otro)
    whatsapp.resultado_envio = "aceptado"
    op.post(url_envio(otro))
    assert len(whatsapp.envios()) == 2


def test_7_sin_consentimiento_permiso_o_acceso_al_recibo_no_se_manda(whatsapp, gente):
    rol = gente["op"].rol
    assert "enviar_whatsapp" in rol.permisos()
    op = cliente(gente["op"])
    propio, contacto = recibo_de(gente, "Ana", acepta=False)
    ajeno, _ = recibo_de(gente, "Beto", quien="op2")

    assert not ofrece_boton(op, propio)
    respuestas = [op.post(url_envio(propio)), op.post(url_envio(ajeno)), op.get(url_envio(propio))]
    Contacto.objects.filter(pk=contacto.pk).update(acepta_whatsapp=True)
    PermisoRol.objects.filter(rol=rol, permiso="enviar_whatsapp").delete()
    op = cliente(gente["op"])
    respuestas += [op.post(url_envio(propio)), op.post(url_envio(ajeno))]
    assert all(r.status_code < 500 for r in respuestas)
    assert ENVIAR not in whatsapp.rutas() and not enviados_con_exito().exists()
    assert not ofrece_boton(op, propio)

    PermisoRol.objects.create(rol=rol, permiso="enviar_whatsapp")
    op = cliente(gente["op"])
    assert ofrece_boton(op, propio)
    op.post(url_envio(propio))
    op.post(url_envio(propio))
    assert whatsapp.envios()
    for cuerpo in whatsapp.envios():
        comprobar_envio(cuerpo, propio)
    assert list(enviados_con_exito().values_list("recibo", "clave_envio", "estado")) == [(propio.pk, f"recibo-{propio.pk}-1", "aceptado")]
    bitacora = json.dumps(list(Evento.objects.filter(accion="whatsapp_enviado").values_list("datos", flat=True)))
    assert Evento.objects.filter(accion="whatsapp_enviado").exists() and "5512345678" not in bitacora

    llamadas = len(whatsapp.envios())
    sup = cliente(gente["sup"])
    assert sup.post(url_envio(ajeno)).status_code < 500
    assert len(whatsapp.envios()) == llamadas + 1
    assert carga_de(whatsapp.envios()[-1])["datos"]["clave_envio"] == f"recibo-{ajeno.pk}-1"


def test_8_plantilla_sin_aprobar_variables_ajenas_y_texto_escapado(whatsapp, gente):
    direccion = gente["dir"]
    antes = PlantillaMensaje.objects.get(clave="recordatorio").texto
    for texto in (
        "Hola [nombre], tu teléfono [telefono] quedó registrado.",
        "Hola [Nombre], te recordamos tu pago.",
        "Hola [nombre], {{1}} [script] te recordamos.",
        "[nombre] te recordamos tu pago pendiente.",
        "Te recordamos tu pago pendiente, [nombre]",
        "Hola [nombre][alumno], te recordamos tu pago.",
    ):
        with contextlib.suppress(Exception):
            mensajes.guardar_plantilla("recordatorio", "Recordatorio", texto, direccion)
        assert PlantillaMensaje.objects.get(clave="recordatorio").texto == antes
    assert "/v1/mensajes/plantilla" not in whatsapp.rutas()
    valido = "Hola [nombre], te recordamos el pago de [concepto]."
    mensajes.guardar_plantilla("recordatorio", "Recordatorio", valido, direccion)
    assert PlantillaMensaje.objects.get(clave="recordatorio").texto == valido
    assert whatsapp.rutas().count("/v1/mensajes/plantilla") == 1

    op = cliente(gente["op"])
    recibo, _ = recibo_de(gente, "Ana")
    PlantillaMensaje.objects.filter(clave="recibo").update(estado="en_revision")
    whatsapp.plantillas = [plantilla_de_central(estado="en_revision")]
    assert not ofrece_boton(op, recibo)
    op.post(url_envio(recibo))
    assert ENVIAR not in whatsapp.rutas() and not enviados_con_exito().exists()

    PlantillaMensaje.objects.filter(clave="atraso").update(texto=f"Hola [nombre] {HOSTIL} vence [fecha].", motivo=HOSTIL)
    whatsapp.plantillas = [plantilla_de_central(), plantilla_de_central("atraso", "rechazada", f"Hola [nombre] {HOSTIL} fin.", HOSTIL)]
    respuesta = cliente(direccion).get(reverse("mensajes:panel"))
    assert respuesta.status_code == 200
    assert HOSTIL not in respuesta.content.decode() and "<script>alert" not in respuesta.content.decode()


@pytest.mark.parametrize("falta", ["direccion_de_central", "activacion"])
def test_10_sin_central_no_hay_boton_y_nada_falla(central, hora, local, falso, gente, settings, falta):
    if falta == "direccion_de_central":
        licencias.instalar(licencia(central, local.huella, hora.momento))
        Instalacion.objects.update(activada=True)
        settings.CENTRAL_URL = ""
    else:
        Instalacion.objects.update(activada=False)
    PlantillaMensaje.objects.filter(clave="recibo").update(estado="aprobada")
    op = cliente(gente["op"])
    recibo, _ = recibo_de(gente, "Ana")

    assert mensajes.estado() == {"disponible": False}
    assert not ofrece_boton(op, recibo)
    assert cliente(gente["dir"]).get(reverse("mensajes:panel")).status_code == 200
    assert op.post(url_envio(recibo)).status_code < 500
    assert not enviados_con_exito().exists()
    mensajes.actualizar_estados()
    tareas = {nombre: funcion for nombre, funcion, _ in trabajador.TAREAS}
    tareas["mensajes"](hoy_negocio())
    assert falso.llamadas == []
