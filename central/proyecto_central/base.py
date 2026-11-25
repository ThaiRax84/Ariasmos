from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

DEBUG = False

INSTALLED_APPS = ["emision", "mensajeria"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "proyecto_central.urls"
WSGI_APPLICATION = "proyecto_central.wsgi.application"

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True
APPEND_SLASH = False

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "no-referrer"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 32 * 1024


def base_de_datos(ruta):
    return {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ruta,
            "OPTIONS": {
                "timeout": 30,
                "transaction_mode": "IMMEDIATE",
                "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=30000;",
            },
        }
    }
