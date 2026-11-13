from dataclasses import dataclass
from datetime import date

CRITERIOS = ("recargos", "vencimiento", "prioridad")
ORDEN_POR_DEFECTO = ("recargos", "vencimiento", "prioridad")


class ErrorReparto(ValueError):
    pass


@dataclass(frozen=True)
class Pendiente:
    id: int
    titular: int
    saldo: int
    vencimiento: date
    es_recargo: bool = False
    prioridad: int = 100


@dataclass(frozen=True)
class Parte:
    cargo: int
    titular: int
    importe: int


def _llave(orden):
    for criterio in orden:
        if criterio not in CRITERIOS:
            raise ErrorReparto("criterio de orden desconocido")
    if len(set(orden)) != len(orden):
        raise ErrorReparto("criterio de orden repetido")

    def llave(pendiente):
        valores = []
        for criterio in orden:
            if criterio == "recargos":
                valores.append(0 if pendiente.es_recargo else 1)
            elif criterio == "vencimiento":
                valores.append(pendiente.vencimiento.toordinal())
            else:
                valores.append(pendiente.prioridad)
        valores.append(pendiente.id)
        return tuple(valores)

    return llave


def repartir(importe, pendientes, titular, miembros=(), orden=ORDEN_POR_DEFECTO):
    if not isinstance(importe, int) or isinstance(importe, bool) or importe <= 0:
        raise ErrorReparto("el importe debe ser un entero positivo de centavos")
    llave = _llave(tuple(orden))
    familia = set(miembros) | {titular}
    vistos = set()
    propios, ajenos = [], []
    for pendiente in pendientes:
        if pendiente.id in vistos:
            raise ErrorReparto("cargo repetido")
        vistos.add(pendiente.id)
        if not isinstance(pendiente.saldo, int) or pendiente.saldo < 0:
            raise ErrorReparto("saldo de cargo invalido")
        if pendiente.saldo == 0 or pendiente.titular not in familia:
            continue
        (propios if pendiente.titular == titular else ajenos).append(pendiente)
    partes = []
    resto = importe
    for grupo in (sorted(propios, key=llave), sorted(ajenos, key=llave)):
        for pendiente in grupo:
            if resto == 0:
                break
            aplicado = min(resto, pendiente.saldo)
            partes.append(Parte(pendiente.id, pendiente.titular, aplicado))
            resto -= aplicado
    return partes, resto
