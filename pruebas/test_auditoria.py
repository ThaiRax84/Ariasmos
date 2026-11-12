import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import models

from auditoria.models import Evento, EventoInmutable
from auditoria.servicios import registrar, verificar_cadena


def test_cadena_integra_y_detecta_alteracion(db):
    for i in range(6):
        registrar("prueba", datos={"i": i, "texto": "ñandú"})
    assert verificar_cadena() == (True, None, 6)
    call_command("verificar_auditoria")
    tercero = Evento.objects.order_by("id")[2]
    models.QuerySet.update(Evento.objects.filter(pk=tercero.pk), datos={"i": 99, "texto": "ñandú"})
    valida, evento_id, antes = verificar_cadena()
    assert not valida and evento_id == tercero.pk and antes == 2
    with pytest.raises(CommandError):
        call_command("verificar_auditoria")


def test_detecta_borrado_intermedio(db):
    for i in range(4):
        registrar("prueba", datos={"i": i})
    segundo = Evento.objects.order_by("id")[1]
    models.QuerySet.delete(Evento.objects.filter(pk=segundo.pk))
    assert verificar_cadena()[0] is False


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
