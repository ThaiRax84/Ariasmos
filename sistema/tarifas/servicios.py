from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace

from django.db import transaction

from auditoria.servicios import diferencias, registrar
from cobros.models import ConceptoCobro
from configuracion.models import vocabulario

from . import periodos
from .models import CANTIDAD_TOPE, OpcionConcepto, OrigenCargo, TarifaAgrupacion

CANTIDAD_DE_SIEMPRE = 1000


def opciones_de(concepto):
    opcion = OpcionConcepto.objects.filter(concepto=concepto).first()
    return opcion if opcion is not None else OpcionConcepto(concepto=concepto)


def tarifa_de(concepto, agrupacion_id):
    if not agrupacion_id:
        return None
    return TarifaAgrupacion.objects.filter(concepto=concepto, agrupacion_id=agrupacion_id, activa=True).first()


def precio(concepto, titular):
    tarifa = tarifa_de(concepto, titular.agrupacion_id)
    return tarifa.importe_centavos if tarifa is not None else concepto.importe_centavos


def sin_tarifa_obligatoria(concepto, titular):
    return opciones_de(concepto).solo_con_tarifa and tarifa_de(concepto, titular.agrupacion_id) is None


def cantidad_maxima(concepto):
    opcion = opciones_de(concepto)
    if opcion.pk is None and concepto.tipo == ConceptoCobro.POR_EVENTO:
        return CANTIDAD_DE_SIEMPRE
    return opcion.cantidad_maxima if opcion.por_cantidad else 1


def error_cantidad(concepto, cantidad):
    if type(cantidad) is not int:
        return "La cantidad debe ser un número entero."
    maximo = cantidad_maxima(concepto)
    if maximo == 1 and cantidad != 1:
        return f"{concepto} no se cobra por cantidad: la cantidad es 1."
    if not 1 <= cantidad <= maximo:
        return f"La cantidad de {concepto} va de 1 a {maximo}."
    return None


def error_cargo(concepto, titular, cantidad):
    if sin_tarifa_obligatoria(concepto, titular):
        return f"{concepto} solo se cobra con tarifa de su {vocabulario()['agrupacion_min']} y {titular} no tiene una activa."
    return error_cantidad(concepto, cantidad)


@dataclass
class Vigente:
    tarifa: object
    importe: int
    periodicidad: str
    dia_vencimiento: object

    @property
    def regla(self):
        return SimpleNamespace(periodicidad=self.periodicidad, dia_vencimiento=self.dia_vencimiento)


class DelConcepto:
    def __init__(self, concepto):
        self.concepto = concepto
        self.opcion = opciones_de(concepto)
        self.tarifas = {t.agrupacion_id: t for t in TarifaAgrupacion.objects.filter(concepto=concepto, activa=True)}
        self.ultimos = {}
        for titular_id, periodicidad, fin in OrigenCargo.objects.filter(cargo__concepto=concepto).order_by("fin", "id").values_list("cargo__titular_id", "periodicidad", "fin"):
            self.ultimos[titular_id] = (periodicidad, fin)

    def para(self, titular):
        tarifa = self.tarifas.get(titular.agrupacion_id)
        if tarifa is None:
            if self.opcion.solo_con_tarifa:
                return None
            return Vigente(None, self.concepto.importe_centavos, self.concepto.periodicidad, self.concepto.dia_vencimiento)
        return Vigente(tarifa, tarifa.importe_centavos, tarifa.periodicidad or self.concepto.periodicidad, tarifa.dia_vencimiento or self.concepto.dia_vencimiento)

    def _ultimo(self, titular, hechos):
        if titular.pk in self.ultimos:
            return self.ultimos[titular.pk]
        finales = [l[1] for l in (periodos.limites(self.concepto.periodicidad, p) for p in hechos) if l is not None]
        return (self.concepto.periodicidad, max(finales)) if finales else None

    def desde(self, titular, vigente, hechos):
        ultimo = self._ultimo(titular, hechos)
        if ultimo is None or ultimo[0] == vigente.periodicidad:
            return None
        return ultimo[1] + timedelta(days=1)

    def admite(self, vigente, periodo, frontera):
        if frontera is None:
            return True
        limites = periodos.limites(vigente.periodicidad, periodo)
        return limites is None or limites[0] >= frontera

    def anotar(self, cargo, vigente, periodo):
        limites = periodos.limites(vigente.periodicidad, periodo) or (cargo.vencimiento, cargo.vencimiento)
        OrigenCargo.objects.create(cargo=cargo, tarifa=vigente.tarifa, periodicidad=vigente.periodicidad, inicio=limites[0], fin=limites[1])
        self.ultimos[cargo.titular_id] = (vigente.periodicidad, limites[1])


