import base64
import json
import secrets
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.conf import settings
from django.test import Client
from django.utils import timezone

from emision import llave, reloj, servicios
from emision.models import Ajuste, Bitacora, CodigoActivacion, Instalacion, Negocio, Rechazo
from nucleo.licencia import LicenciaInvalida, abrir, firmar, huella, texto_de

RECHAZADA = {"error": "rechazada"}
PETICION = {"error": "peticion"}
ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def b64(datos):
    return base64.b64encode(datos).decode()


class Reloj:
    def __init__(self, momento):
        self.momento = momento

    def __call__(self):
        return self.momento


class Equipo:
    def __init__(self):
        self.privada = Ed25519PrivateKey.generate()
        self.publica = self.privada.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.huella = huella(self.publica)


@pytest.fixture
def hora(monkeypatch):
    actual = Reloj(timezone.now().replace(microsecond=0))
    monkeypatch.setattr(reloj, "ahora", actual)
    return actual


@pytest.fixture
def api():
    return Client(raise_request_exception=False)


def negocio_pagado(hora, nombre="Negocio de prueba", instalaciones=1):
    negocio = servicios.crear_negocio(nombre, instalaciones=instalaciones)
    servicios.registrar_pago(negocio, hora.momento.date() + timedelta(days=90))
    return negocio


@pytest.fixture
def negocio(db, hora):
    return negocio_pagado(hora)


def peticion(equipo, tipo, momento, firmante=None):
    carga = {"formato": 1, "producto": "ariasmos", "tipo": tipo, "instalacion": equipo.huella, "momento": texto_de(momento), "sello": secrets.token_hex(16), "version": "1.0.0"}
    return firmar(carga, (firmante or equipo).privada)


def enviar(api, ruta, cuerpo, **extra):
    return api.post(ruta, json.dumps(cuerpo), content_type="application/json", **extra)


def cuerpo_activar(equipo, codigo, momento):
    return {"codigo": codigo, "llave_publica": b64(equipo.publica), **peticion(equipo, "activacion", momento)}


def activar(api, equipo, codigo, momento, **extra):
    return enviar(api, "/v1/activar", cuerpo_activar(equipo, codigo, momento), **extra)


def renovar(api, equipo, momento):
    return enviar(api, "/v1/renovar", {"instalacion": equipo.huella, **peticion(equipo, "renovacion", momento)})


def activado(api, negocio, hora):
    equipo = Equipo()
    respuesta = activar(api, equipo, servicios.crear_codigo(negocio), hora.momento)
    assert respuesta.status_code == 200 and respuesta.json()["resultado"] == "activada"
    assert abrir(respuesta.json()["documento"], [llave.publica()], "licencia")["instalacion"] == equipo.huella
    return equipo


@pytest.fixture
def activo(api, negocio, hora):
    return activado(api, negocio, hora)


def emitidas():
    return Bitacora.objects.filter(accion="licencia_emitida").count()


def serie(equipo):
    return Instalacion.objects.get(huella=equipo.huella).serie


def test_renovacion_falsificada_no_emite(api, hora, activo):
    intruso = activado(api, negocio_pagado(hora, "Otro negocio"), hora)
    serie_antes, emitidas_antes = serie(activo), emitidas()
    buena = peticion(activo, "renovacion", hora.momento)
    firma_rota = bytearray(base64.b64decode(buena["firma"]))
    firma_rota[0] ^= 1
    intentos = [
        {**buena, "firma": b64(bytes(firma_rota))},
        peticion(activo, "renovacion", hora.momento, firmante=intruso),
        peticion(intruso, "renovacion", hora.momento),
        peticion(activo, "activacion", hora.momento),
        peticion(activo, "renovacion", hora.momento - timedelta(minutes=11)),
        peticion(activo, "renovacion", hora.momento + timedelta(minutes=11)),
    ]
    respuestas = [enviar(api, "/v1/renovar", {"instalacion": activo.huella, **intento}) for intento in intentos]

    primera = enviar(api, "/v1/renovar", {"instalacion": activo.huella, **buena})
    assert primera.status_code == 200 and primera.json()["resultado"] == "renovada"
    respuestas.append(enviar(api, "/v1/renovar", {"instalacion": activo.huella, **buena}))

    for respuesta in respuestas:
        assert respuesta.status_code == 403 and respuesta.json() == RECHAZADA
        assert respuesta.content == respuestas[0].content
    assert serie(activo) == serie_antes + 1 and emitidas() == emitidas_antes + 1


