from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_private_key,
)
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def privada():
    try:
        with open(settings.RUTA_LLAVE_LICENCIAS, "rb") as archivo:
            llave = load_pem_private_key(archivo.read(), password=None)
    except (OSError, ValueError, TypeError):
        raise ImproperlyConfigured("No se pudo leer la llave de licencias de Central.")
    if not isinstance(llave, Ed25519PrivateKey):
        raise ImproperlyConfigured("La llave de licencias de Central no es Ed25519.")
    return llave


def publica():
    return privada().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
