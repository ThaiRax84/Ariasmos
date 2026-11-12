import hashlib
import json
import os

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import models
from django.urls import reverse

from auditoria import ancla
from auditoria.models import Evento, EventoInmutable, Verificacion
from auditoria.servicios import registrar, verificar_cadena
from nucleo import cadena
from titulares.servicios import crear_titular

from .conftest import cliente


@pytest.fixture
def bitacora(db, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        for i in range(6):
            registrar("prueba", datos={"i": i, "texto": "ñandú"})
    return list(Evento.objects.order_by("numero"))


def _actualizar(evento_pk, **campos):
    models.QuerySet.update(Evento.objects.filter(pk=evento_pk), **campos)


def test_numeracion_consecutiva_y_ancla(bitacora):
    assert [e.numero for e in bitacora] == [1, 2, 3, 4, 5, 6]
    resultado = verificar_cadena()
    assert resultado.valida and resultado.total == 6
    registro = ancla.leer()
    assert registro["numero"] == 6 and registro["sello"] == bitacora[-1].sello and ancla.es_autentica(registro)
    call_command("verificar_auditoria")
    assert Verificacion.objects.first().valida


def test_alteracion_detectada(bitacora):
    _actualizar(bitacora[2].pk, datos={"i": 99, "texto": "ñandú"})
    resultado = verificar_cadena()
    assert not resultado.valida and resultado.numero == 3 and resultado.motivo == "sello"
    with pytest.raises(CommandError):
        call_command("verificar_auditoria")
    assert not Verificacion.objects.first().valida


def test_alterar_y_recalcular_sin_la_clave_se_detecta(bitacora):
    _actualizar(bitacora[2].pk, datos={"i": 99})
    anterior = bitacora[1].sello
    for evento in Evento.objects.order_by("numero").filter(numero__gte=3):
        nuevo = hashlib.sha256((anterior + "|" + cadena.canonico(evento.contenido())).encode()).hexdigest()
        _actualizar(evento.pk, sello_anterior=anterior, sello=nuevo)
        anterior = nuevo
    resultado = verificar_cadena()
    assert not resultado.valida and resultado.numero == 3


def test_recalcular_con_otra_clave_se_detecta(bitacora):
    _actualizar(bitacora[2].pk, datos={"i": 99})
    otra_clave = bytes(32)
    anterior = bitacora[1].sello
    for evento in Evento.objects.order_by("numero").filter(numero__gte=3):
        nuevo = cadena.sellar(otra_clave, anterior, evento.contenido())
        _actualizar(evento.pk, sello_anterior=anterior, sello=nuevo)
        anterior = nuevo
    resultado = verificar_cadena()
    assert not resultado.valida and resultado.numero == 3


def test_borrar_el_ultimo_evento_se_detecta_por_el_ancla(bitacora):
    models.QuerySet.delete(Evento.objects.filter(pk=bitacora[-1].pk))
    resultado = verificar_cadena()
    assert not resultado.valida and resultado.motivo == "ancla_no_coincide" and resultado.numero == 6


def test_hueco_en_la_numeracion_se_detecta(bitacora):
    models.QuerySet.delete(Evento.objects.filter(pk=bitacora[2].pk))
    resultado = verificar_cadena()
    assert not resultado.valida and resultado.motivo == "hueco" and resultado.numero == 3


def test_ancla_alterada_o_ausente(bitacora, ancla_temporal):
    with open(ancla_temporal, encoding="utf-8") as archivo:
        registro = json.load(archivo)
    with open(ancla_temporal, "w", encoding="utf-8") as archivo:
        json.dump(dict(registro, numero=2), archivo)
    assert verificar_cadena().motivo == "ancla_alterada"
    os.remove(ancla_temporal)
    assert verificar_cadena().motivo == "sin_ancla"


def test_ancla_no_retrocede(bitacora):
    ancla.escribir(3, bitacora[2].sello, "x")
    assert ancla.leer()["numero"] == 6


def test_eventos_no_se_modifican_ni_borran(db):
    evento = registrar("prueba")
    evento.accion = "otra"
    with pytest.raises(EventoInmutable):
        evento.save()
    with pytest.raises(EventoInmutable):
        evento.delete()
    with pytest.raises(EventoInmutable):
        Evento.objects.all().update(accion="x")
    with pytest.raises(EventoInmutable):
        Evento.objects.all().delete()


def test_verificacion_fallida_alerta_en_inicio(personas, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        registrar("prueba")
    ultimo = Evento.objects.order_by("-numero").first()
    _actualizar(ultimo.pk, accion="alterada")
    direccion = cliente(personas["dir"])
    direccion.post(reverse("auditoria:verificar"))
    assert "La bitácora no está íntegra" in direccion.get(reverse("inicio")).content.decode()
    assert "La bitácora no está íntegra" not in cliente(personas["sup"]).get(reverse("inicio")).content.decode()


def test_eventos_guardan_equipo_y_titular(personas):
    titular = crear_titular(personas["op"], {"nombre": "A", "apellidos": "B"}, contacto={"nombre": "C", "valores": {}})
    assert Evento.objects.filter(titular=titular.pk, accion="titular_creado").exists()
    assert Evento.objects.filter(titular=titular.pk, accion="contacto_creado").exists()
    cliente(personas["op"]).get(reverse("titulares:ficha_pago", args=[titular.pk]))
    evento = Evento.objects.get(accion="ficha_pago_consultada")
    assert evento.equipo is not None and evento.titular == titular.pk
