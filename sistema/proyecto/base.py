from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SISTEMA = RAIZ / "sistema"
PLANTILLAS_NEGOCIO = RAIZ / "plantillas"

DEBUG = False

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "auditoria",
    "configuracion",
    "cuentas",
    "titulares",
    "solicitudes",
    "cobros",
    "banco",
    "caja",
]

MIDDLEWARE = [
    "proyecto.seguridad.CabecerasProxy",
    "django.middleware.security.SecurityMiddleware",
    "proyecto.seguridad.CabecerasSeguridad",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "configuracion.middleware.Instalacion",
    "cuentas.middleware.ControlDispositivo",
    "cuentas.middleware.ControlSesion",
]

ROOT_URLCONF = "proyecto.urls"
WSGI_APPLICATION = "proyecto.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [SISTEMA / "plantillas_html"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "configuracion.contexto.general",
            ],
        },
    },
]

AUTH_USER_MODEL = "cuentas.Usuario"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
LOGIN_URL = "entrar"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [SISTEMA / "estaticos"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_NAME = "sesion"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_NAME = "csrf"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

PROXIES_CONFIABLES = ["127.0.0.1", "::1"]

COOKIE_DISPOSITIVO = "dispositivo"
COOKIE_DISPOSITIVO_SEGURA = True
EDAD_COOKIE_DISPOSITIVO = 60 * 60 * 24 * 365 * 5

FILE_UPLOAD_HANDLERS = ["proyecto.subidas.SubidaLimitada"]
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"


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
