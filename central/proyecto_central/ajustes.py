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
else:
    SECRET_KEY = _datos["clave_django"]
    DATABASES = base_de_datos(_datos["base_datos"])
    ALLOWED_HOSTS = list(_datos.get("hosts", []))
    PROXIES_CONFIABLES = list(_datos.get("proxies_confiables", []))
    RUTA_LLAVE_LICENCIAS = str(_datos.get("llave_licencias") or instancia.carpeta() / instancia.LLAVE)