def pago_pendiente(respuesta, equipo):
    datos = respuesta.json()
    return respuesta.status_code == 200 and set(datos) == {"resultado", "acuse"} and datos["resultado"] == "pago_pendiente" and abrir(datos["acuse"], [llave.publica()], "acuse")["instalacion"] == equipo.huella


def test_sin_pago_o_revocado_central_no_emite(api, negocio, hora, activo):
    sin_pago = servicios.crear_negocio("Negocio sin pago")
    servicios.registrar_pago(sin_pago, hora.momento.date() - timedelta(days=1))
    moroso = Equipo()
    revocado = negocio_pagado(hora, "Negocio revocado", instalaciones=3)
    codigo_revocado = servicios.crear_codigo(revocado)
    servicios.revocar(revocado)
    nuevo = Equipo()
    emitidas_antes = emitidas()

    assert pago_pendiente(activar(api, moroso, servicios.crear_codigo(sin_pago), hora.momento), moroso)
    assert pago_pendiente(renovar(api, moroso, hora.momento), moroso)
    hoy = hora.momento
    hora.momento = hoy + timedelta(days=91)
    assert pago_pendiente(renovar(api, activo, hora.momento), activo)
    hora.momento = hoy

    for alcance in ({"huella": activo.huella}, {}):
        servicios.revocar(negocio, **alcance)
        respuesta = renovar(api, activo, hora.momento)
        assert respuesta.status_code == 200 and respuesta.json()["resultado"] == "revocada"
        documento = respuesta.json()["documento"]
        assert abrir(documento, [llave.publica()], "revocacion")["instalacion"] == activo.huella
        with pytest.raises(LicenciaInvalida):
            abrir(documento, [llave.publica()], "licencia")
        servicios.revocar(negocio, deshacer=True, **alcance)

    respuesta = activar(api, nuevo, codigo_revocado, hora.momento)
    assert respuesta.status_code == 403 and respuesta.json() == RECHAZADA
    assert not Instalacion.objects.filter(huella=nuevo.huella).exists()
    assert emitidas() == emitidas_antes


def test_codigos_invalidos_y_limite_de_rechazos(api, hora, db):
    negocio = negocio_pagado(hora, "Negocio con equipos", instalaciones=5)
    usado = servicios.crear_codigo(negocio)
    assert activar(api, Equipo(), usado, hora.momento).status_code == 200
    hoy = hora.momento
    hora.momento = hoy - timedelta(days=8)
    vencido = servicios.crear_codigo(negocio)
    hora.momento = hoy
    inventado = "-".join("".join(secrets.choice(ALFABETO) for _ in range(5)) for _ in range(4))
    instalaciones = Instalacion.objects.count()

    for codigo in (inventado, vencido, usado, usado.lower().replace("-", " ")):
        respuesta = activar(api, Equipo(), codigo, hora.momento)
        assert respuesta.status_code == 403 and respuesta.json() == RECHAZADA
    assert Instalacion.objects.count() == instalaciones and Rechazo.objects.count() == 4

    Ajuste.objects.create(clave="rechazos_por_hora", valor=4)
    bueno, equipo = servicios.crear_codigo(negocio), Equipo()
    for extra in ({}, {"HTTP_X_FORWARDED_FOR": "203.0.113.7"}):
        respuesta = activar(api, equipo, bueno, hora.momento, **extra)
        assert respuesta.status_code == 429 and respuesta.json() == {"error": "espera"}
    assert not Instalacion.objects.filter(huella=equipo.huella).exists() and Rechazo.objects.count() == 4

    respuesta = activar(api, equipo, bueno, hora.momento, REMOTE_ADDR="198.51.100.20")
    assert respuesta.status_code == 200 and respuesta.json()["resultado"] == "activada"


