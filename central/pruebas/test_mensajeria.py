import base64
import hashlib
import hmac
import json
import urllib.parse
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.core.management import call_command
from django.test import Client

from emision import reloj
from emision import servicios as emision
from emision.models import Bitacora
from mensajeria import secretos
from mensajeria.models import Baja, Documento, Mensaje, Plantilla, Remitente
from mensajeria.proveedores import simulado, twilio
from nucleo import licencia

PDF = b"%PDF-1.4 recibo de prueba"
TOKEN_SECRETO = "token-secreto-de-twilio"


class Equipo:
    def __init__(self, negocio, sello="f" * 32):
        self.privada = Ed25519PrivateKey.generate()
        publica = self.privada.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.huella = licencia.huella(publica)
        codigo = emision.crear_codigo(negocio)
        carga = {
            "formato": 1,
            "producto": "ariasmos",
            "tipo": "activacion",
            "instalacion": self.huella,
            "momento": licencia.texto_de(reloj.ahora()),
            "sello": sello,
            "version": "1.0.0",
        }
        cuerpo = {
            "codigo": codigo,
            "llave_publica": base64.b64encode(publica).decode(),
            **licencia.firmar(carga, self.privada),
        }
        assert (
            Client()
            .post("/v1/activar", json.dumps(cuerpo), content_type="application/json")
            .status_code
            == 200
        )
        self.sellos = 0

    def pedir(self, ruta, accion, datos, adjunto=None, momento=None, sello=None):
        self.sellos += 1
        carga = {
            "formato": 1,
            "producto": "ariasmos",
            "tipo": "servicio",
            "instalacion": self.huella,
            "momento": licencia.texto_de(momento or reloj.ahora()),
            "sello": sello or f"{self.sellos:032x}",
            "version": "1.0.0",
            "accion": accion,
            "datos": datos,
        }
        cuerpo = {"instalacion": self.huella, **licencia.firmar(carga, self.privada)}
        if adjunto is not None:
            cuerpo["adjunto"] = base64.b64encode(adjunto).decode()
        return Client().post(ruta, json.dumps(cuerpo), content_type="application/json")


@pytest.fixture
def negocio(db):
    simulado.ENVIADOS.clear()
    negocio = emision.crear_negocio("Negocio de prueba")
    emision.registrar_pago(negocio, reloj.ahora().date() + timedelta(days=90))
    return negocio


@pytest.fixture
def equipo(negocio):
    return Equipo(negocio)


@pytest.fixture
def conectado(negocio, equipo, monkeypatch):
    monkeypatch.setenv("TWILIO_TOKEN", TOKEN_SECRETO)
    call_command(
        "whatsapp_conectar",
        str(negocio.pk),
        numero="+525512345678",
        cuenta="AC123456",
        servicio="MG123456",
    )
    return negocio


def _enviar(equipo, clave="recibo-1-1", destino="+525587654321", **extra):
    datos = {
        "clave_envio": clave,
        "plantilla": "recibo",
        "destino": destino,
        "valores": {"nombre": "Ana", "folio": "A-1"},
        "adjunto_sha256": hashlib.sha256(PDF).hexdigest(),
    }
    return equipo.pedir(
        "/v1/mensajes/enviar", "mensajes_enviar", datos, extra.get("adjunto", PDF)
    )


def _aprobar(equipo):
    datos = {
        "clave": "recibo",
        "nombre": "Recibo",
        "texto": "Hola [nombre], tu recibo [folio] va adjunto.",
        "con_documento": True,
    }
    respuesta = equipo.pedir("/v1/mensajes/plantilla", "mensajes_plantilla", datos)
    assert respuesta.json()["resultado"] == "aprobada"


def test_peticiones_falsas_dan_403_y_nada_llega_al_proveedor(conectado, equipo):
    _aprobar(equipo)
    repetida = equipo.pedir(
        "/v1/mensajes/estado", "mensajes_estado", {}, sello="a" * 32
    )
    assert repetida.status_code == 200 and "acuse" in repetida.json()
    mala = [
        equipo.pedir("/v1/mensajes/estado", "mensajes_estado", {}, sello="a" * 32),
        equipo.pedir("/v1/mensajes/enviar", "mensajes_estado", {}),
        equipo.pedir(
            "/v1/mensajes/estado",
            "mensajes_estado",
            {},
            momento=reloj.ahora() - timedelta(hours=2),
        ),
        Equipo(emision.crear_negocio("Sin pago")).pedir(
            "/v1/mensajes/enviar", "mensajes_enviar", {}
        ),
    ]
    assert {r.status_code for r in mala} == {403}
    assert len({r.content for r in mala}) == 1
    assert simulado.ENVIADOS == []


