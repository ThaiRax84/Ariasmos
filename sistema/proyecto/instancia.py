import json
import os
import secrets
import socket
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ARCHIVO = "configuracion.json"


def carpeta():
    return Path(os.environ.get("COBRO_INSTANCIA") or RAIZ / "instancia").resolve()


def ruta_archivo():
    return carpeta() / ARCHIVO


def leer():
    ruta = ruta_archivo()
    if not ruta.exists():
        return None
    with ruta.open(encoding="utf-8") as archivo:
        return json.load(archivo)


def nueva(https=True):
    base = carpeta()
    hosts = ["localhost", "127.0.0.1", "[::1]"]
    nombre = socket.gethostname()
    if nombre and nombre not in hosts:
        hosts.append(nombre)
    return {
        "clave_django": secrets.token_urlsafe(50),
        "clave_matricula": secrets.token_hex(32),
        "base_datos": str(base / "cobro.sqlite3"),
        "https": https,
        "hosts": hosts,
        "origenes_confiables": [],
        "proxies_confiables": ["127.0.0.1", "::1"],
    }


def escribir(datos):
    base = carpeta()
    base.mkdir(parents=True, exist_ok=True)
    ruta = ruta_archivo()
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, indent=2, ensure_ascii=False)
    return ruta


def reemplazar(datos):
    ruta = ruta_archivo()
    temporal = ruta.with_suffix(".tmp")
    descriptor = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, indent=2, ensure_ascii=False)
    os.replace(temporal, ruta)
    return ruta
