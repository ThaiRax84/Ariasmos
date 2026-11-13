import calendar
from datetime import date, timedelta

FIJO = "fijo"
PORCENTAJE = "porcentaje"
PUNTOS_BASE = 10000


class ErrorRecargo(ValueError):
    pass


def sumar_meses(fecha, meses):
    indice = fecha.year * 12 + (fecha.month - 1) + meses
    anio, mes = divmod(indice, 12)
    dia = min(fecha.day, calendar.monthrange(anio, mes + 1)[1])
    return date(anio, mes + 1, dia)


def fecha_en_mes(anio, mes, dia):
    return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))


def limite_sin_recargo(vencimiento, dias_gracia=0, prorroga_hasta=None):
    if dias_gracia < 0:
        raise ErrorRecargo("dias de gracia negativos")
    base = vencimiento
    if prorroga_hasta is not None and prorroga_hasta > base:
        base = prorroga_hasta
    return base + timedelta(days=dias_gracia)


def fechas_de_recargo(vencimiento, hoy, dias_gracia=0, se_repite=False, prorroga_hasta=None):
    primera = limite_sin_recargo(vencimiento, dias_gracia, prorroga_hasta) + timedelta(days=1)
    if hoy < primera:
        return []
    if not se_repite:
        return [primera]
    fechas = []
    k = 0
    while True:
        fecha = sumar_meses(primera, k)
        if fecha > hoy:
            return fechas
        fechas.append(fecha)
        k += 1


def redondear_proporcion(importe, puntos_base):
    return (importe * puntos_base + PUNTOS_BASE // 2) // PUNTOS_BASE


def importe_recargo(tipo, valor, saldo_base, acumulado=0, tope=None):
    if valor < 0 or saldo_base < 0 or acumulado < 0 or (tope is not None and tope < 0):
        raise ErrorRecargo("valores negativos")
    if saldo_base == 0:
        return 0
    if tipo == FIJO:
        importe = valor
    elif tipo == PORCENTAJE:
        importe = redondear_proporcion(saldo_base, valor)
    else:
        raise ErrorRecargo("tipo de recargo desconocido")
    if tope is not None:
        importe = min(importe, max(tope - acumulado, 0))
    return importe


def recargos_pendientes(tipo, valor, saldo_base, vencimiento, hoy, ya_generadas=(), acumulado=0, dias_gracia=0, se_repite=False, tope=None, prorroga_hasta=None):
    hechas = set(ya_generadas)
    nuevos = []
    for fecha in fechas_de_recargo(vencimiento, hoy, dias_gracia, se_repite, prorroga_hasta):
        if fecha in hechas:
            continue
        importe = importe_recargo(tipo, valor, saldo_base, acumulado, tope)
        if importe <= 0:
            continue
        nuevos.append((fecha, importe))
        acumulado += importe
    return nuevos


def importe_con_beca(importe, tipo=None, valor=0):
    if importe < 0 or valor < 0:
        raise ErrorRecargo("valores negativos")
    if tipo is None:
        return importe, 0
    if tipo == FIJO:
        descuento = min(valor, importe)
    elif tipo == PORCENTAJE:
        if valor > PUNTOS_BASE:
            raise ErrorRecargo("porcentaje mayor al cien por ciento")
        descuento = redondear_proporcion(importe, valor)
    else:
        raise ErrorRecargo("tipo de beca desconocido")
    return importe - descuento, descuento