def test_enviar_repetir_entregar_y_baja(conectado, equipo):
    _aprobar(equipo)
    primero = _enviar(equipo).json()
    assert primero["resultado"] == "aceptado"
    repetido = _enviar(equipo).json()
    assert (repetido["resultado"], repetido["id"]) == ("repetido", primero["id"])
    assert len(simulado.ENVIADOS) == 1
    mensaje = Mensaje.objects.get(pk=primero["id"])
    assert Documento.objects.filter(mensaje=mensaje).exists()
    firmado = {"HTTP_X_TWILIO_SIGNATURE": simulado.FIRMA}
    assert (
        Client()
        .post(f"/v1/twilio/estado/{mensaje.pk}", {"MessageStatus": "delivered"})
        .status_code
        == 403
    )
    assert (
        Client()
        .post(
            f"/v1/twilio/estado/{mensaje.pk}", {"MessageStatus": "delivered"}, **firmado
        )
        .status_code
        == 200
    )
    Client().post(
        f"/v1/twilio/estado/{mensaje.pk}", {"MessageStatus": "sent"}, **firmado
    )
    mensaje.refresh_from_db()
    assert mensaje.estado == "entregado" and not Documento.objects.exists()
    Client().post(
        f"/v1/twilio/entrante/{conectado.pk}",
        {"From": "whatsapp:+525587654321", "Body": " baja "},
        **firmado,
    )
    assert Baja.objects.count() == 1
    assert _enviar(equipo, clave="recibo-1-2").json()["resultado"] == "baja"
    assert len(simulado.ENVIADOS) == 1
    consultado = equipo.pedir(
        "/v1/mensajes/consultar", "mensajes_consultar", {"ids": [primero["id"]]}
    ).json()
    assert (
        consultado["bajas"] == ["recibo-1-1"]
        and consultado["mensajes"][0]["estado"] == "entregado"
    )


def test_tope_y_entradas_hostiles_nunca_dan_500(conectado, equipo):
    _aprobar(equipo)
    assert (
        equipo.pedir("/v1/mensajes/tope", "mensajes_tope", {"tope": 1}).json()[
            "resultado"
        ]
        == "guardado"
    )
    assert (
        equipo.pedir("/v1/mensajes/tope", "mensajes_tope", {"tope": 501}).json()[
            "resultado"
        ]
        == "fuera_de_rango"
    )
    assert _enviar(equipo).json()["resultado"] == "aceptado"
    assert _enviar(equipo, clave="recibo-2-1").json()["resultado"] == "tope"
    hostiles = [
        equipo.pedir("/v1/mensajes/tope", "mensajes_tope", {"tope": "1"}),
        equipo.pedir(
            "/v1/mensajes/consultar", "mensajes_consultar", {"ids": ["no-es-uuid"]}
        ),
        equipo.pedir("/v1/mensajes/consultar", "mensajes_consultar", {"ids": [1]}),
        equipo.pedir("/v1/mensajes/enviar", "mensajes_enviar", {"clave_envio": "x"}),
        Client().post("/v1/mensajes/enviar", "{roto", content_type="application/json"),
        Client().post("/v1/twilio/entrante/no-es-uuid", {"Body": "BAJA"}),
    ]
    assert all(400 <= r.status_code < 500 for r in hostiles)


def test_el_token_de_twilio_queda_cifrado_y_fuera_de_la_bitacora(conectado):
    remitente = Remitente.objects.get(negocio=conectado)
    assert TOKEN_SECRETO not in remitente.token_cifrado
    assert secretos.token_de(remitente) == TOKEN_SECRETO
    assert TOKEN_SECRETO not in json.dumps(
        list(Bitacora.objects.values("accion", "datos"))
    )


def test_twilio_firma_calculada_a_mano_y_peticion_armada(conectado, monkeypatch):
    remitente = Remitente.objects.get(negocio=conectado)
    url = "https://central.invalid/v1/twilio/estado/x"
    parametros = {"MessageStatus": ["delivered"], "Body": ["hola"]}
    texto = url + "Bodyhola" + "MessageStatusdelivered"
    firma = base64.b64encode(
        hmac.new(TOKEN_SECRETO.encode(), texto.encode(), hashlib.sha1).digest()
    ).decode()
    assert twilio.firma_valida(remitente, url, parametros, firma)
    assert not twilio.firma_valida(remitente, url, parametros, firma[:-2] + "AA")
    plantilla = Plantilla(
        negocio=conectado,
        clave="recibo",
        texto="Hola [nombre]",
        variables=["nombre"],
        con_documento=True,
        id_proveedor="HX1",
    )
    peticion = twilio.peticion_mensaje(
        remitente,
        plantilla,
        "+525587654321",
        {"nombre": "Ana"},
        "https://central.invalid/v1/documentos/tok.pdf",
        "https://central.invalid/e",
    )
    formulario = urllib.parse.parse_qs(peticion.data.decode())
    assert (
        peticion.full_url
        == "https://api.twilio.com/2010-04-01/Accounts/AC123456/Messages.json"
    )
    assert formulario["To"] == ["whatsapp:+525587654321"] and formulario[
        "ContentSid"
    ] == ["HX1"]
    assert json.loads(formulario["ContentVariables"][0]) == {"1": "Ana", "2": "tok"}
    assert (
        peticion.get_header("Authorization")
        == "Basic " + base64.b64encode(f"AC123456:{TOKEN_SECRETO}".encode()).decode()
    )
    vistas = []

    class Respuesta:
        def __enter__(self):
            return self

        def __exit__(self, *argumentos):
            return False

        def read(self):
            return b'{"sid": "SM1"}'

    monkeypatch.setattr(twilio, "urlopen", lambda p: vistas.append(p) or Respuesta())
    assert (
        twilio.enviar(
            remitente,
            plantilla,
            "+525587654321",
            {"nombre": "Ana"},
            "https://central.invalid/v1/documentos/tok.pdf",
            "https://central.invalid/e",
        )
        == "SM1"
    )
    assert vistas[0].full_url == peticion.full_url


