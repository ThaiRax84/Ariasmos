import hashlib
import hmac
import json

GENESIS = "0" * 64


def canonico(contenido):
    return json.dumps(contenido, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sellar(clave, anterior, contenido):
    if len(clave) < 32:
        raise ValueError("clave de auditoria demasiado corta")
    return hmac.new(clave, (anterior + "|" + canonico(contenido)).encode("utf-8"), hashlib.sha256).hexdigest()


def firmar(clave, contenido):
    return hmac.new(clave, canonico(contenido).encode("utf-8"), hashlib.sha256).hexdigest()


def firma_valida(clave, contenido, firma):
    return hmac.compare_digest(firmar(clave, contenido), firma or "")


def verificar(clave, eslabones):
    anterior = GENESIS
    for posicion, (sello_anterior, contenido, sello) in enumerate(eslabones):
        if sello_anterior != anterior or not hmac.compare_digest(sellar(clave, anterior, contenido), sello):
            return posicion
        anterior = sello
    return None
