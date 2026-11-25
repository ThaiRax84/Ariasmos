import hashlib
import hmac

from django.conf import settings

from nucleo import sobre

CONTEXTO_TOKEN = "mensajeria|token"
ETIQUETA_TOKEN = "mensajeria|secretos"
ETIQUETA_NUMERO = "mensajeria|numero"


def cifrar_token(token):
    return sobre.cifrar_texto(
        sobre.derivar(bytes(settings.CLAVE_SECRETOS), ETIQUETA_TOKEN),
        token,
        CONTEXTO_TOKEN,
    )


def token_de(remitente):
    return sobre.descifrar_texto(
        sobre.derivar(bytes(settings.CLAVE_SECRETOS), ETIQUETA_TOKEN),
        remitente.token_cifrado,
        CONTEXTO_TOKEN,
    )


def resumen_de_numero(numero):
    clave = sobre.derivar(bytes(settings.CLAVE_SECRETOS), ETIQUETA_NUMERO)
    return hmac.new(clave, numero.encode("utf-8"), hashlib.sha256).hexdigest()