def periodicidad_de(cargo):
    origen = OrigenCargo.objects.filter(cargo=cargo).values_list("periodicidad", flat=True).first()
    return origen or cargo.concepto.periodicidad


def _foto_tarifa(tarifa):
    return {"importe": tarifa.importe_centavos, "periodicidad": tarifa.periodicidad, "dia_vencimiento": tarifa.dia_vencimiento, "activa": tarifa.activa}


def guardar_tarifa(tarifa, datos, usuario, request=None):
    antes = _foto_tarifa(tarifa) if tarifa.pk else {}
    with transaction.atomic():
        for campo in ("importe_centavos", "periodicidad", "dia_vencimiento", "activa"):
            setattr(tarifa, campo, datos[campo])
        if not tarifa.pk:
            tarifa.agrupacion = datos["agrupacion"]
        if tarifa.concepto.tipo != ConceptoCobro.RECURRENTE:
            tarifa.periodicidad = ""
        nueva = tarifa.pk is None
        tarifa.save()
        registrar(
            "tarifa_creada" if nueva else "tarifa_cambiada",
            usuario=usuario,
            objeto=tarifa,
            datos={"concepto": str(tarifa.concepto), "agrupacion": str(tarifa.agrupacion), "antes": antes, "despues": _foto_tarifa(tarifa), "cambios": diferencias(antes, _foto_tarifa(tarifa))},
            request=request,
        )
    return tarifa


def _foto_opcion(opcion):
    return {"por_cantidad": opcion.por_cantidad, "cantidad_maxima": opcion.cantidad_maxima, "solo_con_tarifa": opcion.solo_con_tarifa}


def guardar_opciones(concepto, datos, usuario, request=None):
    with transaction.atomic():
        opcion = opciones_de(concepto)
        antes = _foto_opcion(opcion) if opcion.pk else {}
        opcion.por_cantidad = bool(datos["por_cantidad"])
        opcion.cantidad_maxima = datos["cantidad_maxima"] if opcion.por_cantidad else 1
        opcion.solo_con_tarifa = bool(datos["solo_con_tarifa"])
        opcion.save()
        cambios = diferencias(antes, _foto_opcion(opcion))
        if cambios:
            registrar("opciones_concepto_cambiadas", usuario=usuario, objeto=concepto, datos={"concepto": str(concepto), "antes": antes, "despues": _foto_opcion(opcion), "cambios": cambios}, request=request)
    return opcion


def cargar_de_plantilla(datos):
    for definicion in datos.get("conceptos", []):
        concepto = ConceptoCobro.objects.filter(nombre=definicion["nombre"]).first()
        if concepto is None or OpcionConcepto.objects.filter(concepto=concepto).exists():
            continue
        if not (definicion.get("por_cantidad") or definicion.get("solo_con_tarifa")):
            continue
        OpcionConcepto.objects.create(
            concepto=concepto,
            por_cantidad=bool(definicion.get("por_cantidad")),
            cantidad_maxima=definicion.get("cantidad_maxima", 1) if definicion.get("por_cantidad") else 1,
            solo_con_tarifa=bool(definicion.get("solo_con_tarifa")),
        )


def exportar_concepto(concepto):
    opcion = opciones_de(concepto)
    if opcion.pk is None:
        return {}
    salida = {}
    if opcion.por_cantidad:
        salida.update({"por_cantidad": True, "cantidad_maxima": min(opcion.cantidad_maxima, CANTIDAD_TOPE)})
    if opcion.solo_con_tarifa:
        salida["solo_con_tarifa"] = True
    return salida


def descripcion_cargo(concepto, cantidad):
    return f"{concepto} × {cantidad}" if cantidad > 1 else str(concepto)
