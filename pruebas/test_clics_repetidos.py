import secrets
import threading

import pytest
from django.db import connection
from django.test import Client
from django.urls import reverse

from caja.models import Arqueo, Caja, MotivoRetiro, RetiroCaja, Turno
from caja.servicios import abrir_turno
from cobros import libro
from cobros.models import ConceptoCobro, Pago
from configuracion.models import Parametro
from envios.middleware import CAMPO
from inventario import servicios as inventario
from inventario.models import Articulo, Conteo, Venta
from solicitudes import motor
from solicitudes.models import Solicitud

from .conftest import cliente, configurar, nuevo_usuario
from .libro_ayudas import preparar_conceptos, titular_activo

HILOS = 10


def ficha():
    return secrets.token_urlsafe(32)


def al_mismo_tiempo(base, ruta, datos):
    barrera = threading.Barrier(HILOS)
    estados, errores = [], []

    def enviar():
        c = Client()
        c.cookies = base.cookies
        try:
            barrera.wait()
            respuesta = c.post(ruta, datos, follow=True)
            estados.append(respuesta.status_code)
        except Exception as error:
            errores.append(repr(error))
        finally:
            connection.close()

    hilos = [threading.Thread(target=enviar) for _ in range(HILOS)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert not errores, errores
    assert len(estados) == HILOS
    assert all(estado < 400 for estado in estados), estados
    return estados


@pytest.fixture
def escenario(transactional_db):
    roles = configurar("escuela")
    op = nuevo_usuario("operacion", roles["Operación"])
    sup = nuevo_usuario("supervision", roles["Supervisión"])
    preparar_conceptos()
    ana = titular_activo(op, sup, "Ana")
    return {"op": op, "sup": sup, "ana": ana, "caja": Caja.objects.get_or_create(nombre="Caja 1")[0]}


def _turno_con_efectivo(escenario):
    turno = abrir_turno(escenario["op"], escenario["caja"], 0, piezas={"100000": 2})
    libro.registrar_pago(escenario["ana"], 50000, Pago.EFECTIVO, escenario["op"], turno=turno, piezas={"recibidas": {"50000": 1}, "cambio": {}})
    return turno


def test_abrir_turno_con_diez_clics(escenario):
    datos = {CAMPO: ficha(), "caja": escenario["caja"].pk, "apertura": "efectivo", "f_100000": "1", "f_5000": "2"}
    al_mismo_tiempo(cliente(escenario["op"]), reverse("caja:abrir"), datos)
    assert Turno.objects.count() == 1
    assert Turno.objects.get().fondo_inicial == 110000


def test_cobrar_con_diez_clics(escenario):
    abrir_turno(escenario["op"], escenario["caja"], 0, piezas={"10000": 5})
    datos = {CAMPO: ficha(), "paso": "confirmar", "ficha": secrets.token_urlsafe(24), "importe": "50000", "r_100000": "1", "c_50000": "1"}
    al_mismo_tiempo(cliente(escenario["op"]), reverse("cobros:cobrar", args=[escenario["ana"].pk]), datos)
    assert Pago.objects.count() == 1


def test_cobrar_con_fichas_distintas_no_duplica_el_pago(escenario):
    abrir_turno(escenario["op"], escenario["caja"], 0, piezas={"10000": 5})
    pago = secrets.token_urlsafe(24)
    base = cliente(escenario["op"])
    barrera = threading.Barrier(HILOS)
    estados = []

    def enviar():
        c = Client()
        c.cookies = base.cookies
        try:
            barrera.wait()
            estados.append(c.post(reverse("cobros:cobrar", args=[escenario["ana"].pk]), {CAMPO: ficha(), "paso": "confirmar", "ficha": pago, "importe": "50000", "r_50000": "1"}).status_code)
        finally:
            connection.close()

    hilos = [threading.Thread(target=enviar) for _ in range(HILOS)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert len(estados) == HILOS and all(e < 500 for e in estados), estados
    assert Pago.objects.count() == 1


def test_vender_con_diez_clics(escenario):
    Parametro.objects.update_or_create(clave="modulo_inventario", defaults={"valor": "1"})
    libros = ConceptoCobro.objects.get(nombre="Libros")
    cuaderno = Articulo.objects.create(clave="CUA-1", nombre="Cuaderno", precio=5000, concepto=libros)
    conteo = inventario.subir_conteo({cuaderno.pk: 20}, escenario["op"], Conteo.PANTALLA)
    motor.aprobar(conteo.solicitud, escenario["sup"])
    abrir_turno(escenario["op"], escenario["caja"], 0, piezas={"1000": 5})
    datos = {CAMPO: ficha(), "paso": "confirmar", "ficha": secrets.token_urlsafe(24), f"cantidad_{cuaderno.pk}": "2", "r_20000": "1", "c_10000": "1"}
    al_mismo_tiempo(cliente(escenario["op"]), reverse("inventario:vender_publico"), datos)
    assert Venta.objects.count() == 1
    assert inventario.existencias()[cuaderno.pk] == 18


def test_retirar_con_diez_clics(escenario):
    for clave, valor in (("tope_retiro_individual", 100000), ("tope_retiros_periodo", 300000), ("maximo_retiros_periodo", 5)):
        Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})
    _turno_con_efectivo(escenario)
    motivo = MotivoRetiro.objects.filter(activo=True).first()
    datos = {CAMPO: ficha(), "importe": "100", "motivo": motivo.pk, "nota": "", "p_10000": "1"}
    al_mismo_tiempo(cliente(escenario["op"]), reverse("caja:retiro_nuevo"), datos)
    assert RetiroCaja.objects.count() == 1


