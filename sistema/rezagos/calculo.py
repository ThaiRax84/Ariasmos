from dataclasses import dataclass, field

from django.db.models import DateField, Max, Min, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce, Greatest

from cobros import libro
from cobros.models import Cargo, Prorroga
from configuracion.models import hoy_negocio
from titulares.models import Titular

from .models import ILIMITADO, NEGOCIO, VALOR, ExcepcionLimite, LimiteAdeudo, ReglaRezago

ESTADOS = (Titular.ACTIVO, Titular.PENDIENTE)
TEXTO_LIMITE = "Rebasó el límite de adeudo"
TEXTO_NEUTRO = "Con atraso"
TEXTO_SIN_CREDITO = "Sin crédito"


@dataclass
class Situacion:
    titular_id: int
    agrupacion_id: object
    vencido: int
    dias: int
    limite_importe: object = None
    limite_dias: object = None
    rebasa_importe: bool = False
    rebasa_dias: bool = False
    excepcion: object = None
    acciones: dict = field(default_factory=dict)

    @property
    def rebasa(self):
        return self.rebasa_importe or self.rebasa_dias

    @property
    def aviso(self):
        return self.rebasa or "aviso_inicio" in self.acciones

    @property
    def sin_credito(self):
        return self.rebasa or "sin_credito" in self.acciones

    @property
    def cobranza(self):
        return "cobranza" in self.acciones

    @property
    def rezagado(self):
        return self.rebasa or bool(self.acciones)

    def reglas(self, accion, ver_dirigidas=True):
        return [r for r in self.acciones.get(accion, []) if ver_dirigidas or r.alcance != ReglaRezago.TITULAR]

    def texto_aviso(self, ver_dirigidas=True):
        reglas = self.reglas("aviso_inicio", ver_dirigidas)
        if reglas:
            return max(reglas, key=lambda r: r.gravedad).texto
        if self.rebasa:
            return TEXTO_LIMITE
        return TEXTO_NEUTRO

    def marcas(self, ver_dirigidas=True):
        textos = []
        for regla in sorted(self.reglas("marca", ver_dirigidas), key=lambda r: r.gravedad, reverse=True):
            if regla.texto not in textos:
                textos.append(regla.texto)
        if self.sin_credito and TEXTO_SIN_CREDITO not in textos:
            textos.append(TEXTO_SIN_CREDITO)
        return textos


def _prorroga():
    return Subquery(Prorroga.objects.filter(cargo=OuterRef("pk")).order_by().values("cargo").annotate(m=Max("fecha_limite")).values("m"), output_field=DateField())


def vencidos(hoy, ids=None):
    consulta = Cargo.objects.filter(vencimiento__lt=hoy, titular__interno=False, titular__estado__in=ESTADOS)
    if ids is not None:
        consulta = consulta.filter(titular_id__in=list(ids))
    consulta = libro.con_saldo(consulta).annotate(efectivo=Greatest("vencimiento", Coalesce(_prorroga(), "vencimiento"))).filter(saldo__gt=0, efectivo__lt=hoy)
    filas = consulta.order_by().values("titular_id", "titular__agrupacion_id").annotate(total=Sum("saldo"), desde=Min("efectivo"))
    return {f["titular_id"]: (f["titular__agrupacion_id"], f["total"], f["desde"]) for f in filas}


def _efectivo(modo, valor, negocio_modo, negocio_valor):
    if modo == NEGOCIO:
        modo, valor = negocio_modo, negocio_valor
    if modo == VALOR:
        return valor
    return None


def limites_de(negocio, excepcion):
    if excepcion is None:
        return _efectivo(negocio.modo_importe, negocio.importe_maximo, ILIMITADO, 0), _efectivo(negocio.modo_dias, negocio.dias_maximos, ILIMITADO, 0)
    return (
        _efectivo(excepcion.modo_importe, excepcion.importe_maximo, negocio.modo_importe, negocio.importe_maximo),
        _efectivo(excepcion.modo_dias, excepcion.dias_maximos, negocio.modo_dias, negocio.dias_maximos),
    )


def excepciones_vigentes(hoy, ids=None):
    consulta = ExcepcionLimite.objects.filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=hoy))
    if ids is not None:
        consulta = consulta.filter(titular_id__in=list(ids))
    return {e.titular_id: e for e in consulta}


def _acciones(reglas, titular_id, agrupacion_id, vencido, dias, rebasa):
    aplicables = [r for r in reglas if r.aplica_a(titular_id, agrupacion_id)]
    acciones = {}
    for accion in ReglaRezago.ACCIONES:
        con = [r for r in aplicables if getattr(r, accion)]
        if not con:
            continue
        nivel = max(r.nivel for r in con)
        cumplidas = [r for r in con if r.nivel == nivel and r.se_cumple(vencido, dias, rebasa)]
        if cumplidas:
            acciones[accion] = cumplidas
    return acciones


def evaluar(hoy=None, ids=None):
    hoy = hoy or hoy_negocio()
    deudas = vencidos(hoy, ids)
    if not deudas:
        return {}
    negocio = LimiteAdeudo.actual()
    excepciones = excepciones_vigentes(hoy, ids)
    reglas = list(ReglaRezago.objects.filter(activa=True))
    resultado = {}
    for titular_id, (agrupacion_id, vencido, desde) in deudas.items():
        dias = (hoy - desde).days
        excepcion = excepciones.get(titular_id)
        limite_importe, limite_dias = limites_de(negocio, excepcion)
        situacion = Situacion(titular_id, agrupacion_id, vencido, dias, limite_importe, limite_dias, excepcion=excepcion)
        situacion.rebasa_importe = limite_importe is not None and vencido > limite_importe
        situacion.rebasa_dias = limite_dias is not None and dias > limite_dias
        situacion.acciones = _acciones(reglas, titular_id, agrupacion_id, vencido, dias, situacion.rebasa)
        if situacion.rezagado:
            resultado[titular_id] = situacion
    return resultado


def de(titular, hoy=None):
    return evaluar(hoy, ids=[titular.pk]).get(titular.pk)


def sin_credito(titular, hoy=None):
    situacion = de(titular, hoy)
    return situacion is not None and situacion.sin_credito