def test_limites_exactos_de_tamano(conectado, equipo):
    _aprobar(equipo)
    grande = b"%PDF-" + b"0" * (1_550_000 - 5)
    datos = {
        "clave_envio": "g",
        "plantilla": "recibo",
        "destino": "+525587654321",
        "valores": {"nombre": "a", "folio": "b"},
        "adjunto_sha256": hashlib.sha256(grande).hexdigest(),
    }
    respuesta = equipo.pedir("/v1/mensajes/enviar", "mensajes_enviar", datos, grande)
    assert (
        respuesta.status_code in (400, 413)
        and not Mensaje.objects.exists()
        and simulado.ENVIADOS == []
    )
    relleno = json.dumps({"relleno": "x" * (2 * 1024 * 1024 + 10)})
    assert (
        Client()
        .post("/v1/mensajes/enviar", relleno, content_type="application/json")
        .status_code
        == 413
    )
    relleno = json.dumps({"relleno": "x" * (16 * 1024 + 10)})
    for ruta in ("estado", "plantilla", "tope", "consultar"):
        assert (
            Client()
            .post(f"/v1/mensajes/{ruta}", relleno, content_type="application/json")
            .status_code
            == 413
        )


def test_numero_normalizado_clave_por_instalacion_y_destino_distinto(conectado, equipo):
    _aprobar(equipo)
    conectado.instalaciones_permitidas = 2
    conectado.save()
    otro = Equipo(conectado, sello="e" * 32)
    firmado = {"HTTP_X_TWILIO_SIGNATURE": simulado.FIRMA}
    assert _enviar(equipo, destino="+5215587654321").json()["resultado"] == "aceptado"
    assert simulado.ENVIADOS[0]["destino"] == "+525587654321"
    assert _enviar(equipo, destino="+525587654321").json()["resultado"] == "repetido"
    assert _enviar(equipo, destino="+525500000000").status_code == 400
    propio = _enviar(otro).json()
    assert propio["resultado"] == "aceptado" and len(simulado.ENVIADOS) == 2
    Client().post(
        f"/v1/twilio/entrante/{conectado.pk}",
        {"From": "whatsapp:+5215587654321", "Body": "BAJA", "MessageSid": "SM9"},
        **firmado,
    )
    suyo = Mensaje.objects.get(instalacion__huella=equipo.huella).pk
    ids = [propio["id"], suyo]
    consultado = equipo.pedir(
        "/v1/mensajes/consultar", "mensajes_consultar", {"ids": [str(i) for i in ids]}
    ).json()
    assert [m["id"] for m in consultado["mensajes"]] == [str(ids[1])]
    assert consultado["bajas"] == ["recibo-1-1"]
    assert Baja.objects.count() == 1
    assert (
        _enviar(equipo, clave="p", destino="+14155550123").json()["resultado"] == "pais"
    )
    Client().post(
        f"/v1/twilio/entrante/{conectado.pk}",
        {"From": "whatsapp:+525587654321", "Body": " álta ", "MessageSid": "SM10"},
        **firmado,
    )
    consultado = equipo.pedir(
        "/v1/mensajes/consultar", "mensajes_consultar", {"ids": []}
    ).json()
    assert not Baja.objects.exists() and consultado["altas"] == ["recibo-1-1"]


def test_entrante_repetido_y_secreto_ilegible_no_cambian_nada(
    conectado, equipo, settings
):
    firmado = {"HTTP_X_TWILIO_SIGNATURE": simulado.FIRMA}
    ruta = f"/v1/twilio/entrante/{conectado.pk}"
    baja = {"From": "whatsapp:+525587654321", "Body": "BAJA", "MessageSid": "SM1"}
    assert Client().post(ruta, baja, **firmado).status_code == 200
    Baja.objects.all().delete()
    assert Client().post(ruta, baja, **firmado).status_code == 200
    assert not Baja.objects.exists()
    Remitente.objects.update(token_cifrado="ilegible")
    settings.PROVEEDOR_MENSAJES = "twilio"
    ilegible = Client().post(ruta, {**baja, "MessageSid": "SM2"}, **firmado)
    assert ilegible.status_code == 403
    assert ilegible.content == Client().post(ruta, baja).content
