import pytest
from django.urls import reverse

from caja.servicios import esperado_de, neto_de, turno_abierto
from cobros import libro
from cobros.models import CancelacionCargo, Pago, ReversionPago
from inventario import servicios as inventario
from inventario.models import Devolucion, Venta
from solicitudes import motor
from solicitudes.models import Solicitud

from .conftest import cliente
from .libro_ayudas import turno_de
from .test_inventario import base, cobrar_venta, fijar


def credito_de(titular):
    return sum(p.remanente for p in libro.con_remanente(Pago.objects.filter(titular=titular, reversion__isnull=True)))


def test_devolver_un_cargo_condonado_no_regresa_dinero(base):
    personas, ana, libro_a, cuaderno = base
    venta = inventario.vender(ana, [(cuaderno.pk, 2)], Venta.ADEUDO, personas["op"])
    renglon = venta.renglones.get()
    libro.cancelar_cargo(renglon.cargo, 10000, CancelacionCargo.CANCELACION, "condonado", personas["sup"], personas["sup"], None, None)
    devolucion = inventario.devolver(venta, {str(renglon.pk): [2, True]}, Devolucion.SALDO, personas["op"], "ya no lo quiso")
    assert devolucion.importe_dinero == 0
    assert credito_de(ana) == 0


def test_devolver_un_cargo_pagado_con_descuento_regresa_solo_lo_pagado(base):
    personas, ana, libro_a, cuaderno = base
    turno_de(personas["sup"], "Caja 2")
    venta = inventario.vender(ana, [(cuaderno.pk, 2)], Venta.AHORA, personas["sup"])
    renglon = venta.renglones.get()
    libro.cancelar_cargo(renglon.cargo, 2000, CancelacionCargo.CANCELACION, "descuento", personas["dir"], personas["dir"], None, None)
    cobrar_venta(cliente(personas["sup"]), ana, venta, 8000)
    assert libro.saldo_de(renglon.cargo) == 0
    primera = inventario.devolver(venta, {str(renglon.pk): [1, True]}, Devolucion.SALDO, personas["op"], "uno")
    segunda = inventario.devolver(venta, {str(renglon.pk): [1, True]}, Devolucion.SALDO, personas["op"], "otro")
    assert primera.importe_dinero + segunda.importe_dinero == 8000
    assert sum(p.importe for p in Pago.objects.filter(titular=ana, medio=Pago.DEVOLUCION)) == 8000


def test_venta_publico_devuelta_en_efectivo_no_se_cobra_otra_vez_al_revertir_el_pago(base):
    personas, ana, libro_a, cuaderno = base
    turno_op = turno_de(personas["op"])
    libro.registrar_pago(ana, 100000, Pago.EFECTIVO, personas["op"], turno=turno_op)
    venta = inventario.vender_publico([(cuaderno.pk, 2)], personas["op"], turno_abierto(personas["op"]), "f" * 20)
    renglon = venta.renglones.get()
    antes = neto_de(turno_op)
    resultado = inventario.solicitar_efectivo(venta, {str(renglon.pk): [2, True]}, personas["op"], "no lo quiso")
    motor.aprobar(resultado.solicitud, personas["dir"])
    assert neto_de(turno_op) == antes - 10000
    with pytest.raises(Exception):
        libro.revertir_pago(venta.pago, "otra vez", personas["sup"], turno=turno_op, autorizador=personas["dir"])
    assert not ReversionPago.objects.filter(pago=venta.pago).exists()
    assert neto_de(turno_op) == antes - 10000


def test_venta_a_titular_devuelta_en_efectivo_no_deja_revertir_el_pago_completo(base):
    personas, ana, libro_a, cuaderno = base
    turno_op = turno_de(personas["op"])
    turno_sup = turno_de(personas["sup"], "Caja 2")
    venta = inventario.vender(ana, [(cuaderno.pk, 2)], Venta.AHORA, personas["sup"])
    cobrar_venta(cliente(personas["sup"]), ana, venta, 10000)
    libro.registrar_pago(ana, 50000, Pago.EFECTIVO, personas["op"], turno=turno_op)
    renglon = venta.renglones.get()
    resultado = inventario.solicitar_efectivo(venta, {str(renglon.pk): [2, True]}, personas["op"], "no lo quiso")
    motor.aprobar(resultado.solicitud, personas["dir"])
    venta.refresh_from_db()
    with pytest.raises(Exception):
        libro.revertir_pago(venta.pago, "otra vez", personas["dir"], turno=turno_sup, autorizador=personas["dir"])
    assert not ReversionPago.objects.filter(pago=venta.pago).exists()