def test_cerrar_turno_con_diez_clics(escenario):
    turno = _turno_con_efectivo(escenario)
    datos = {CAMPO: ficha(), "d_100000": "2", "d_50000": "1", "nota": ""}
    al_mismo_tiempo(cliente(escenario["op"]), reverse("caja:cerrar", args=[turno.pk]), datos)
    assert Arqueo.objects.count() == 1
    assert Turno.objects.get(pk=turno.pk).estado == Turno.CERRADO


def test_aprobar_solicitud_con_diez_clics(escenario):
    for clave, valor in (("tope_retiro_individual", 1000), ("tope_retiros_periodo", 300000), ("maximo_retiros_periodo", 5)):
        Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})
    _turno_con_efectivo(escenario)
    from caja import retiros

    resultado = retiros.registrar_retiro(escenario["op"], 10000, MotivoRetiro.objects.filter(activo=True).first(), "", {"10000": 1})
    solicitud = resultado.solicitud
    assert solicitud is not None
    al_mismo_tiempo(cliente(escenario["sup"]), reverse("solicitudes:aprobar", args=[solicitud.pk]), {CAMPO: ficha()})
    assert Solicitud.objects.get(pk=solicitud.pk).estado == Solicitud.APROBADA
    assert RetiroCaja.objects.count() == 1


def test_aprobar_solicitud_sin_ficha_tampoco_falla(escenario):
    for clave, valor in (("tope_retiro_individual", 1000), ("tope_retiros_periodo", 300000), ("maximo_retiros_periodo", 5)):
        Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})
    _turno_con_efectivo(escenario)
    from caja import retiros

    solicitud = retiros.registrar_retiro(escenario["op"], 10000, MotivoRetiro.objects.filter(activo=True).first(), "", {"10000": 1}).solicitud
    al_mismo_tiempo(cliente(escenario["sup"]), reverse("solicitudes:aprobar", args=[solicitud.pk]), {})
    assert RetiroCaja.objects.count() == 1


def test_abrir_turno_sin_ficha_abre_uno_solo(escenario):
    al_mismo_tiempo(cliente(escenario["op"]), reverse("caja:abrir"), {"caja": escenario["caja"].pk, "apertura": "cero"})
    assert Turno.objects.count() == 1
