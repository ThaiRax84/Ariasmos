import json
from contextvars import ContextVar
from functools import lru_cache

from django.conf import settings

from nucleo import dinero

POR_DEFECTO = "MXN"
_actual = ContextVar("moneda_actual", default=None)


class ErrorMoneda(ValueError):
    pass


@lru_cache(maxsize=1)
def catalogo():
    with (settings.RAIZ / "datos" / "monedas.json").open(encoding="utf-8") as archivo:
        datos = json.load(archivo)
    resultado = {}
    for moneda in datos.get("monedas", []):
        codigo = moneda.get("codigo", "")
        if not (isinstance(codigo, str) and len(codigo) == 3 and codigo.isascii() and codigo.isupper()) or codigo in resultado:
            raise ErrorMoneda(f"código de moneda inválido: {codigo!r}")
        if not isinstance(moneda.get("simbolo"), str) or not 1 <= len(moneda["simbolo"]) <= 4 or not isinstance(moneda.get("decimales"), int):
            raise ErrorMoneda(f"moneda mal definida: {codigo}")
        resultado[codigo] = {"codigo": codigo, "nombre": str(moneda.get("nombre", codigo))[:60], "simbolo": moneda["simbolo"], "decimales": moneda["decimales"]}
    if POR_DEFECTO not in resultado:
        raise ErrorMoneda("el catálogo no trae MXN")
    return resultado


def disponibles():
    return {codigo: m for codigo, m in catalogo().items() if m["decimales"] == 2}


def opciones():
    return [(codigo, f"{m['nombre']} ({codigo}, {m['simbolo']})") for codigo, m in disponibles().items()]


def validar(codigo):
    if codigo not in disponibles():
        raise ErrorMoneda(f"moneda no disponible: {codigo}")
    return codigo


def fijar(codigo):
    return _actual.set(codigo)


def soltar(marca):
    _actual.reset(marca)


def codigo_actual():
    codigo = _actual.get()
    if codigo is None:
        from .models import Negocio

        codigo = Negocio.objects.filter(pk=1).values_list("moneda", flat=True).first() or POR_DEFECTO
    return codigo


def actual():
    return catalogo().get(codigo_actual()) or catalogo()[POR_DEFECTO]


def _simbolo_pdf(simbolo):
    try:
        simbolo.encode("cp1252")
    except UnicodeEncodeError:
        return ""
    return simbolo


def formatear(centavos, pdf=False):
    moneda = actual()
    simbolo = _simbolo_pdf(moneda["simbolo"]) if pdf else moneda["simbolo"]
    return dinero.formatear(centavos, simbolo, moneda["codigo"])