def material_de_la_llave():
    pem = Path(settings.RUTA_LLAVE_LICENCIAS).read_text()
    cuerpo_pem = "".join(linea for linea in pem.splitlines() if not linea.startswith("-----"))
    cruda = llave.privada().private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    return [cuerpo_pem, b64(cruda), cruda.hex()]


def test_entradas_hostiles_dan_4xx_y_no_filtran_la_llave(api, negocio, hora, activo):
    Ajuste.objects.create(clave="rechazos_por_hora", valor=10000)
    activacion = cuerpo_activar(Equipo(), servicios.crear_codigo(negocio), hora.momento)
    renovacion = {"instalacion": activo.huella, **peticion(activo, "renovacion", hora.momento)}
    inyecciones = ["' OR '1'='1", "<script>alert(1)</script>", "../../../../etc/passwd", "'; DROP TABLE emision_negocio; --", "\u0000", "A" * 41, "{{ settings.SECRET_KEY }}"]
    pruebas = []
    for ruta, valido in (("/v1/activar", activacion), ("/v1/renovar", renovacion)):
        pruebas += [
            (ruta, json.dumps({**valido, "relleno": "A" * 20000}), {413}),
            (ruta, "{", {400}),
            (ruta, "[]", {400}),
            (ruta, "null", {400}),
            (ruta, "[" * 5000 + "]" * 5000, {400}),
            (ruta, b"\xff\xfe\x00{", {400}),
            (ruta, '{"codigo": NaN, "instalacion": Infinity}', {400}),
            (ruta, json.dumps({**valido, "extra": 1}), {400}),
            (ruta, json.dumps({clave: v for clave, v in valido.items() if clave != "firma"}), {400}),
        ]
        for clave in valido:
            for incorrecto in (123, None, [], {}, True):
                pruebas.append((ruta, json.dumps({**valido, clave: incorrecto}), {400}))
            for texto in inyecciones:
                pruebas.append((ruta, json.dumps({**valido, clave: texto}), {400, 403}))
    negocios, instalaciones = Negocio.objects.count(), Instalacion.objects.count()
    secretos = material_de_la_llave()

    respuestas = [(api.post(ruta, cuerpo, content_type="application/json"), esperados) for ruta, cuerpo, esperados in pruebas]
    respuestas += [(api.get(ruta), {405}) for ruta in ("/v1/activar", "/v1/renovar")]

    for respuesta, esperados in respuestas:
        assert respuesta.status_code in esperados, (respuesta.status_code, respuesta.content[:200])
        texto = respuesta.content.decode("utf-8", "replace")
        assert "Traceback" not in texto and not any(secreto in texto for secreto in secretos)
        if respuesta.status_code != 405:
            assert respuesta.json() == (RECHAZADA if respuesta.status_code == 403 else PETICION)
    bitacora = json.dumps(list(Bitacora.objects.values_list("datos", flat=True)))
    assert not any(secreto in bitacora for secreto in secretos)
    assert (Negocio.objects.count(), Instalacion.objects.count()) == (negocios, instalaciones)


def test_no_mas_instalaciones_que_las_permitidas(api, negocio, hora, activo):
    assert negocio.instalaciones_permitidas == 1
    segundo = servicios.crear_codigo(negocio)
    for equipo in (Equipo(), activo):
        respuesta = activar(api, equipo, segundo, hora.momento)
        assert respuesta.status_code == 403 and respuesta.json() == RECHAZADA
    assert Instalacion.objects.filter(negocio=negocio).count() == 1
    assert CodigoActivacion.objects.filter(negocio=negocio, usado__isnull=True).count() == 1
