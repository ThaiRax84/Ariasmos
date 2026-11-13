import getpass
import importlib.util
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

RAIZ = Path(__file__).resolve().parents[2]
EXTENSION_PRIVADA = ".llave-privada"
LARGO_MINIMO_CONTRASENA = 16


class ErrorFirma(Exception):
    pass


def modulo_aviso():
    ruta = RAIZ / "sistema" / "actualizaciones" / "aviso.py"
    especificacion = importlib.util.spec_from_file_location("ariasmos_aviso", ruta)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def pedir_contrasena_nueva(nombre, pedir=getpass.getpass):
    primera = pedir(f"Contraseña para la llave de {nombre} (mínimo {LARGO_MINIMO_CONTRASENA} caracteres): ")
    if len(primera) < LARGO_MINIMO_CONTRASENA:
        raise ErrorFirma(f"La contraseña debe tener al menos {LARGO_MINIMO_CONTRASENA} caracteres.")
    if pedir(f"Repite la contraseña de la llave de {nombre}: ") != primera:
        raise ErrorFirma("Las contraseñas no coinciden.")
    return primera


def escribir_nuevo(ruta, contenido, privado=False):
    ruta = Path(ruta)
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600 if privado else 0o644)
    with os.fdopen(descriptor, "wb") as archivo:
        archivo.write(contenido)
    return ruta


def privada_cifrada(llave, contrasena):
    return llave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.BestAvailableEncryption(contrasena.encode("utf-8")))


def publica_texto(llave):
    aviso = modulo_aviso()
    return aviso.texto_de_llave(llave.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def leer_privada(ruta, pedir=getpass.getpass, nombre="la llave"):
    ruta = Path(ruta)
    if ruta.suffix != EXTENSION_PRIVADA:
        raise ErrorFirma(f"La llave privada debe tener la extensión {EXTENSION_PRIVADA}.")
    contenido = ruta.read_bytes()
    contrasena = pedir(f"Contraseña de {nombre} ({ruta.name}): ")
    try:
        llave = serialization.load_pem_private_key(contenido, password=contrasena.encode("utf-8"))
    except (ValueError, TypeError):
        raise ErrorFirma("La contraseña no es correcta o el archivo no es una llave.")
    if not isinstance(llave, Ed25519PrivateKey):
        raise ErrorFirma("El archivo no es una llave Ed25519.")
    return llave


def principal(funcion, argv=None):
    try:
        funcion(argv)
    except ErrorFirma as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0
