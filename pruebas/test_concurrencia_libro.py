import threading
from datetime import date

import pytest
from django.db import connection

from caja.models import Arqueo, Caja, Traslado
from caja.servicios import ErrorCaja, cerrar_turno, confirmar_entrega
from cobros import generacion, libro
from cobros.models import Aplicacion, Cargo, Pago, Recibo
from cuentas.models import Usuario

from .conftest import configurar, nuevo_usuario
from .libro_ayudas import preparar_conceptos, titular_activo, turno_de, verificar_sumas


def en_hilos(funcion, argumentos):
    errores, resultados = [], []
    barrera = threading.Barrier(len(argumentos))

    def trabajo(arg):
        try:
            barrera.wait()
            resultados.append(funcion(arg))
        except Exception as error:
            errores.append(error)
        finally:
            connection.close()

    hilos = [threading.Thread(target=trabajo, args=(a,)) for a in argumentos]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    return resultados, errores


@pytest.fixture
def base(transactional_db):
    roles = configurar("escuela")
    preparar_conceptos()
    sup = nuevo_usuario("supervision", roles["Supervisión"])
    cajeros = [nuevo_usuario(f"cajero{i}", roles["Operación"]) for i in range(6)]
    ana = titular_activo(cajeros[0], sup, "Ana")
    return roles, sup, cajeros, ana


def test_folios_consecutivos_con_hilos(base):
    roles, sup, cajeros, ana = base
    for i, cajero in enumerate(cajeros):
        turno_de(cajero, f"Caja {i + 1}")

    def pagar(usuario_id):
        usuario = Usuario.objects.get(pk=usuario_id)
        turno = usuario.turnos.get(estado="abierto")
        return [libro.registrar_pago(ana, 1000, Pago.EFECTIVO, usuario, turno=turno).recibo.folio for _ in range(4)]

    resultados, errores = en_hilos(pagar, [c.pk for c in cajeros])
    assert not errores, errores
    folios = sorted(Recibo.objects.filter(serie="A").values_list("folio", flat=True))
    assert folios == list(range(1, 25))
    verificar_sumas()


def test_pagos_simultaneos_sobre_el_mismo_cargo(base):
    roles, sup, cajeros, ana = base
    for i, cajero in enumerate(cajeros):
        turno_de(cajero, f"Caja {i + 1}")
    cargo = Cargo.objects.get(titular=ana)

    def pagar(usuario_id):
        usuario = Usuario.objects.get(pk=usuario_id)
        return libro.registrar_pago(ana, 30000, Pago.EFECTIVO, usuario, turno=usuario.turnos.get(estado="abierto"))

    resultados, errores = en_hilos(pagar, [c.pk for c in cajeros])
    assert not errores, errores
    assert sum(Aplicacion.objects.filter(cargo=cargo).values_list("importe", flat=True)) == 100000
    assert libro.saldo_de(cargo) == 0
    assert sum(libro.remanente_de(p) for p in Pago.objects.all()) == 6 * 30000 - 100000
    verificar_sumas()


def test_doble_confirmacion_y_doble_cierre(base):
    roles, sup, cajeros, ana = base
    turno = turno_de(cajeros[0])
    libro.registrar_pago(ana, 50000, Pago.EFECTIVO, cajeros[0], turno=turno)

    def cerrar(_):
        return cerrar_turno(turno, cajeros[0], {"50000": 1})

    resultados, errores = en_hilos(cerrar, range(4))
    assert len(resultados) == 1 and all(isinstance(e, ErrorCaja) for e in errores)
    assert Arqueo.objects.count() == 1
    entrega = Traslado.objects.create(tipo=Traslado.ENTREGA, origen=cajeros[0], destino=sup, importe=50000, estado=Traslado.PENDIENTE)

    def confirmar(_):
        return confirmar_entrega(Traslado.objects.get(pk=entrega.pk), Usuario.objects.get(pk=sup.pk), 50000)

    resultados, errores = en_hilos(confirmar, range(4))
    assert len(resultados) == 1 and all(isinstance(e, ErrorCaja) for e in errores)
    verificar_sumas()


def test_generacion_simultanea_del_mismo_periodo(base):
    roles, sup, cajeros, ana = base
    beto = titular_activo(cajeros[0], sup, "Beto")
    resultados, errores = en_hilos(lambda _: (generacion.generar_recurrentes(date(2026, 3, 5)), generacion.generar_recargos(date(2026, 3, 20))), range(4))
    assert not errores, errores
    for titular in (ana, beto):
        periodos = list(Cargo.objects.filter(titular=titular, origen=Cargo.AUTOMATICO).exclude(periodo="").values_list("periodo", flat=True))
        assert sorted(periodos) == ["2026-01", "2026-02", "2026-03"]
        assert Cargo.objects.filter(titular=titular, origen=Cargo.RECARGO).count() == 3
