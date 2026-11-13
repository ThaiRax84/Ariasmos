from datetime import date

from django.db.models import Sum

from caja.models import Caja, Traslado
from caja.servicios import abrir_turno, custodia
from cobros import libro
from cobros.models import Aplicacion, Cargo, ConceptoCobro, Pago, ReglaRecargo, ReversionPago
from configuracion.models import Negocio
from cuentas.models import Usuario
from solicitudes import motor
from titulares.models import Familia, Titular
from titulares.servicios import crear_titular

INICIO = date(2026, 1, 1)


def preparar_conceptos():
    regla = ReglaRecargo.objects.create(nombre="Recargo mensual", tipo="fijo", valor=20000, dias_gracia=0)
    ConceptoCobro.objects.filter(nombre="Inscripción").update(importe_centavos=100000)
    ConceptoCobro.objects.filter(nombre="Colegiatura").update(importe_centavos=250000, dia_vencimiento=10, regla_recargo=regla)
    ConceptoCobro.objects.filter(nombre="Libros").update(importe_centavos=50000)
    Negocio.objects.filter(pk=1).update(cobro_desde=INICIO)
    return regla


def titular_activo(capturista, aprobador, nombre, familia=None, iniciales=("Inscripción",)):
    titular = crear_titular(capturista, {"nombre": nombre, "apellidos": "Prueba", "familia": familia}, contacto={"nombre": "Resp", "valores": {}}, conceptos=list(ConceptoCobro.objects.filter(nombre__in=iniciales)))
    motor.ejecutar("alta", aprobador, titular)
    Titular.objects.filter(pk=titular.pk).update(activo_desde=INICIO)
    titular.refresh_from_db()
    return titular


def familia_con_dos(capturista, aprobador):
    familia = Familia.objects.create(nombre="Familia Prueba")
    return familia, titular_activo(capturista, aprobador, "Ana", familia), titular_activo(capturista, aprobador, "Beto", familia)


def turno_de(usuario, nombre_caja="Caja 1"):
    caja, _ = Caja.objects.get_or_create(nombre=nombre_caja)
    return abrir_turno(usuario, caja, 0)


def saldo(cargo):
    return libro.saldo_de(cargo)


def cargos_de(titular, **filtro):
    return libro.con_saldo(Cargo.objects.filter(titular=titular, **filtro)).order_by("vencimiento", "id")


def verificar_sumas():
    vigentes = Pago.objects.filter(reversion__isnull=True)
    total_pagos = vigentes.aggregate(t=Sum("importe"))["t"] or 0
    aplicado = Aplicacion.objects.filter(pago__reversion__isnull=True).aggregate(t=Sum("importe"))["t"] or 0
    a_favor = sum(p.remanente for p in libro.con_remanente(vigentes))
    assert total_pagos == aplicado + a_favor
    for cargo in libro.con_saldo(Cargo.objects.all()):
        assert 0 <= cargo.saldo <= cargo.importe_final
    cobrado = (Pago.objects.filter(medio=Pago.EFECTIVO).aggregate(t=Sum("importe"))["t"] or 0) - (ReversionPago.objects.filter(turno__isnull=False).aggregate(t=Sum("pago__importe"))["t"] or 0)
    depositado = Traslado.objects.filter(tipo=Traslado.DEPOSITO).aggregate(t=Sum("importe"))["t"] or 0
    en_custodia = sum(custodia(u) for u in Usuario.objects.all())
    assert cobrado == en_custodia + depositado
