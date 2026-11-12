import json
import os
import threading
from pathlib import Path

from django.conf import settings

from nucleo import cadena

_cerrojo = threading.Lock()


def ruta():
    return Path(settings.RUTA_ANCLA_AUDITORIA)


def leer():
    archivo = ruta()
    if not archivo.exists():
        return None
    try:
        with archivo.open(encoding="utf-8") as entrada:
            return json.load(entrada)
    except (OSError, ValueError):
        return {}


def contenido(ancla):
    return {"numero": ancla.get("numero"), "sello": ancla.get("sello"), "momento": ancla.get("momento")}


def es_autentica(ancla):
    return bool(ancla) and cadena.firma_valida(settings.CLAVE_AUDITORIA, contenido(ancla), ancla.get("firma"))


def escribir(numero, sello, momento):
    with _cerrojo:
        actual = leer()
        if actual and es_autentica(actual) and actual.get("numero", 0) >= numero:
            return
        datos = {"numero": numero, "sello": sello, "momento": momento}
        datos["firma"] = cadena.firmar(settings.CLAVE_AUDITORIA, datos)
        archivo = ruta()
        archivo.parent.mkdir(parents=True, exist_ok=True)
        temporal = archivo.with_name(archivo.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
        with temporal.open("w", encoding="utf-8") as salida:
            json.dump(datos, salida)
            salida.flush()
            os.fsync(salida.fileno())
        os.replace(temporal, archivo)
