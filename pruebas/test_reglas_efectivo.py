import pytest
from django.urls import reverse

from caja import servicios as caja
from cobros import libro
from cobros.models import Pago, PlanCobro, ReversionPago
from solicitudes import motor
from solicitudes.models import Solicitud

from .conftest import cliente, codigo_actual
from .libro_ayudas import preparar_conceptos, titular_activo, turno_de


@pytest.fixture
def base(personas):
    preparar_conceptos()
    return personas, titular_activo(personas["op"], personas["sup"], "Ana")


def test_mensaje_dice_quien_tiene_el_efectivo(base):
    personas, ana = base
    op, sup = personas["op"], personas["sup"]
    turno = turno_de(op)
    pago = libro.registrar_pago(ana, 100000, Pago.EFECTIVO, op, turno=turno)
    caja.cerrar_turno(turno, op, {"100000": 1})
    caja.confirmar_entrega(caja.entregar(op, sup, 100000), sup, 100000)
    turno_de(personas["sup2"], "Caja 2")
    with pytest.raises(motor.ErrorSolicitud) as error:
        motor.ejecutar("revertir_pago", personas["sup2"], ana, {"pago": pago.pk, "motivo": "x"})
    assert str(sup) in str(error.value) and "$1,000.00" in str(error.value)
    assert not ReversionPago.objects.exists()


def test_quien_cobro_no_autoriza_por_codigo_su_reversion(base):
    personas, ana = base
    turno = turno_de(personas["sup"])
    pago = libro.registrar_pago(ana, 50000, Pago.EFECTIVO, personas["sup"], turno=turno)
    turno_de(personas["op"], "Caja 2")
    cliente(personas["op"]).post(reverse("cobros:revertir", args=[pago.pk]), {"motivo": "error"})
    solicitud = Solicitud.objects.get(accion="revertir_pago")
    with pytest.raises(motor.ErrorSolicitud):
        motor.autorizar_con_codigo(solicitud, personas["op"], personas["sup"], codigo_actual(personas["sup"]))
    assert not ReversionPago.objects.exists()


def test_el_plan_ya_no_captura_descuento(base):
    personas, ana = base
    pagina = cliente(personas["sup"]).get(reverse("cobros:plan_nuevo")).content.decode()
    assert "descuento" not in pagina.lower()
    assert not hasattr(PlanCobro, "descuento_centesimas")
