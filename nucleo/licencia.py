import base64
import binascii
import hashlib
import json
import re
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

FORMATO = 1
PRODUCTO = "ariasmos"
LIMITE = 8192
LARGO_FIRMA = 64
CAMPOS = {
    "licencia": ("formato", "producto", "tipo", "negocio", "instalacion", "plan", "modulos", "serie", "emitida", "vence", "dias_gracia"),
    "revocacion": ("formato", "producto", "tipo", "negocio", "instalacion", "emitida"),
    "renovacion": ("formato", "producto", "tipo", "instalacion", "momento", "sello", "version"),
    "activacion": ("formato", "producto", "tipo", "instalacion", "momento", "sello", "version"),
    "acuse": ("formato", "producto", "tipo", "instalacion", "sello", "hora"),
}
ENTEROS = ("serie", "dias_gracia")
FECHAS = ("emitida", "vence", "momento", "hora")
TEXTOS = ("producto", "tipo", "negocio", "instalacion", "plan", "emitida", "vence", "momento", "hora", "sello", "version")
PATRON_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
PATRON_INSTALACION = re.compile(r"[0-9a-f]{64}")
PATRON_SELLO = re.compile(r"[0-9a-f]{32}")
PATRON_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
FORMATO_FECHA = "%Y-%m-%dT%H:%M:%SZ"
ANIO_MAXIMO = 9000
GRACIA_MAXIMA = 366
SERIE_MAXIMA = 2**53


class LicenciaInvalida(Exception):
    def __init__(self, motivo):
        super().__init__(motivo)
        self.motivo = motivo


def serializar(carga):
    return json.dumps(carga, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def firmar(carga, llave_privada):
    datos = serializar(carga)
    return {"carga": base64.b64encode(datos).decode("ascii"), "firma": base64.b64encode(llave_privada.sign(datos)).decode("ascii")}


def huella(llave_publica):
    return hashlib.sha256(llave_publica).hexdigest()


def texto_de(momento):
    if momento.tzinfo is None:
        raise ValueError("el momento debe tener zona horaria")
    return momento.astimezone(timezone.utc).strftime(FORMATO_FECHA)


def momento_de(texto):
    if not isinstance(texto, str) or PATRON_FECHA.fullmatch(texto) is None:
        raise ValueError("fecha no válida")
    momento = datetime.strptime(texto, FORMATO_FECHA).replace(tzinfo=timezone.utc)
    if momento.year > ANIO_MAXIMO:
        raise ValueError("fecha fuera de rango")
    return momento


def _sin_repetidos(pares):
    resultado = {}
    for clave, valor in pares:
        if clave in resultado:
            raise LicenciaInvalida("formato")
        resultado[clave] = valor
    return resultado


def _rechazar_constante(valor):
    raise LicenciaInvalida("formato")


def leer_json(datos):
    try:
        texto = bytes(datos).decode("utf-8")
        return json.loads(texto, object_pairs_hook=_sin_repetidos, parse_constant=_rechazar_constante)
    except (ValueError, RecursionError):
        raise LicenciaInvalida("formato")


def _decodificar(texto, largo_maximo):
    if not isinstance(texto, str) or len(texto) > largo_maximo:
        raise LicenciaInvalida("formato")
    try:
        return base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        raise LicenciaInvalida("formato")


def _separar(documento):
    if not isinstance(documento, dict) or set(documento) != {"carga", "firma"}:
        raise LicenciaInvalida("formato")
    carga = _decodificar(documento["carga"], (LIMITE // 3 + 1) * 4)
    firma = _decodificar(documento["firma"], 88)
    if len(carga) > LIMITE or len(firma) != LARGO_FIRMA:
        raise LicenciaInvalida("formato")
    return carga, firma


def _firma_valida(carga, firma, llaves_publicas):
    for llave in llaves_publicas:
        try:
            Ed25519PublicKey.from_public_bytes(bytes(llave)).verify(firma, carga)
            return True
        except (InvalidSignature, ValueError, TypeError):
            continue
    return False


def _es_entero(valor):
    return type(valor) is int and valor >= 0


def _validar(carga, tipo):
    if not isinstance(carga, dict) or set(carga) != set(CAMPOS[tipo]):
        raise LicenciaInvalida("campos")
    if carga["formato"] != FORMATO or type(carga["formato"]) is not int:
        raise LicenciaInvalida("campos")
    if carga["producto"] != PRODUCTO or carga["tipo"] != tipo:
        raise LicenciaInvalida("campos")
    if any(campo in carga and not isinstance(carga[campo], str) for campo in TEXTOS):
        raise LicenciaInvalida("campos")
    if any(campo in carga and not _es_entero(carga[campo]) for campo in ENTEROS):
        raise LicenciaInvalida("campos")
    if "modulos" in carga and not (isinstance(carga["modulos"], list) and all(isinstance(m, str) for m in carga["modulos"])):
        raise LicenciaInvalida("campos")
    patrones = (("instalacion", PATRON_INSTALACION), ("sello", PATRON_SELLO), ("version", PATRON_VERSION))
    if any(campo in carga and patron.fullmatch(carga[campo]) is None for campo, patron in patrones):
        raise LicenciaInvalida("campos")
    try:
        fechas = {campo: momento_de(carga[campo]) for campo in FECHAS if campo in carga}
    except ValueError:
        raise LicenciaInvalida("campos")
    if tipo == "licencia" and not (carga["dias_gracia"] <= GRACIA_MAXIMA and carga["serie"] <= SERIE_MAXIMA and fechas["vence"] >= fechas["emitida"]):
        raise LicenciaInvalida("campos")


def abrir(documento, llaves_publicas, tipo):
    if tipo not in CAMPOS:
        raise LicenciaInvalida("campos")
    carga, firma = _separar(documento)
    if not _firma_valida(carga, firma, tuple(llaves_publicas)):
        raise LicenciaInvalida("firma")
    datos = leer_json(carga)
    _validar(datos, tipo)
    return datos
