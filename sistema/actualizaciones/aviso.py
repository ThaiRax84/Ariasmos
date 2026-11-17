import base64
import binascii
import json
import re
import unicodedata
from datetime import date

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PRODUCTO = "ariasmos"
LIMITE_AVISO = 64 * 1024
LARGO_FIRMA = 64
LARGO_LLAVE = 32
MAXIMO_INSTALADOR = 500 * 1024 * 1024
MAXIMO_CONTADOR = 2 ** 53
MAXIMO_CAMBIOS = 20
LARGO_CAMBIO = 200
CAMPOS_VERSION = ("producto", "version", "contador", "fecha", "instalador", "minimo", "cambios")
CAMPOS_INSTALADOR = ("nombre", "tamano", "sha256")
CAMPOS_CAMBIO_LLAVE = ("producto", "contador", "llave_uso")
PATRON_VERSION = re.compile(r"(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})")
PATRON_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
PATRON_SHA256 = re.compile(r"[0-9a-f]{64}")
PATRON_NOMBRE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\.exe")
PATRON_BASE64 = re.compile(r"[A-Za-z0-9+/]{43}=")


class AvisoInvalido(ValueError):
    def __init__(self, motivo, detalle=""):
        super().__init__(detalle or motivo)
        self.motivo = motivo


def version_valida(texto):
    return isinstance(texto, str) and PATRON_VERSION.fullmatch(texto) is not None


def como_tupla(texto):
    if not version_valida(texto):
        raise AvisoInvalido("version_invalida")
    return tuple(int(parte) for parte in texto.split("."))


def mayor(una, otra):
    return como_tupla(una) > como_tupla(otra)


def llave_de_texto(texto):
    if not isinstance(texto, str) or PATRON_BASE64.fullmatch(texto) is None:
        raise AvisoInvalido("llave_invalida")
    try:
        crudos = base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        raise AvisoInvalido("llave_invalida")
    if len(crudos) != LARGO_LLAVE:
        raise AvisoInvalido("llave_invalida")
    return crudos


def texto_de_llave(crudos):
    return base64.b64encode(crudos).decode("ascii")


def verificar_firma(llave, datos, firma):
    if not isinstance(datos, (bytes, bytearray)) or not isinstance(firma, (bytes, bytearray)):
        raise AvisoInvalido("formato")
    if len(datos) == 0 or len(datos) > LIMITE_AVISO:
        raise AvisoInvalido("tamano_aviso")
    if len(firma) != LARGO_FIRMA:
        raise AvisoInvalido("firma")
    try:
        Ed25519PublicKey.from_public_bytes(llave_de_texto(llave)).verify(bytes(firma), bytes(datos))
    except InvalidSignature:
        raise AvisoInvalido("firma")
    except ValueError:
        raise AvisoInvalido("llave_invalida")


def _sin_repetidos(pares):
    resultado = {}
    for clave, valor in pares:
        if clave in resultado:
            raise AvisoInvalido("formato", "campo repetido")
        resultado[clave] = valor
    return resultado


def _rechazar_constante(valor):
    raise AvisoInvalido("formato", "valor numérico no admitido")


def _json(datos):
    try:
        texto = bytes(datos).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise AvisoInvalido("formato", "no es UTF-8")
    if texto.startswith("﻿"):
        raise AvisoInvalido("formato", "marca de orden de bytes")
    try:
        valor = json.loads(texto, object_pairs_hook=_sin_repetidos, parse_float=_rechazar_constante, parse_constant=_rechazar_constante)
    except AvisoInvalido:
        raise
    except (ValueError, RecursionError):
        raise AvisoInvalido("formato", "JSON no válido")
    if not isinstance(valor, dict):
        raise AvisoInvalido("formato", "no es un objeto")
    return valor


def _exactos(objeto, campos):
    if not isinstance(objeto, dict) or set(objeto) != set(campos):
        raise AvisoInvalido("formato", "campos de más o de menos")


def _entero(valor, minimo, maximo):
    if type(valor) is not int or not minimo <= valor <= maximo:
        raise AvisoInvalido("formato", "entero fuera de rango")
    return valor


def _texto_plano(valor, largo):
    if not isinstance(valor, str) or not 0 < len(valor) <= largo:
        raise AvisoInvalido("formato", "texto no válido")
    for caracter in valor:
        if unicodedata.category(caracter)[0] in ("C", "Z") and caracter != " ":
            raise AvisoInvalido("formato", "carácter no admitido")
    return valor


def _producto(objeto):
    if objeto.get("producto") != PRODUCTO:
        raise AvisoInvalido("producto")


def leer_version(datos, firma, llave):
    verificar_firma(llave, datos, firma)
    objeto = _json(datos)
    _exactos(objeto, CAMPOS_VERSION)
    _producto(objeto)
    if not version_valida(objeto["version"]) or not version_valida(objeto["minimo"]):
        raise AvisoInvalido("formato", "versión no válida")
    if mayor(objeto["minimo"], objeto["version"]):
        raise AvisoInvalido("formato", "mínimo mayor que la versión")
    _entero(objeto["contador"], 1, MAXIMO_CONTADOR)
    fecha = objeto["fecha"]
    if not isinstance(fecha, str) or PATRON_FECHA.fullmatch(fecha) is None:
        raise AvisoInvalido("formato", "fecha no válida")
    try:
        date.fromisoformat(fecha)
    except ValueError:
        raise AvisoInvalido("formato", "fecha no válida")
    instalador = objeto["instalador"]
    _exactos(instalador, CAMPOS_INSTALADOR)
    if not isinstance(instalador["nombre"], str) or PATRON_NOMBRE.fullmatch(instalador["nombre"]) is None:
        raise AvisoInvalido("formato", "nombre del instalador no válido")
    _entero(instalador["tamano"], 1, MAXIMO_INSTALADOR)
    if not isinstance(instalador["sha256"], str) or PATRON_SHA256.fullmatch(instalador["sha256"]) is None:
        raise AvisoInvalido("formato", "huella no válida")
    cambios = objeto["cambios"]
    if not isinstance(cambios, list) or len(cambios) > MAXIMO_CAMBIOS:
        raise AvisoInvalido("formato", "lista de cambios no válida")
    for linea in cambios:
        _texto_plano(linea, LARGO_CAMBIO)
    return {
        "producto": PRODUCTO,
        "version": objeto["version"],
        "contador": objeto["contador"],
        "fecha": fecha,
        "instalador": {"nombre": instalador["nombre"], "tamano": instalador["tamano"], "sha256": instalador["sha256"]},
        "minimo": objeto["minimo"],
        "cambios": list(cambios),
    }


def leer_cambio_de_llave(datos, firma, recuperacion):
    verificar_firma(recuperacion, datos, firma)
    objeto = _json(datos)
    _exactos(objeto, CAMPOS_CAMBIO_LLAVE)
    _producto(objeto)
    _entero(objeto["contador"], 1, MAXIMO_CONTADOR)
    llave_de_texto(objeto["llave_uso"])
    if objeto["llave_uso"] == recuperacion:
        raise AvisoInvalido("llave_invalida", "la llave de uso no puede ser la de recuperación")
    return {"producto": PRODUCTO, "contador": objeto["contador"], "llave_uso": objeto["llave_uso"]}


def serializar(objeto):
    return (json.dumps(objeto, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
