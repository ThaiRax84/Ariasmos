from configuracion.models import parametro

SIGUIENTE_PERIODO = "siguiente_periodo"
DESDE_ALTA = "desde_alta"
OPCIONES = [
    (SIGUIENTE_PERIODO, "Hasta el siguiente periodo: no se cobran recargos de lo que vence en el periodo del alta"),
    (DESDE_ALTA, "Desde el alta: lo que vence se atrasa como cualquier otro cargo"),
]
ORIGENES_EXENTOS = ("automatico", "manual")


def modo():
    valor = parametro("recargos_tras_alta")
    return valor if valor in (SIGUIENTE_PERIODO, DESDE_ALTA) else SIGUIENTE_PERIODO


def exento(cargo, periodicidad):
    from tarifas import periodos

    alta = cargo.titular.activo_desde
    if alta is None or cargo.origen not in ORIGENES_EXENTOS:
        return False
    inicio, fin = periodos.periodo_de(periodicidad or "mensual", alta)
    return inicio <= cargo.vencimiento <= fin


def evaluador():
    if modo() != SIGUIENTE_PERIODO:
        return lambda cargo: False

    def evaluar(cargo):
        from tarifas.servicios import periodicidad_de

        alta = cargo.titular.activo_desde
        if alta is None or cargo.origen not in ORIGENES_EXENTOS or abs((cargo.vencimiento - alta).days) > 366:
            return False
        periodicidad = periodicidad_de(cargo) if cargo.concepto.tipo == "recurrente" else "mensual"
        return exento(cargo, periodicidad)

    return evaluar
