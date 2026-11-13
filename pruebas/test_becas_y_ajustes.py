from datetime import date

import pytest
from django.urls import reverse

from auditoria.models import Evento
from caja.servicios import custodia
from cobros import generacion, libro
from cobros.models import Beca, CancelacionCargo, Cargo, ConceptoCobro, Pago, Prorroga, ReversionPago
from cuentas.models import Delegacion
from solicitudes import motor
from solicitudes.models import Solicitud

from .conftest import cliente, codigo_actual
from .libro_ayudas import cargos_de, preparar_conceptos, titular_activo, turno_de, verificar_sumas


@pytest.fixture
def base(personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana", iniciales=())
    return personas, ana, ConceptoCobro.objects.get(nombre="Colegiatura")


def pedir_beca(c, titular, concepto, porcentaje, **extra):
    datos = {"concepto": concepto.pk, "porcentaje": porcentaje, "desde": "2026-01-01", "motivo": "Apoyo"}
    datos.update(extra)
    return c.post(reverse("cobros:beca", args=[titular.pk]), datos)


@pytest.mark.parametrize("porcentaje,descuento", [("25", 62500), ("12.5", 31250), ("100", 250000)])
def test_beca_en_porcentaje_sobre_el_cargo_mensual(base, porcentaje, descuento):
    personas, ana, colegiatura = base
    assert pedir_beca(cliente(personas["sup"]), ana, colegiatura, porcentaje).status_code == 302
    beca = Beca.objects.get()
    assert beca.autorizada_por == personas["sup"]
    generacion.generar_recurrentes(date(2026, 1, 5))
    cargo = cargos_de(ana).get(periodo="2026-01")
    assert (cargo.importe_original, cargo.descuento, cargo.importe_final, cargo.beca_id) == (250000, descuento, 250000 - descuento, beca.pk)
    if porcentaje == "100":
        assert cargo.saldo == 0 and libro.estado_de(cargo) == "pagado"
        assert generacion.generar_recargos(date(2026, 3, 1)) == 0


@pytest.mark.parametrize("porcentaje", ["0", "101", "-5", "abc", "12.345", "100.01"])
def test_beca_rechaza_porcentajes_invalidos(base, porcentaje):
    personas, ana, colegiatura = base
    respuesta = pedir_beca(cliente(personas["sup"]), ana, colegiatura, porcentaje)
    assert respuesta.status_code == 200 and not Beca.objects.exists()


@pytest.mark.parametrize("campo", ["tipo", "importe", "importe_fijo", "valor", "puntos_base"])
def test_beca_rechaza_importe_fijo(base, campo):
    personas, ana, colegiatura = base
    respuesta = pedir_beca(cliente(personas["sup"]), ana, colegiatura, "25", **{campo: "fijo" if campo == "tipo" else "50000"})
    assert respuesta.status_code == 400 and not Beca.objects.exists()
    assert Evento.objects.filter(accion="beca_rechazada").exists()
    with pytest.raises(motor.ErrorSolicitud):
        motor.ejecutar("beca", personas["sup"], ana, {"concepto": colegiatura.pk, "puntos_base": 2500, "desde": "2026-01-01", "motivo": "x", "tipo": "fijo"})
    with pytest.raises(motor.ErrorSolicitud):
        motor.ejecutar("beca", personas["sup"], ana, {"concepto": colegiatura.pk, "puntos_base": 0, "desde": "2026-01-01", "motivo": "x"})


def test_beca_por_las_tres_vias_y_autoaprobacion(base):
    personas, ana, colegiatura = base
    op = cliente(personas["op"])
    respuesta = pedir_beca(op, ana, colegiatura, "10", hasta="2026-01-31")
    solicitud = Solicitud.objects.get(accion="beca")
    assert respuesta.url == reverse("solicitudes:detalle", args=[solicitud.pk])
    assert "10.00 %" in cliente(personas["sup"]).get(respuesta.url).content.decode()
    cliente(personas["sup"]).post(reverse("solicitudes:aprobar", args=[solicitud.pk]))
    assert Beca.objects.get().creada_por == personas["op"]
    pedir_beca(op, ana, colegiatura, "20", desde="2026-02-01", hasta="2026-02-28")
    segunda = Solicitud.objects.filter(accion="beca", estado=Solicitud.PENDIENTE).get()
    op.post(reverse("solicitudes:codigo", args=[segunda.pk]), {"autorizador": personas["sup"].pk, "codigo": codigo_actual(personas["sup"])})
    segunda.refresh_from_db()
    assert segunda.estado == Solicitud.APROBADA and Beca.objects.count() == 2
    Delegacion.objects.create(otorgante=personas["sup"], receptor=personas["op2"], permiso="aprobar_solicitudes", usos_maximos=2)
    pedir_beca(op, ana, colegiatura, "30", desde="2026-03-01", hasta="2026-12-31")
    tercera = Solicitud.objects.filter(accion="beca", estado=Solicitud.PENDIENTE).get()
    cliente(personas["op2"]).post(reverse("solicitudes:aprobar", args=[tercera.pk]))
    tercera.refresh_from_db()
    assert tercera.via == Solicitud.DELEGACION and Beca.objects.count() == 3
    Delegacion.objects.create(otorgante=personas["sup"], receptor=personas["op"], permiso="aprobar_solicitudes", usos_maximos=2)
    pedir_beca(op, ana, ConceptoCobro.objects.get(nombre="Colegiatura"), "40", desde="2027-01-01")
    propia = Solicitud.objects.filter(accion="beca", estado=Solicitud.PENDIENTE).get()
    op.post(reverse("solicitudes:aprobar", args=[propia.pk]))
    propia.refresh_from_db()
    assert propia.estado == Solicitud.PENDIENTE and Beca.objects.count() == 3


def test_beca_no_cambia_cargos_ya_generados_y_no_se_traslapa(base):
    personas, ana, colegiatura = base
    generacion.generar_recurrentes(date(2026, 1, 5))
    pedir_beca(cliente(personas["sup"]), ana, colegiatura, "50", desde="2026-01-01")
    generacion.generar_recurrentes(date(2026, 2, 5))
    assert cargos_de(ana).get(periodo="2026-01").importe_final == 250000
    assert cargos_de(ana).get(periodo="2026-02").importe_final == 125000
    respuesta = pedir_beca(cliente(personas["sup"]), ana, colegiatura, "10", desde="2026-06-01")
    assert Beca.objects.count() == 1 and respuesta.status_code == 200


def test_prorroga_mueve_el_recargo_por_las_vias(base):
    personas, ana, colegiatura = base
    generacion.generar_recurrentes(date(2026, 1, 5))
    cargo = cargos_de(ana).get(periodo="2026-01")
    op = cliente(personas["op"])
    op.post(reverse("cobros:prorroga", args=[cargo.pk]), {"fecha_limite": "2026-01-25", "motivo": "Acuerdo"})
    solicitud = Solicitud.objects.get(accion="prorroga")
    op.post(reverse("solicitudes:codigo", args=[solicitud.pk]), {"autorizador": personas["sup"].pk, "codigo": codigo_actual(personas["sup"])})
    assert Prorroga.objects.get().fecha_limite == date(2026, 1, 25)
    assert generacion.generar_recargos(date(2026, 1, 11)) == 0
    assert generacion.generar_recargos(date(2026, 1, 25)) == 0
    assert generacion.generar_recargos(date(2026, 1, 26)) == 1
    respuesta = cliente(personas["sup"]).post(reverse("cobros:prorroga", args=[cargo.pk]), {"fecha_limite": "2026-01-20", "motivo": "Otra"})
    assert respuesta.status_code == 200 and Prorroga.objects.count() == 1


def test_cancelar_condonar_y_revertir(base):
    personas, ana, colegiatura = base
    generacion.generar_recurrentes(date(2026, 1, 5))
    generacion.generar_recargos(date(2026, 1, 11))
    cargo = cargos_de(ana).get(periodo="2026-01", origen=Cargo.AUTOMATICO)
    recargo = cargos_de(ana).get(origen=Cargo.RECARGO)
    sup = cliente(personas["sup"])
    assert sup.post(reverse("cobros:cancelar", args=[cargo.pk]), {"importe": "500", "motivo": "Ajuste"}).status_code == 302
    assert libro.saldo_de(cargo) == 200000
    assert sup.post(reverse("cobros:cancelar", args=[cargo.pk]), {"importe": "999999", "motivo": "Ajuste"}).status_code == 200
    sup.post(reverse("cobros:cancelar", args=[recargo.pk]), {"importe": "200", "motivo": "Condonado"})
    assert CancelacionCargo.objects.get(cargo=recargo).tipo == CancelacionCargo.CONDONACION
    assert libro.estado_de(cargos_de(ana).get(pk=recargo.pk)) == "cancelado"
    with pytest.raises(motor.ErrorSolicitud):
        motor.ejecutar("condonar_recargo", personas["sup"], ana, {"cargo": cargo.pk, "importe": 100, "motivo": "x"})
    turno = turno_de(personas["op"])
    pago = libro.registrar_pago(ana, 150000, Pago.EFECTIVO, personas["op"], turno=turno)
    assert libro.saldo_de(cargo) == 50000
    sin_turno = sup.post(reverse("cobros:revertir", args=[pago.pk]), {"motivo": "Error de captura"}, follow=True)
    assert "turno de caja abierto" in sin_turno.content.decode() and not ReversionPago.objects.exists()
    cliente(personas["op"]).post(reverse("cobros:revertir", args=[pago.pk]), {"motivo": "Error de captura"})
    solicitud = Solicitud.objects.get(accion="revertir_pago")
    sup.post(reverse("solicitudes:aprobar", args=[solicitud.pk]))
    reversion = ReversionPago.objects.get()
    assert reversion.turno == turno and reversion.ejecutada_por == personas["sup"] and reversion.autorizada_por == personas["sup"]
    assert libro.saldo_de(cargo) == 200000
    recibo = sup.get(reverse("cobros:recibo", args=[pago.recibo.pk])).content.decode()
    assert "CANCELADO" in recibo
    assert custodia(personas["op"]) == 0
    assert "Recibo A-1 cancelado" in sup.get(reverse("inicio")).content.decode()
    verificar_sumas()
    assert Evento.objects.filter(accion="pago_revertido", titular=ana.pk).exists()
