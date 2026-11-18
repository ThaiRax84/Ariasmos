import os
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

REGIONES = {
    "America": "América",
    "Europe": "Europa",
    "Africa": "África",
    "Asia": "Asia",
    "Atlantic": "Atlántico",
    "Australia": "Australia",
    "Indian": "Índico",
    "Pacific": "Pacífico",
    "Antarctica": "Antártida",
}
ORDEN_REGIONES = tuple(REGIONES)


def _leer(nombre):
    try:
        return resources.files("tzdata").joinpath(f"zoneinfo/{nombre}").read_text(encoding="utf-8")
    except (ModuleNotFoundError, FileNotFoundError, OSError):
        return ""


@lru_cache(maxsize=1)
def canonicas():
    nombres = set()
    for linea in _leer("tzdata.zi").splitlines():
        if linea.startswith("Z "):
            nombres.add(linea.split()[1])
    for linea in _leer("zone.tab").splitlines():
        partes = linea.split("\t")
        if len(partes) >= 3 and not linea.startswith("#"):
            nombres.add(partes[2])
    disponibles = available_timezones()
    if not nombres:
        nombres = set(disponibles)
    return frozenset(n for n in nombres & disponibles if n.split("/", 1)[0] in REGIONES and "/" in n)


def ciudad(nombre):
    partes = nombre.split("/")[1:]
    texto = partes[-1].replace("_", " ")
    if len(partes) > 1:
        texto = f"{texto} ({partes[0].replace('_', ' ')})"
    return texto


def desfase(nombre, momento=None):
    momento = momento or datetime.now(timezone.utc)
    minutos = int(momento.astimezone(ZoneInfo(nombre)).utcoffset().total_seconds() // 60)
    signo = "−" if minutos < 0 else "+"
    minutos = abs(minutos)
    return f"UTC{signo}{minutos // 60:02d}:{minutos % 60:02d}"


def etiqueta(nombre, momento=None):
    return f"{ciudad(nombre)} ({desfase(nombre, momento)})"


def validas(actual=""):
    nombres = set(canonicas())
    if actual and actual not in nombres and es_zona(actual):
        nombres.add(actual)
    return nombres


def es_zona(nombre):
    if not nombre or not isinstance(nombre, str) or len(nombre) > 64:
        return False
    try:
        ZoneInfo(nombre)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def opciones(actual="", vacia=True, momento=None):
    grupos = {}
    for nombre in validas(actual):
        region = nombre.split("/", 1)[0]
        grupos.setdefault(REGIONES.get(region, "Otras"), []).append((nombre, etiqueta(nombre, momento)))
    resultado = [("", "Elige la zona horaria")] if vacia else []
    for region in ORDEN_REGIONES:
        titulo = REGIONES[region]
        if titulo in grupos:
            resultado.append((titulo, sorted(grupos[titulo], key=lambda par: par[1].casefold())))
    if "Otras" in grupos:
        resultado.append(("Otras", sorted(grupos["Otras"], key=lambda par: par[1])))
    return resultado


def _de_enlace(ruta):
    try:
        destino = os.path.realpath(ruta)
    except OSError:
        return ""
    marca = "zoneinfo" + os.sep
    if marca in destino:
        return destino.split(marca, 1)[1].replace(os.sep, "/")
    return ""


def de_la_computadora():
    candidatos = [os.environ.get("TZ", "").lstrip(":")]
    try:
        with open("/etc/timezone", encoding="utf-8") as archivo:
            candidatos.append(archivo.read().strip())
    except OSError:
        pass
    candidatos.append(_de_enlace("/etc/localtime"))
    for candidato in candidatos:
        if candidato in canonicas():
            return candidato
    return ""
