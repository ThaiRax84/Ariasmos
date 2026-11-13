from datetime import date

import pytest

from cobros import generacion, libro
from cobros.models import Aplicacion, AsientoInmutable, Cargo, Pago

from .libro_ayudas import cargos_de, familia_con_dos, preparar_conceptos, saldo, turno_de, verificar_sumas


@pytest.fixture
def escenario(personas):
    preparar_conceptos()
    familia, ana, beto = familia_con_dos(personas["op"], personas["sup"])
    return personas, familia, ana, beto


def test_flujo_completo_del_libro(escenario):
    personas, familia, ana, beto = escenario
    inscripcion = cargos_de(ana).get(concepto__nombre="Inscripción")
    assert inscripcion.saldo == 100000 and inscripcion.origen == Cargo.AUTOMATICO
    assert generacion.generar_recurrentes(date(2026, 1, 5)) == 2
    assert generacion.generar_recurrentes(date(2026, 1, 5)) == 0
    colegiatura_ana = cargos_de(ana).get(concepto__nombre="Colegiatura", periodo="2026-01")
    assert colegiatura_ana.vencimiento == date(2026, 1, 10)
    assert generacion.generar_recargos(date(2026, 1, 10)) == 0
    assert generacion.generar_recargos(date(2026, 1, 11)) == 2
    assert generacion.generar_recargos(date(2026, 1, 20)) == 0
    recargo_ana = cargos_de(ana).get(origen=Cargo.RECARGO)
    assert recargo_ana.importe_final == 20000 and recargo_ana.cargo_base_id == colegiatura_ana.pk and recargo_ana.fecha_recargo == date(2026, 1, 11)
    turno = turno_de(personas["op"])
    pago = libro.registrar_pago(ana, 150000, Pago.EFECTIVO, personas["op"], turno=turno)
    assert saldo(recargo_ana) == 0
    assert saldo(colegiatura_ana) == 250000 - 130000
    assert pago.recibo.folio == 1
    verificar_sumas()
    adeudo_ana = sum(c.saldo for c in cargos_de(ana))
    libro.registrar_pago(ana, adeudo_ana + 50000, Pago.EFECTIVO, personas["op"], turno=turno)
    assert sum(c.saldo for c in cargos_de(ana)) == 0
    recargo_beto = cargos_de(beto).get(origen=Cargo.RECARGO)
    assert saldo(recargo_beto) == 0
    assert sum(c.saldo for c in cargos_de(beto)) == 100000 + 250000 + 20000 - 50000
    verificar_sumas()
    deuda_familia = sum(c.saldo for c in cargos_de(beto))
    sobrante = libro.registrar_pago(beto, deuda_familia + 30000, Pago.EFECTIVO, personas["op"], turno=turno)
    assert libro.remanente_de(sobrante) == 30000
    generacion.generar_recurrentes(date(2026, 2, 1))
    febrero_ana = cargos_de(ana).get(periodo="2026-02", origen=Cargo.AUTOMATICO)
    assert febrero_ana.saldo == 250000 - 30000
    assert Aplicacion.objects.filter(pago=sobrante, cargo=febrero_ana, importe=30000).exists()
    assert libro.remanente_de(sobrante) == 0
    verificar_sumas()
    assert libro.estado_de(cargos_de(ana).get(pk=colegiatura_ana.pk)) == "pagado"
    assert libro.estado_de(febrero_ana) == "parcial"


def test_asientos_no_se_modifican(escenario):
    personas, familia, ana, beto = escenario
    cargo = Cargo.objects.filter(titular=ana).first()
    cargo.importe_original = 1
    with pytest.raises(AsientoInmutable):
        cargo.save()
    with pytest.raises(AsientoInmutable):
        Cargo.objects.filter(pk=cargo.pk).update(importe_original=1)
    with pytest.raises(AsientoInmutable):
        Cargo.objects.all().delete()
    with pytest.raises(AsientoInmutable):
        cargo.delete()


def test_importes_invalidos(escenario):
    personas, familia, ana, beto = escenario
    turno = turno_de(personas["op"])
    for malo in (0, -5, 1.5, "100", True):
        with pytest.raises(libro.ErrorLibro):
            libro.registrar_pago(ana, malo, Pago.EFECTIVO, personas["op"], turno=turno)
    with pytest.raises(libro.ErrorLibro):
        libro.registrar_pago(ana, 100, Pago.EFECTIVO, personas["op"], turno=None)
