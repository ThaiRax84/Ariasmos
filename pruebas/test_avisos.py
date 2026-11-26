from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse

from auditoria.models import Evento
from cobros import libro
from cobros.models import ConceptoCobro, Pago
from configuracion import trabajador
from licencias import servicios as licencias
from mensajes import avisos
from mensajes.models import Aviso, Envio, PlantillaMensaje
from titulares.models import Agrupacion, CampoContacto, Contacto
from titulares.servicios import crear_titular

from .conftest import cliente
from .libro_ayudas import preparar_conceptos
from .test_mensajes import CentralFalso


def _lunes_a_las_diez():
    dia = date.today()
    while dia.weekday() == 6:
        dia -= timedelta(days=1)
    return datetime.combine(dia, time(10), ZoneInfo("America/Mexico_City")), dia


def _titular(personas, nombre, telefono):
    campo = CampoContacto.objects.filter(tipo=CampoContacto.TELEFONO).first()
    titular = crear_titular(
        personas["dir"],
        {"nombre": nombre, "apellidos": "Prueba"},
        contacto={"nombre": "Rosa", "valores": {str(campo.pk): telefono}},
    )
    Contacto.objects.filter(titular=titular).update(acepta_whatsapp=True)
    return titular


def _debe(titular, vencimiento, importe=100000):
    return libro.crear_cargo(
        titular,
        ConceptoCobro.objects.get(nombre="Libros"),
        importe,
        vencimiento,
        "manual",
    )


@pytest.fixture
def escenario(personas, monkeypatch):
    preparar_conceptos()
    ahora, hoy = _lunes_a_las_diez()
    PlantillaMensaje.objects.update(estado="aprobada")
    aviso = Aviso.objects.get(momento="atraso", dias=5)
    aviso.activo = True
    aviso.save()
    return aviso, ahora, hoy, personas, CentralFalso(monkeypatch)


def test_el_atraso_sale_una_sola_vez_con_los_datos_de_su_cargo(escenario):
    aviso, ahora, hoy, personas, central = escenario
    ana = _titular(personas, "Ana", "5512345678")
    cargo = _debe(ana, hoy - timedelta(days=6))
    _debe(_titular(personas, "Beto", "5587654321"), hoy - timedelta(days=30))
    assert avisos.ejecutar(ahora) == 1
    assert avisos.ejecutar(ahora) == 0
    ((accion, datos, adjunto),) = central.llamadas
    assert datos["clave_envio"] == f"aviso-{aviso.pk}-{cargo.pk}" and adjunto is None
    assert datos["destino"] == "+525512345678"
    assert datos["valores"] == {
        "nombre": "Rosa",
        "concepto": "Libros",
        "dias": "6",
        "adeudo": "$1,000.00 MXN",
    }
    assert Evento.objects.filter(accion="avisos_enviados").count() == 1


def test_no_sale_sin_permiso_de_la_persona_fuera_de_horario_ni_en_otra_agrupacion(
    escenario,
):
    aviso, ahora, hoy, personas, central = escenario
    ana = _titular(personas, "Ana", "5512345678")
    _debe(ana, hoy - timedelta(days=6))
    fuera = ahora.replace(hour=20)
    assert avisos.ejecutar(fuera) == 0 and not central.llamadas
    aviso.agrupaciones.add(Agrupacion.objects.create(nombre="Otra"))
    assert avisos.ejecutar(ahora) == 0 and not central.llamadas
    aviso.agrupaciones.clear()
    Contacto.objects.filter(titular=ana).update(acepta_whatsapp=False)
    assert avisos.ejecutar(ahora) == 0 and not Envio.objects.exists()


def test_el_tope_detiene_el_ciclo_y_lo_incierto_se_reintenta_con_la_misma_clave(
    escenario,
):
    aviso, ahora, hoy, personas, central = escenario
    for nombre, telefono in (("Ana", "5512345678"), ("Beto", "5587654321")):
        _debe(_titular(personas, nombre, telefono), hoy - timedelta(days=6))
    central.respuestas["mensajes_enviar"] = {"resultado": "tope"}
    assert avisos.ejecutar(ahora) == 0 and len(central.llamadas) == 1
    claves = set(Envio.objects.values_list("clave_envio", flat=True))
    central.respuestas.clear()
    avisos.ejecutar(ahora)
    assert Envio.objects.get(clave_envio=central.llamadas[-1][1]["clave_envio"]).estado == "incierto"
    central.respuestas["mensajes_enviar"] = {"resultado": "aceptado", "id": "6f1c1c1e-2f6c-4a3b-9a55-0d2f4d8f7a10"}
    assert avisos.ejecutar(ahora) == 2
    assert claves <= {llamada[1]["clave_envio"] for llamada in central.llamadas}
    assert Envio.objects.count() == 2


def test_el_recibo_automatico_solo_sale_para_pagos_nuevos(escenario):
    aviso, ahora, hoy, personas, central = escenario
    ana = _titular(personas, "Ana", "5512345678")
    cargo = _debe(ana, hoy)
    viejo = libro.registrar_pago(ana, 10000, Pago.BANCO, personas["op"]).recibo
    pago = Aviso.objects.get(momento="pago")
    pago.activo, pago.activado = True, None
    pago.save()
    nuevo = libro.registrar_pago(ana, 20000, Pago.BANCO, personas["op"]).recibo
    assert cargo and avisos.ejecutar(ahora) == 1
    assert avisos.ejecutar(ahora) == 0
    ((_, datos, adjunto),) = central.llamadas
    assert datos["clave_envio"] == f"recibo-{nuevo.pk}-1" and adjunto
    assert Envio.objects.get().aviso == pago and not Envio.objects.filter(recibo=viejo)


