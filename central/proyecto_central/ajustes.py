import sys

from django.core.exceptions import ImproperlyConfigured

from . import instancia
from .base import *
from .base import base_de_datos

_datos = instancia.leer()

if _datos is None:
    if "inicializar_central" not in sys.argv:
        raise ImproperlyConfigured(
            f"No existe {instancia.ruta_archivo()}. Ejecuta: python manage.py inicializar_central --carpeta <carpeta>"
        )
    SECRET_KEY = "sin-instancia"
    DATABASES = base_de_datos(":memory:")
    ALLOWED_HOSTS = []
    PROXIES_CONFIABLES = []
    RUTA_LLAVE_LICENCIAS = ""
    CLAVE_SECRETOS = b""
    URL_PUBLICA = ""
    PROVEEDOR_MENSAJES = "simulado"
else:
    SECRET_KEY = _datos["clave_django"]
    DATABASES = base_de_datos(_datos["base_datos"])
    ALLOWED_HOSTS = list(_datos.get("hosts", []))
    PROXIES_CONFIABLES = list(_datos.get("proxies_confiables", []))
    RUTA_LLAVE_LICENCIAS = str(
        _datos.get("llave_licencias") or instancia.carpeta() / instancia.LLAVE
    )
    if "clave_secretos" not in _datos and "inicializar_central" not in sys.argv:
        raise ImproperlyConfigured(
            "Faltan claves nuevas en la instancia. Ejecuta: python manage.py inicializar_central"
        )
    CLAVE_SECRETOS = bytes.fromhex(_datos.get("clave_secretos", ""))
    URL_PUBLICA = str(_datos.get("url_publica", "")).rstrip("/")
    PROVEEDOR_MENSAJES = str(_datos.get("proveedor_mensajes", "simulado"))
    if PROVEEDOR_MENSAJES not in ("simulado", "twilio"):
        raise ImproperlyConfigured(
            "proveedor_mensajes debe ser «simulado» o «twilio» en la configuración de Central."
        )
    if PROVEEDOR_MENSAJES == "twilio" and not URL_PUBLICA.startswith("https://"):
        raise ImproperlyConfigured(
            "Con el proveedor «twilio», url_publica debe ser una dirección https en la configuración de Central."
        )
