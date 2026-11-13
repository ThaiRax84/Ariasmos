import random
from datetime import date

from banco.models import Banco, CuentaBancaria
from caja import servicios as caja
from cobros import generacion, libro
from cobros.models import CancelacionCargo, Cargo, Pago

from .libro_ayudas import familia_con_dos, preparar_conceptos, titular_activo, turno_de, verificar_sumas


def test_sumas_globales_con_operaciones_al_azar(personas):
    preparar_conceptos()
    familia, ana, beto = familia_con_dos(personas["op"], personas["sup"])
    carla = titular_activo(personas["op"], personas["sup"], "Carla")
    titulares = [ana, beto, carla]
    cuenta = CuentaBancaria.objects.create(banco=Banco.objects.get(clave="002"), clabe="002010077777777771", beneficiario="B", principal=True)
    azar = random.Random(20261112)
    cajeros = [personas["op"], personas["op2"]]
    turnos = {c.pk: turno_de(c, f"Caja {c.pk}") for c in cajeros}
    for mes in range(1, 7):
        generacion.generar_recurrentes(date(2026, mes, 5))
        generacion.generar_recargos(date(2026, mes, 20))
        for _ in range(6):
            cajero = azar.choice(cajeros)
            libro.registrar_pago(azar.choice(titulares), azar.randint(1, 400000), Pago.EFECTIVO, cajero, turno=turnos[cajero.pk])
            verificar_sumas()
        vivos = list(Pago.objects.filter(reversion__isnull=True))
        pago = azar.choice(vivos)
        libro.revertir_pago(pago, "azar", personas["sup"], turno=turnos[pago.turno.usuario_id] if turnos[pago.turno.usuario_id].abierto else None)
        verificar_sumas()
        con_saldo = list(libro.con_saldo(Cargo.objects.all()).filter(saldo__gt=0))
        if con_saldo:
            cargo = azar.choice(con_saldo)
            tipo = CancelacionCargo.CONDONACION if cargo.origen == Cargo.RECARGO else CancelacionCargo.CANCELACION
            libro.cancelar_cargo(cargo, azar.randint(1, cargo.saldo), tipo, "azar", personas["sup"])
            verificar_sumas()
        for cajero in cajeros:
            turno = turnos[cajero.pk]
            caja.cerrar_turno(turno, cajero, {}, nota="conteo de prueba")
            libre = caja.disponible_para_trasladar(cajero)
            if libre > 0:
                caja.entregar(cajero, personas["sup"], libre // 2)
                pendiente = cajero.traslados_enviados.filter(estado="pendiente").latest("id")
                caja.confirmar_entrega(pendiente, personas["sup"], pendiente.importe)
                resto = caja.disponible_para_trasladar(cajero)
                if resto > 0:
                    caja.depositar(cajero, resto, cuenta, date(2026, mes, 25), f"D{mes}{cajero.pk}")
            verificar_sumas()
            turnos[cajero.pk] = turno_de(cajero, f"Caja {cajero.pk}")
    assert caja.custodia(personas["op"]) == 0 and caja.custodia(personas["op2"]) == 0
    assert Pago.objects.count() == 36
