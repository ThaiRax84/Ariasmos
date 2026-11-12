import sys

from django.core.exceptions import ImproperlyConfigured

from . import instancia
from .base import *
from .base import base_de_datos

_datos = instancia.leer()

if _datos is None:
    if "inicializar" not in sys.argv:
        raise ImproperlyConfigured(
            f"No existe {instancia.ruta_archivo()}. Ejecuta: python manage.py inicializar"
        )
    SECRET_KEY = "sin-instancia"
    CLAVE_MATRICULA = b""
    CLAVE_AUDITORIA = b""
    RUTA_ANCLA_AUDITORIA = ""
    DATABASES = base_de_datos(":memory:")
    ALLOWED_HOSTS = []
else:
    SECRET_KEY = _datos["clave_django"]
    CLAVE_MATRICULA = bytes.fromhex(_datos["clave_matricula"])
    if "clave_auditoria" not in _datos and "inicializar" not in sys.argv:
        raise ImproperlyConfigured("Falta clave_auditoria en la instancia. Ejecuta: python manage.py inicializar")
    CLAVE_AUDITORIA = bytes.fromhex(_datos.get("clave_auditoria", ""))
    RUTA_ANCLA_AUDITORIA = str(instancia.carpeta() / instancia.ANCLA)
    DATABASES = base_de_datos(_datos["base_datos"])
    ALLOWED_HOSTS = list(_datos.get("hosts", []))
    CSRF_TRUSTED_ORIGINS = list(_datos.get("origenes_confiables", []))
    TOKEN_ASISTENTE_HASH = _datos.get("token_asistente_hash", "")
    PROXIES_CONFIABLES = list(_datos.get("proxies_confiables", ["127.0.0.1", "::1"]))
    if _datos.get("https", True):
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
        COOKIE_DISPOSITIVO_SEGURA = True
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    else:
        SESSION_COOKIE_SECURE = False
        CSRF_COOKIE_SECURE = False
        COOKIE_DISPOSITIVO_SEGURA = False
