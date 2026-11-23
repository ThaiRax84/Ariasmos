import base64
import json
from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.test import Client

from emision import ajustes, llave, origen, reloj, servicios
from emision.models import Ajuste, Bitacora, Instalacion, Rechazo
from nucleo import licencia


class Equipo:
    def __init__(self):
        self.privada = Ed25519PrivateKey.generate()
        self.publica = self.privada.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        )
        self.huella = licencia.huella(self.publica)

    def firmada(self, tipo, sello="a" * 32, momento=None):
        carga = {
            "formato": 1,
            "producto": "ariasmos",
            "tipo": tipo,
            "instalacion": self.huella,
            "momento": licencia.texto_de(momento or reloj.ahora()),
            "sello": sello,
            "version": "1.0.0",
        }
        return licencia.firmar(carga, self.privada)

    def activar(self, codigo, **opciones):
        cuerpo = {
            "codigo": codigo,
            "llave_publica": base64.b64encode(self.publica).decode(),
            **self.firmada("activacion", **opciones),
        }
        return Client().post(
            "/v1/activar", json.dumps(cuerpo), content_type="application/json"
        )

    def renovar(self, **opciones):
        cuerpo = {"instalacion": self.huella, **self.firmada("renovacion", **opciones)}
        return Client().post(
            "/v1/renovar", json.dumps(cuerpo), content_type="application/json"
        )


@pytest.fixture
def negocio(db):
    negocio = servicios.crear_negocio("Negocio de prueba", instalaciones=1)
    servicios.registrar_pago(negocio, reloj.ahora().date() + timedelta(days=90))
    return negocio


def test_activar_y_renovar_emiten_licencia_verificable_y_cierran_la_puerta_a_repeticiones(
    negocio,
):
    equipo = Equipo()
    codigo = servicios.crear_codigo(negocio)
    respuesta = equipo.activar(codigo)
    assert respuesta.status_code == 200 and respuesta.json()["resultado"] == "activada"
    carga = licencia.abrir(respuesta.json()["documento"], [llave.publica()], "licencia")
    assert carga["instalacion"] == equipo.huella and carga["serie"] == 1
    assert Equipo().activar(codigo).status_code == 403
    assert Equipo().activar(servicios.crear_codigo(negocio)).status_code == 403
    assert equipo.renovar().json()["resultado"] == "renovada"
    assert equipo.renovar().status_code == 403
    assert (
        equipo.renovar(
            sello="c" * 32, momento=reloj.ahora() - timedelta(hours=1)
        ).status_code
        == 403
    )
    assert Instalacion.objects.get().serie == 2


def test_sin_pago_o_revocado_central_no_emite(negocio):
    equipo = Equipo()
    assert equipo.activar(servicios.crear_codigo(negocio)).status_code == 200
    servicios.registrar_pago(negocio, date(2000, 1, 1))
    assert equipo.renovar(sello="1" * 32).json() == {"resultado": "pago_pendiente"}
    servicios.revocar(negocio)
    respuesta = equipo.renovar(sello="2" * 32).json()
    assert respuesta["resultado"] == "revocada"
    assert (
        licencia.abrir(respuesta["documento"], [llave.publica()], "revocacion")[
            "instalacion"
        ]
        == equipo.huella
    )


def test_entradas_hostiles_dan_4xx_sin_filtrar_nada_y_el_origen_se_bloquea(negocio):
    cliente = Client()
    hostiles = [
        b"x" * 20000,
        b"{",
        b"[]",
        b"null",
        b'{"a":1,"a":2}',
        b"[" * 5000 + b"]" * 5000,
        json.dumps(
            {"codigo": 1, "llave_publica": "x", "carga": "x", "firma": "x"}
        ).encode(),
        json.dumps(
            {"codigo": "' OR 1=1 --", "llave_publica": "!!", "carga": "x", "firma": "x"}
        ).encode(),
        json.dumps(
            {
                "codigo": "A",
                "llave_publica": "x",
                "carga": "x",
                "firma": "x",
                "de_mas": "x",
            }
        ).encode(),
    ]
    for cuerpo in hostiles:
        respuesta = cliente.post("/v1/activar", cuerpo, content_type="application/json")
        assert 400 <= respuesta.status_code < 500
        assert respuesta.json() in (
            {"error": "peticion"},
            {"error": "rechazada"},
            {"error": "espera"},
        )
    assert Rechazo.objects.count() == len(hostiles)
    publica = base64.b64encode(llave.publica()).decode()
    registro = json.dumps(list(Bitacora.objects.values_list("datos", flat=True)))
    assert "PRIVATE" not in registro and publica not in registro
    for _ in range(40):
        cliente.post("/v1/renovar", b"{", content_type="application/json")
    assert (
        cliente.post("/v1/renovar", b"{", content_type="application/json").status_code
        == 429
    )


