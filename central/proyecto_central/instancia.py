import json
import os
import secrets
import socket
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ARCHIVO = "configuracion.json"
LLAVE = "llave-licencias.pem"


def carpeta():
    return Path(
        os.environ.get("CENTRAL_INSTANCIA") or RAIZ / "central" / "instancia"
    ).resolve()


def ruta_archivo(base=None):
    return (base or carpeta()) / ARCHIVO


def leer(base=None):
    ruta = ruta_archivo(base)
    if not ruta.exists():
        return None
    with ruta.open(encoding="utf-8") as archivo:
        return json.load(archivo)


def nueva(base, hosts=()):
    nombres = ["localhost", "127.0.0.1", "[::1]", socket.gethostname(), *hosts]
    return {
        "clave_django": secrets.token_urlsafe(50),
        "base_datos": str(base / "central.sqlite3"),
        "hosts": list(dict.fromkeys(nombre for nombre in nombres if nombre)),
        "proxies_confiables": [],
        "llave_licencias": str(base / LLAVE),
    }


def escribir_privado(ruta, contenido):
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as archivo:
        archivo.write(contenido)


def escribir(base, datos):
    base.mkdir(parents=True, exist_ok=True)
    escribir_privado(
        ruta_archivo(base),
        json.dumps(datos, indent=2, ensure_ascii=False).encode("utf-8"),
    )
