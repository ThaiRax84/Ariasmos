import importlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.apps import apps as registro
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Evento
from caja import servicios as caja
from caja.models import Turno
from cobros import libro
from cobros.models import Pago
from configuracion.formularios import FormularioCajaCortes
from configuracion.models import Parametro
from cortes import calendario
from cortes import servicios as cortes
from cortes.models import DIARIO, Corte

from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo, turno_de

ZONA = ZoneInfo("America/Mexico_City")
MIGRACION = importlib.import_module("configuracion.migrations.0012_calendario_y_carpeta_banco")


def guardar(horario):
    Parametro.objects.update_or_create(clave="calendario_corte", defaults={"valor": calendario.a_texto(horario)})


def momento(texto):
    return datetime.fromisoformat(texto).replace(tzinfo=ZONA)


def test_validacion_del_calendario():
    assert calendario.validar({"0": "18:00", "5": "14:30"}) == {"0": "18:00", "5": "14:30"}
    for malo in ({"7": "18:00"}, {"0": "24:00"}, {"0": "18:60"}, {"0": "8:00"}, {"0": 1800}, {0: "18:00"}, ["18:00"], {"0": "18:00:00"}):
        with pytest.raises(calendario.CalendarioInvalido):
            calendario.validar(malo)
    with pytest.raises(calendario.CalendarioInvalido):
        calendario.desde_texto("{no es json")


def test_limite_en_dia_con_corte_y_en_dia_sin_corte():
    horario = {"0": "18:00", "1": "18:00", "2": "18:00", "3": "18:00", "4": "18:00", "5": "14:00"}
    assert calendario.limite(momento("2026-11-11T09:00"), horario) == momento("2026-11-11T18:00")
    assert calendario.limite(momento("2026-11-14T09:00"), horario) == momento("2026-11-14T14:00")
    assert calendario.limite(momento("2026-11-15T10:00"), horario) == momento("2026-11-16T18:00")
    assert calendario.limite(momento("2026-11-15T10:00"), {"2": "12:00"}) == momento("2026-11-18T12:00")
    assert calendario.limite(momento("2026-11-15T10:00"), {}) is None


@pytest.mark.django_db
def test_parametro_vacio_o_danado_usa_todos_los_dias_a_las_18():
    assert calendario.actual() == calendario.todos_los_dias("18:00")
    Parametro.objects.create(clave="calendario_corte", valor="no es json")
    assert calendario.actual() == calendario.todos_los_dias("18:00")


@pytest.mark.django_db
def test_migracion_copia_la_hora_anterior_a_los_siete_dias():
    Parametro.objects.create(clave="hora_limite_corte_diario", valor="19:15")
    MIGRACION.a_calendario(registro, None)
    assert calendario.actual() == calendario.todos_los_dias("19:15")
    assert not Parametro.objects.filter(clave="hora_limite_corte_diario").exists()
    MIGRACION.a_hora(registro, None)
    assert Parametro.objects.get(clave="hora_limite_corte_diario").valor == "19:15"


@pytest.mark.django_db
def test_migracion_con_hora_danada_usa_las_18():
    Parametro.objects.create(clave="hora_limite_corte_diario", valor="25:99")
    MIGRACION.a_calendario(registro, None)
    assert calendario.actual() == calendario.todos_los_dias("18:00")


def _turno_con_cobro(personas, abierto):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 10000, Pago.EFECTIVO, personas["op"], turno=turno)
    Turno.objects.filter(pk=turno.pk).update(abierto_en=abierto)
    return turno


def test_turno_abierto_en_dia_sin_corte_vence_el_siguiente_dia_con_corte(personas):
    domingo = momento("2026-11-15T10:00")
    guardar({"0": "18:00"})
    _turno_con_cobro(personas, domingo)
    assert cortes.diarios_pendientes(momento("2026-11-15T20:00")) == []
    assert cortes.diarios_pendientes(momento("2026-11-16T17:59")) == []
    pendientes = cortes.diarios_pendientes(momento("2026-11-16T18:00"))
    assert [p["persona"] for p in pendientes] == [personas["op"]] and pendientes[0]["limite"] == momento("2026-11-16T18:00")