def test_ajustes_absurdos_se_ignoran_y_las_rutas_ajenas_responden_json(negocio):
    Ajuste.objects.create(clave="dias_vigencia", valor=10**12)
    Ajuste.objects.create(clave="minutos_tolerancia", valor=0)
    assert (
        ajustes.valor("dias_vigencia") == 30
        and ajustes.valor("minutos_tolerancia") == 10
    )
    assert Equipo().activar(servicios.crear_codigo(negocio)).status_code == 200
    for ruta, extra in (
        ("/nada", {}),
        ("/v1/activar/", {}),
        ("/v1/salud", {"HTTP_HOST": "malo.example"}),
    ):
        respuesta = Client().get(ruta, **extra)
        assert respuesta.status_code in (400, 404) and respuesta.json() == {
            "error": "peticion"
        }
        assert respuesta["Cache-Control"] == "no-store"
    Rechazo.objects.update(momento=reloj.ahora() - timedelta(hours=2))
    Equipo().renovar()
    assert (
        Rechazo.objects.filter(momento__lt=reloj.ahora() - timedelta(hours=1)).count()
        == 0
    )


def test_origen_valida_el_reenviado_y_agrupa_ipv6(settings):
    class Peticion:
        def __init__(self, remoto, reenviado=""):
            self.META = {"REMOTE_ADDR": remoto, "HTTP_X_FORWARDED_FOR": reenviado}

    settings.PROXIES_CONFIABLES = ["10.0.0.1"]
    assert origen.de(Peticion("10.0.0.1", "9.9.9.9, 1.2.3.4")) == "1.2.3.4"
    assert origen.de(Peticion("10.0.0.1", "1.2.3.4:80")) == "10.0.0.1"
    assert origen.de(Peticion("7.7.7.7", "1.2.3.4")) == "7.7.7.7"
    assert (
        origen.de(Peticion("2001:db8::1"))
        == origen.de(Peticion("2001:db8::ffff"))
        == "2001:db8::/64"
    )


def test_activacion_repetida_acuse_y_renovacion_autentica_sobre_el_limite(negocio):
    equipo = Equipo()
    codigo = servicios.crear_codigo(negocio)
    primera = equipo.activar(codigo).json()
    repetida = equipo.activar(codigo, sello="b" * 32)
    assert repetida.status_code == 200 and repetida.json()["resultado"] == "activada"
    assert Instalacion.objects.count() == 1 and Rechazo.objects.count() == 0
    acuse = licencia.abrir(repetida.json()["acuse"], [llave.publica()], "acuse")
    assert acuse["sello"] == "b" * 32 and acuse["instalacion"] == equipo.huella
    assert primera["documento"] != repetida.json()["documento"]
    assert Client().get("/v1/salud").json()["hora"] == licencia.texto_de(reloj.ahora())
    Ajuste.objects.create(clave="rechazos_por_hora", valor=1)
    Rechazo.objects.create(origen="127.0.0.1", momento=reloj.ahora())
    bitacoras = Bitacora.objects.count()
    assert Client().get("/nada").status_code == 429
    assert (
        Client().post("/v1/renovar", b"{", content_type="application/json").status_code
        == 429
    )
    assert Rechazo.objects.count() == 1 and Bitacora.objects.count() == bitacoras
    assert equipo.renovar(sello="c" * 32).json()["resultado"] == "renovada"
