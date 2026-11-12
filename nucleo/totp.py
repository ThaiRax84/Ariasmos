import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

DIGITOS = 6
PERIODO = 30


def generar_secreto():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def _clave(secreto):
    limpio = secreto.replace(" ", "").upper()
    return base64.b32decode(limpio + "=" * (-len(limpio) % 8))


def paso_actual(momento=None):
    return int((time.time() if momento is None else momento) // PERIODO)


def codigo(secreto, paso, digitos=DIGITOS):
    mac = hmac.new(_clave(secreto), struct.pack(">Q", paso), hashlib.sha1).digest()
    desplazamiento = mac[-1] & 0x0F
    valor = struct.unpack(">I", mac[desplazamiento:desplazamiento + 4])[0] & 0x7FFFFFFF
    return str(valor % 10 ** digitos).zfill(digitos)


def normalizar(propuesto):
    return "".join(c for c in str(propuesto) if c.isascii() and c.isdigit())


def verificar(secreto, propuesto, momento=None, ventana=1):
    propuesto = normalizar(propuesto)
    if len(propuesto) != DIGITOS or not secreto:
        return None
    actual = paso_actual(momento)
    for paso in range(actual - ventana, actual + ventana + 1):
        if hmac.compare_digest(codigo(secreto, paso), propuesto):
            return paso
    return None


def uri(secreto, cuenta, emisor):
    etiqueta = quote(f"{emisor}:{cuenta}")
    parametros = urlencode({"secret": secreto, "issuer": emisor, "algorithm": "SHA1", "digits": DIGITOS, "period": PERIODO})
    return f"otpauth://totp/{etiqueta}?{parametros}"