def test_las_pantallas_guardan_limites_niegan_plantillas_sin_aprobar_y_la_tarea_pide_licencia(
    escenario, monkeypatch
):
    aviso, ahora, hoy, personas, central = escenario
    web = cliente(personas["dir"])
    pantalla = web.get(reverse("mensajes:avisos")).content.decode()
    assert "A los 5 días de atraso" in pantalla and "0 de 0" in pantalla
    web.post(
        reverse("mensajes:avisos"),
        {"accion": "limites", "inicio": "08:00", "fin": "17:30", "maximo": "3", "dias_sin_envio": ["5", "6"]},
    )
    assert avisos.horario() == (time(8, 0), time(17, 30))
    PlantillaMensaje.objects.filter(clave="atraso").update(estado="borrador")
    web.post(reverse("mensajes:aviso", args=[aviso.pk]), {"accion": "desactivar"})
    web.post(reverse("mensajes:aviso", args=[aviso.pk]), {"accion": "activar"})
    aviso.refresh_from_db()
    assert not aviso.activo
    monkeypatch.setattr(licencias, "permite_escribir", lambda: False)
    informe = {n: texto for n, _, texto in trabajador.ejecutar_ciclo()}
    assert "solo consulta" in informe["avisos"]


def test_lo_permanente_no_se_repite_y_lo_nuevo_va_antes_que_los_reintentos(escenario):
    aviso, ahora, hoy, personas, central = escenario
    for nombre, telefono in (("Ana", "5512345678"), ("Beto", "5587654321")):
        _debe(_titular(personas, nombre, telefono), hoy - timedelta(days=6))
    central.respuestas["mensajes_enviar"] = {"resultado": "destino"}
    assert avisos.ejecutar(ahora) == 0
    assert set(Envio.objects.values_list("estado", flat=True)) == {"fallido"}
    llamadas = len(central.llamadas)
    avisos.ejecutar(ahora)
    assert len(central.llamadas) == llamadas
    Envio.objects.update(estado="no_enviado")
    _debe(_titular(personas, "Caro", "5511112222"), hoy - timedelta(days=6))
    central.llamadas.clear()
    avisos.ejecutar(ahora)
    assert central.llamadas[0][1]["destino"] == "+525511112222"


def test_el_recibo_sin_destinatario_valido_no_ocupa_lugar(escenario, monkeypatch):
    aviso, ahora, hoy, personas, central = escenario
    pago = Aviso.objects.get(momento="pago")
    pago.activo = True
    pago.save()
    sin_permiso = _titular(personas, "Sin", "5512345678")
    Contacto.objects.filter(titular=sin_permiso).update(acepta_whatsapp=False)
    con_permiso = _titular(personas, "Con", "5587654321")
    _debe(sin_permiso, hoy)
    _debe(con_permiso, hoy)
    monkeypatch.setattr(avisos, "MAXIMO_POR_CICLO", 1)
    libro.registrar_pago(sin_permiso, 10000, Pago.BANCO, personas["op"])
    libro.registrar_pago(con_permiso, 10000, Pago.BANCO, personas["op"])
    assert avisos.ejecutar(ahora) == 1


def test_borrar_y_recrear_no_salta_el_maximo_y_lo_enviado_no_se_borra(escenario):
    aviso, ahora, hoy, personas, central = escenario
    ana = _titular(personas, "Ana", "5512345678")
    _debe(ana, hoy - timedelta(days=6))
    avisos.ejecutar(ahora)
    envio = Envio.objects.get()
    assert envio.momento == "atraso"
    web = cliente(personas["dir"])
    web.post(reverse("mensajes:aviso", args=[aviso.pk]), {"accion": "borrar"})
    assert Aviso.objects.filter(pk=aviso.pk).exists()
    copia = Aviso.objects.create(
        momento="atraso", dias=4, plantilla=aviso.plantilla, activo=True
    )
    Envio.objects.filter(pk=envio.pk).update(aviso=None)
    _debe(ana, hoy - timedelta(days=5))
    Envio.objects.create(
        clave_envio="x", plantilla=aviso.plantilla, contacto=envio.contacto,
        titular=ana, momento="antes", destino_final="5678", estado="enviado",
    )
    assert copia.pk and avisos.ejecutar(ahora) == 0


def test_un_reintento_con_el_aviso_cambiado_falla_sin_mandarse(escenario):
    aviso, ahora, hoy, personas, central = escenario
    _debe(_titular(personas, "Ana", "5512345678"), hoy - timedelta(days=6))
    central.respuestas.clear()
    avisos.ejecutar(ahora)
    assert Envio.objects.get().estado == "incierto"
    otra = PlantillaMensaje.objects.get(clave="sin_acceso")
    Aviso.objects.filter(pk=aviso.pk).update(plantilla=otra)
    central.llamadas.clear()
    avisos.ejecutar(ahora)
    envio = Envio.objects.get()
    assert envio.estado == "fallido" and "cambió" in envio.motivo and not central.llamadas
