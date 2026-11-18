import re
from datetime import date, timedelta

from nucleo import recargos

MESES = {"mensual": 1, "bimestral": 2, "trimestral": 3, "semestral": 6, "anual": 12}
SEMANA = re.compile(r"^(\d{4})-S(\d{2})$")
QUINCENA = re.compile(r"^(\d{4})-(\d{2})-([12])$")
MES = re.compile(r"^(\d{4})-(\d{2})$")


def _fin_de_mes(anio, mes):
    return recargos.fecha_en_mes(anio, mes, 31)


def _mas_meses(anio, mes, cuantos):
    total = anio * 12 + (mes - 1) + cuantos
    return total // 12, total % 12 + 1


def periodo_de(periodicidad, fecha):
    if periodicidad == "semanal":
        inicio = fecha - timedelta(days=fecha.weekday())
        return inicio, inicio + timedelta(days=6)
    if periodicidad == "quincenal":
        if fecha.day <= 15:
            return date(fecha.year, fecha.month, 1), date(fecha.year, fecha.month, 15)
        return date(fecha.year, fecha.month, 16), _fin_de_mes(fecha.year, fecha.month)
    salto = MESES.get(periodicidad, 1)
    primero = ((fecha.month - 1) // salto) * salto + 1
    anio, mes = _mas_meses(fecha.year, primero, salto - 1)
    return date(fecha.year, primero, 1), _fin_de_mes(anio, mes)


def limites(periodicidad, clave):
    try:
        encontrado = SEMANA.match(clave or "")
        if encontrado:
            inicio = date.fromisocalendar(int(encontrado.group(1)), int(encontrado.group(2)), 1)
            return inicio, inicio + timedelta(days=6)
        encontrado = QUINCENA.match(clave or "")
        if encontrado:
            anio, mes, mitad = int(encontrado.group(1)), int(encontrado.group(2)), encontrado.group(3)
            return periodo_de("quincenal", date(anio, mes, 1 if mitad == "1" else 16))
        encontrado = MES.match(clave or "")
        if encontrado:
            anio, mes = int(encontrado.group(1)), int(encontrado.group(2))
            salto = MESES.get(periodicidad, 1)
            fin_anio, fin_mes = _mas_meses(anio, mes, salto - 1)
            return date(anio, mes, 1), _fin_de_mes(fin_anio, fin_mes)
    except ValueError:
        return None
    return None
