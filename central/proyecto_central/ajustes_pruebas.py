import atexit
import os
import shutil
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from .base import *
from .base import base_de_datos

SECRET_KEY = "clave-solo-para-pruebas-de-central-0123456789"
ALLOWED_HOSTS = ["testserver"]
PROXIES_CONFIABLES = []
_carpeta = Path(tempfile.mkdtemp(prefix="central-pruebas-"))
atexit.register(shutil.rmtree, _carpeta, ignore_errors=True)
RUTA_LLAVE_LICENCIAS = str(_carpeta / "llave-licencias.pem")
Path(RUTA_LLAVE_LICENCIAS).write_bytes(Ed25519PrivateKey.generate().private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
_ruta = os.path.join(tempfile.gettempdir(), f"central-pruebas-{os.getpid()}.sqlite3")
DATABASES = base_de_datos(_ruta)
DATABASES["default"]["TEST"] = {"NAME": _ruta}