def test_sin_dias_con_corte_no_hay_alerta_ni_tardio(personas):
    guardar({})
    turno = _turno_con_cobro(personas, timezone.now() - timedelta(days=3))
    assert cortes.diarios_pendientes() == []
    caja.cerrar_turno(turno, personas["op"], {"100000": 1}, "conteo")
    assert not Corte.objects.get(tipo=DIARIO).tardio


def test_tardio_segun_el_dia_en_que_se_abrio(personas):
    ahora = timezone.localtime(timezone.now(), ZONA)
    ayer = ahora - timedelta(days=1)
    guardar({str(ayer.weekday()): "23:59", str(ahora.weekday()): "23:59"})
    turno = _turno_con_cobro(personas, ayer.replace(hour=0, minute=1))
    caja.cerrar_turno(turno, personas["op"], {"100000": 1}, "conteo")
    assert Corte.objects.get(tipo=DIARIO).tardio


def test_a_tiempo_si_cierra_antes_del_limite(personas):
    ahora = timezone.localtime(timezone.now(), ZONA)
    guardar({str(d): "23:59" for d in range(7)})
    turno = _turno_con_cobro(personas, ahora.replace(hour=0, minute=0, second=1))
    if ahora.hour == 23 and ahora.minute >= 59:
        pytest.skip("justo en el límite")
    caja.cerrar_turno(turno, personas["op"], {"100000": 1}, "conteo")
    assert not Corte.objects.get(tipo=DIARIO).tardio


def test_formulario_valida_horas_y_exige_un_dia_si_hay_cajas(personas):
    base = {"periodo_retiros": "dia", "tope_retiro_individual": "0", "tope_retiros_periodo": "0", "maximo_retiros_periodo": "0", "maximo_efectivo_caja": "0", "dias_retiro_sin_revisar": "3"}
    malo = FormularioCajaCortes({**base, "corte_0": "25:00"})
    assert not malo.is_valid() and "corte_0" in malo.errors
    vacio = FormularioCajaCortes(base)
    assert not vacio.is_valid() and "al menos un día" in str(vacio.errors)
    bueno = FormularioCajaCortes({**base, "corte_2": "17:30"})
    assert bueno.is_valid() and bueno.valores()["calendario_corte"] == {"2": "17:30"}


def test_configuracion_guarda_el_calendario_con_bitacora(personas):
    c = cliente(personas["dir"])
    pagina = c.get(reverse("configuracion:caja")).content.decode()
    assert 'data-acepta="hora"' in pagina and 'data-acepta="dinero"' in pagina and "MXN" in pagina
    datos = {"corte_0": "18:00", "corte_1": "18:00", "corte_5": "13:00", "periodo_retiros": "dia", "tope_retiro_individual": "$1,000.00", "tope_retiros_periodo": "3000", "maximo_retiros_periodo": "4", "maximo_efectivo_caja": "0", "dias_retiro_sin_revisar": "2"}
    assert c.post(reverse("configuracion:caja"), datos).url == reverse("configuracion:indice")
    assert calendario.actual() == {"0": "18:00", "1": "18:00", "5": "13:00"}
    evento = Evento.objects.filter(accion="calendario_corte_cambiado").get()
    anterior, nuevo = evento.datos["cambios"]["calendario_corte"]
    assert anterior == calendario.PROPUESTO and nuevo == {"0": "18:00", "1": "18:00", "5": "13:00"}
    assert cliente(personas["sup"]).get(reverse("configuracion:caja")).status_code == 403
    parametros = c.get(reverse("configuracion:parametros")).content.decode()
    assert 'name="calendario_corte"' not in parametros and 'name="tope_retiro_individual"' not in parametros
