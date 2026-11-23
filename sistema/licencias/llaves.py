import base64
import binascii
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from nucleo.licencia import LicenciaInvalida, leer_json

RUTA = Path(__file__).resolve().with_name("llaves.json")
LIMITE = 4096
MAXIMO_LLAVES = 4
LARGO_LLAVE = 32


def _llave(texto):
    try:
        crudos = base64.b64decode(texto, validate=True) if isinstance(texto, str) else b""
    except (binascii.Error, ValueError):
        crudos = b""
    if len(crudos) != LARGO_LLAVE:
        raise ImproperlyConfigured("Una llave de licencias no es válida.")
    return crudos


def publicas():
    try:
        with RUTA.open("rb") as archivo:
            crudos = archivo.read(LIMITE)
    except OSError:
        raise ImproperlyConfigured("No se pudo leer el archivo de llaves de licencias.")
    if len(crudos) >= LIMITE:
        raise ImproperlyConfigured("El archivo de llaves de licencias es demasiado grande.")
    try:
        datos = leer_json(crudos)
    except LicenciaInvalida:
        raise ImproperlyConfigured("El archivo de llaves de licencias no es válido.")
    if not isinstance(datos, dict) or set(datos) != {"licencias"}:
        raise ImproperlyConfigured("El archivo de llaves de licencias no es válido.")
    lista = datos["licencias"]
    if not isinstance(lista, list) or len(lista) > MAXIMO_LLAVES:
        raise ImproperlyConfigured("El archivo de llaves de licencias no es válido.")
    return tuple(_llave(texto) for texto in lista)
