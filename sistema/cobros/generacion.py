from datetime import date

from django.db.models import Max, Q, Sum

from configuracion.models import Negocio, hoy_negocio, parametro
from nucleo import recargos
from titulares.models import Titular

from . import libro
from .models import Beca, Cargo, ConceptoCobro, PlanCobro, Prorroga

MESES_POR_PERIODO = {"mensual": 1, "bimestral": 2, "trimestral": 3, "semestral": 6, "anual": 12}


def meses(desde, hasta, salto):
    anio, mes = desde.year, desde.month
    while (anio, mes) <= (hasta.year, hasta.month):
        if (mes - 1) % salto == 0:
            yield anio, mes
        mes += 1
        if mes > 12:
            anio, mes = anio + 1, 1


def beca_vigente(titular_id, concepto_id, fecha):
    return (
        Beca.objects.filter(titular_id=titular_id, concepto_id=concepto_id, vigente_desde__lte=fecha)
        .filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=fecha))
        .order_by("-vigente_desde", "-id")
        .first()
    )


def plan_vigente(titular_id, concepto_id, fecha):
    return (
        PlanCobro.objects.filter(titular_id=titular_id, concepto_id=concepto_id, activo=True, vigente_desde__lte=fecha)
        .filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=fecha))
        .order_by("-vigente_desde", "-id")
        .first()
    )


def importe_con_beca(titular_id, concepto, importe, fecha):
    beca = beca_vigente(titular_id, concepto.pk, fecha)
    if beca is None:
        return importe, 0, None
    final, descuento = recargos.importe_con_beca(importe, recargos.PORCENTAJE, beca.puntos_base)
    return final, descuento, beca


def _titulares_de(concepto):
    activos = Titular.objects.filter(estado=Titular.ACTIVO)
    if concepto.aplica_a == ConceptoCobro.TODOS:
        return activos
    con_plan = activos.filter(planes__concepto=concepto, planes__activo=True)
    if concepto.aplica_a == ConceptoCobro.AGRUPACION and concepto.agrupacion_id:
        return activos.filter(Q(agrupacion_id=concepto.agrupacion_id) | Q(pk__in=con_plan.values("pk"))).distinct()
    return con_plan.distinct()


def generar_recurrentes(hoy=None, request=None):
    hoy = hoy or hoy_negocio()
    negocio = Negocio.actual()
    inicio = (negocio.cobro_desde if negocio and negocio.cobro_desde else hoy).replace(day=1)
    dia = min(max(parametro("dia_generacion_cargos"), 1), 28)
    creados = 0
    for concepto in ConceptoCobro.objects.filter(tipo=ConceptoCobro.RECURRENTE, activo=True, periodicidad__in=MESES_POR_PERIODO):
        salto = MESES_POR_PERIODO[concepto.periodicidad]
        for titular in _titulares_de(concepto):
            desde = max(inicio, (titular.activo_desde or hoy).replace(day=1))
            hechos = set(Cargo.objects.filter(titular=titular, concepto=concepto, origen=Cargo.AUTOMATICO).values_list("periodo", flat=True))
            for anio, mes in meses(desde, hoy, salto):
                periodo = f"{anio:04d}-{mes:02d}"
                if periodo in hechos:
                    continue
                fecha = recargos.fecha_en_mes(anio, mes, dia)
                if fecha > hoy:
                    continue
                plan = plan_vigente(titular.pk, concepto.pk, fecha)
                if concepto.aplica_a not in (ConceptoCobro.TODOS, ConceptoCobro.AGRUPACION) and plan is None:
                    continue
                base = plan.importe_centavos if plan is not None and plan.importe_centavos is not None else concepto.importe_centavos
                final, descuento, beca = importe_con_beca(titular.pk, concepto, base, fecha)
                vencimiento = recargos.fecha_en_mes(anio, mes, concepto.dia_vencimiento or dia)
                cargo = libro.crear_cargo(titular, concepto, base, vencimiento, Cargo.AUTOMATICO, periodo=periodo, descripcion=concepto.nombre, beca=beca, descuento=descuento, request=request)
                if cargo is not None:
                    creados += 1
    return creados


def generar_recargos(hoy=None, request=None):
    hoy = hoy or hoy_negocio()
    creados = 0
    base = libro.con_saldo(
        Cargo.objects.filter(origen__in=[Cargo.AUTOMATICO, Cargo.MANUAL, Cargo.SALDO_INICIAL], concepto__regla_recargo__activa=True, vencimiento__lt=hoy).select_related("concepto__regla_recargo", "titular")
    ).filter(saldo__gt=0)
    for cargo in base:
        regla = cargo.concepto.regla_recargo
        existentes = cargo.recargos.all()
        ya = list(existentes.values_list("fecha_recargo", flat=True))
        acumulado = existentes.aggregate(total=Sum("importe_final"))["total"] or 0
        prorroga = Prorroga.objects.filter(cargo=cargo).aggregate(limite=Max("fecha_limite"))["limite"]
        nuevos = recargos.recargos_pendientes(
            regla.tipo, regla.valor, cargo.saldo, cargo.vencimiento, hoy, ya_generadas=ya, acumulado=acumulado,
            dias_gracia=regla.dias_gracia, se_repite=regla.se_repite, tope=regla.tope_centavos, prorroga_hasta=prorroga,
        )
        for fecha, importe in nuevos:
            recargo = libro.crear_cargo(
                cargo.titular, cargo.concepto, importe, fecha, Cargo.RECARGO, periodo=cargo.periodo,
                descripcion=f"Recargo de {cargo}", cargo_base=cargo, fecha_recargo=fecha, request=request,
            )
            if recargo is not None:
                creados += 1
    return creados


def cargos_de_alta(titular, hoy=None, request=None):
    hoy = hoy or hoy_negocio()
    creados = []
    for concepto in titular.conceptos_iniciales.filter(activo=True).exclude(tipo=ConceptoCobro.RECURRENTE):
        cargo = libro.crear_cargo(titular, concepto, concepto.importe_centavos, hoy, Cargo.AUTOMATICO, descripcion=concepto.nombre, request=request)
        if cargo is not None:
            creados.append(cargo)
    return creados


def primer_dia(fecha):
    return date(fecha.year, fecha.month, 1)
