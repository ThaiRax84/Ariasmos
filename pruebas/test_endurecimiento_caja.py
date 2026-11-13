from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from banco.models import Banco, CuentaBancaria
from caja import servicios as caja
from caja.models import Traslado
from cobros import libro
from cobros.models import Pago, ReversionPago
from solicitudes import motor
from solicitudes.models import Solicitud

from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo, turno_de, verificar_sumas


@pytest.fixture
def base(personas):
    cache.clear()
    preparar_conceptos()
    return personas, titular_activo(personas["op"], personas["sup"], "Ana")


def cobrar(usuario, titular, importe):
    turno = caja.turno_abierto(usuario) or turno_de(usuario)
    return libro.registrar_pago(titular, importe, Pago.EFECTIVO, usuario, turno=turno, ficha=None)


def test_nadie_revierte_solo_un_pago_que_el_mismo_cobro(base):
    personas, ana = base
    pago = cobrar(personas["sup"], ana, 50000)
    cliente(personas["sup"]).post(reverse("cobros:revertir", args=[pago.pk]), {"motivo": "error de captura"})
    assert not ReversionPago.objects.exists()
    solicitud = Solicitud.objects.get(accion="revertir_pago")
    assert solicitud.estado == Solicitud.PENDIENTE and solicitud.solicitante == personas["sup"]
    with pytest.raises(motor.ErrorSolicitud):
        motor.aprobar(solicitud, personas["sup"])
    motor.aprobar(solicitud, personas["sup2"])
    assert ReversionPago.objects.filter(pago=pago).exists()
    verificar_sumas()


def test_supervision_si_revierte_directo_un_pago_que_cobro_otra_persona(base):
    personas, ana = base
    pago = cobrar(personas["op"], ana, 50000)
    turno_de(personas["sup"], "Caja 2")
    cobrar(personas["sup"], ana, 80000)
    cliente(personas["sup"]).post(reverse("cobros:revertir", args=[pago.pk]), {"motivo": "devolución"})
    assert ReversionPago.objects.filter(pago=pago).exists()
    assert caja.custodia(personas["sup"]) == 30000
    verificar_sumas()


def test_no_se_devuelve_efectivo_que_el_turno_no_tiene(base):
    personas, ana = base
    op, sup = personas["op"], personas["sup"]
    turno = turno_de(op)
    pago = cobrar(op, ana, 100000)
    caja.cerrar_turno(turno, op, {"100000": 1})
    entrega = caja.entregar(op, sup, 100000)
    caja.confirmar_entrega(entrega, sup, 100000)
    turno_de(op)
    cliente(op).post(reverse("cobros:revertir", args=[pago.pk]), {"motivo": "devolución"})
    solicitud = Solicitud.objects.filter(accion="revertir_pago").first()
    if solicitud is not None and solicitud.estado == Solicitud.PENDIENTE:
        with pytest.raises(motor.ErrorSolicitud):
            motor.aprobar(solicitud, sup)
    assert not ReversionPago.objects.exists()
    assert caja.custodia(op) >= 0
    assert caja.esperado_de(caja.turno_abierto(op)) >= 0
    verificar_sumas()


def test_depositos_por_conciliar_quedan_a_la_vista_y_alertan(base):
    personas, ana = base
    op = personas["op"]
    turno = turno_de(op)
    cobrar(op, ana, 100000)
    caja.cerrar_turno(turno, op, {"100000": 1})
    cuenta = CuentaBancaria.objects.first() or CuentaBancaria.objects.create(
        banco=Banco.objects.get(clave="002"), clabe="002010077777777771", beneficiario="Negocio", contacto_dudas="5512345678", principal=True
    )
    cliente(op).post(reverse("caja:deposito"), {"cuenta": cuenta.pk, "importe": "1000.00", "fecha": "2026-11-12", "referencia": "FOLIO-778899"})
    deposito = Traslado.objects.get(tipo=Traslado.DEPOSITO)
    pagina = cliente(personas["sup"]).get(reverse("caja:custodia")).content.decode()
    assert "FOLIO-778899" in pagina and "por conciliar" in pagina.lower()
    assert list(caja.alertas()["depositos_sin_conciliar"]) == []
    Traslado.objects.filter(pk=deposito.pk).update(creado=timezone.now() - timedelta(days=30))
    assert [t.pk for t in caja.alertas()["depositos_sin_conciliar"]] == [deposito.pk]
    inicio = cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    assert "FOLIO-778899" in inicio or "sin conciliar" in inicio.lower()
