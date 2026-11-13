import hashlib
import os
import tempfile

from django.contrib.auth.hashers import Argon2PasswordHasher

from .base import *
from .base import base_de_datos


class Argon2Pruebas(Argon2PasswordHasher):
    time_cost = 1
    memory_cost = 64
    parallelism = 1


SECRET_KEY = "clave-solo-para-pruebas-no-usar-en-produccion-0123456789"
CLAVE_MATRICULA = bytes(range(32))
CLAVE_AUDITORIA = bytes(range(32, 64))
CLAVE_SECRETOS = bytes(range(64, 96))
CLAVE_RESPALDO = bytes(range(96, 128))
RUTA_INSTANCIA = ""
RUTA_ANCLA_AUDITORIA = os.path.join(tempfile.gettempdir(), f"cobro-pruebas-ancla-{os.getpid()}.json")
TOKEN_ASISTENTE = "token-de-pruebas"
TOKEN_ASISTENTE_HASH = hashlib.sha256(TOKEN_ASISTENTE.encode()).hexdigest()
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
PASSWORD_HASHERS = ["proyecto.ajustes_pruebas.Argon2Pruebas"]
_ruta = os.path.join(tempfile.gettempdir(), f"cobro-pruebas-{os.getpid()}.sqlite3")
DATABASES = base_de_datos(_ruta)
DATABASES["default"]["TEST"] = {"NAME": _ruta}
COOKIE_DISPOSITIVO_SEGURA = True
