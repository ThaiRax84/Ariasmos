import json
import pathlib
import secrets
import time

import pytest
from django.urls import reverse

from caja.models import Turno
from configuracion.models import PARAMETROS
from envios import middleware
from envios.models import EnvioUsado

from .conftest import cliente, configurar, nuevo_usuario

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def test_el_conteo_de_piezas_viene_encendido_de_fabrica():
    assert PARAMETROS["control_denominaciones"][0] == 1
    plantillas = sorted((RAIZ / "plantillas").glob("*.json"))
    assert len(plantillas) >= 6
    for archivo in plantillas:
        texto = archivo.read_text(encoding="utf-8")
        assert '"control_denominaciones": true' in texto, archivo.name
        assert json.loads(texto)


@pytest.fixture
def operacion(db):
    roles = configurar("escuela")
    usuario = nuevo_usuario("operacion", roles["Operación"])
    return cliente(usuario), usuario


def _en_curso(ruta):
    ficha = secrets.token_urlsafe(32)
    EnvioUsado.objects.create(ficha=ficha, ruta=ruta)
    return ficha


def test_un_envio_repetido_no_ocupa_mas_de_un_hilo_en_espera(operacion, monkeypatch):
    c, usuario = operacion
    ruta = reverse("caja:abrir")
    ficha = _en_curso(ruta)
    monkeypatch.setattr(middleware, "ESPERA_MAXIMA", 20)
    assert middleware._entrar(ficha)
    try:
        inicio = time.monotonic()
        respuesta = c.post(ruta, {middleware.CAMPO: ficha, "apertura": "cero"}, HTTP_REFERER="http://testserver" + reverse("caja:inicio"))
        assert time.monotonic() - inicio < 5
    finally:
        middleware._salir(ficha)
    assert respuesta.status_code == 302
    assert respuesta["Location"] == "http://testserver" + reverse("caja:inicio")
    assert not Turno.objects.filter(usuario=usuario).exists()
    assert middleware._esperando == {}


def test_las_esperas_totales_tienen_tope(operacion, monkeypatch):
    c, usuario = operacion
    ruta = reverse("caja:abrir")
    monkeypatch.setattr(middleware, "ESPERA_MAXIMA", 20)
    ocupadas = [secrets.token_urlsafe(32) for _ in range(middleware.ESPERAS_TOTALES)]
    for valor in ocupadas:
        assert middleware._entrar(valor)
    try:
        assert not middleware._entrar(secrets.token_urlsafe(32))
        ficha = _en_curso(ruta)
        inicio = time.monotonic()
        respuesta = c.post(ruta, {middleware.CAMPO: ficha, "apertura": "cero"})
        assert time.monotonic() - inicio < 5
    finally:
        for valor in ocupadas:
            middleware._salir(valor)
    assert respuesta.status_code == 302
    assert respuesta["Location"] == "/"
    assert not Turno.objects.filter(usuario=usuario).exists()
    assert middleware._esperando == {}


def test_la_espera_termina_y_nunca_regresa_a_una_ruta_de_envio(operacion, monkeypatch):
    c, usuario = operacion
    ruta = reverse("caja:abrir")
    ficha = _en_curso(ruta)
    monkeypatch.setattr(middleware, "ESPERA_MAXIMA", 0.3)
    respuesta = c.post(ruta, {middleware.CAMPO: ficha, "apertura": "cero"}, HTTP_REFERER="http://otro.ejemplo/")
    assert respuesta.status_code == 302
    assert respuesta["Location"] == "/"
    assert middleware._esperando == {}
    assert not Turno.objects.filter(usuario=usuario).exists()
