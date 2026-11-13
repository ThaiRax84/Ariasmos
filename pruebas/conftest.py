import secrets

import pytest
from django.conf import settings
from django.test import Client
from django.utils import timezone

from configuracion import plantillas
from configuracion.models import Negocio
from cuentas import secretos
from cuentas.models import Dispositivo, Rol, Usuario
from cuentas.servicios import hash_credencial
from nucleo import totp

CONTRASENA = "Contrasena-de-prueba-2026"


def configurar(plantilla="escuela"):
    Negocio.objects.update_or_create(pk=1, defaults={"nombre": "Negocio de prueba", "nota_ficha": "Instrucciones de prueba", "plantilla": plantilla, "configurado": True})
    plantillas.cargar(plantilla)
    return {rol.nombre: rol for rol in Rol.objects.all()}


def nuevo_usuario(usuario, rol, con_totp=None):
    creado = Usuario.objects.create_user(usuario, CONTRASENA, nombre=f"Persona {usuario}", rol=rol)
    if con_totp is None:
        con_totp = rol.requiere_totp if rol else False
    if con_totp:
        secretos.guardar(creado, totp.generar_secreto())
        creado.totp_confirmado = True
        creado.save()
    return creado


def equipo_aprobado():
    credencial = secrets.token_urlsafe(32)
    Dispositivo.objects.create(hash_credencial=hash_credencial(credencial), codigo="PRUEBA", estado=Dispositivo.APROBADO, aprobado_en=timezone.now())
    return credencial


def cliente(usuario=None, credencial=None, reingreso=True):
    c = Client()
    c.cookies[settings.COOKIE_DISPOSITIVO] = credencial or equipo_aprobado()
    if usuario is not None:
        c.force_login(usuario, backend="django.contrib.auth.backends.ModelBackend")
        if reingreso:
            sesion = c.session
            sesion["reingreso_en"] = timezone.now().timestamp()
            sesion.save()
    return c


def codigo_actual(usuario, desfase=0):
    return totp.codigo(secretos.leer(usuario), totp.paso_actual() + desfase)


@pytest.fixture(autouse=True)
def ancla_temporal(settings, tmp_path):
    settings.RUTA_ANCLA_AUDITORIA = str(tmp_path / "ancla_auditoria.json")
    return settings.RUTA_ANCLA_AUDITORIA


@pytest.fixture
def roles(db):
    return configurar("escuela")


@pytest.fixture
def personas(roles):
    return {
        "op": nuevo_usuario("operacion", roles["Operación"]),
        "op2": nuevo_usuario("operacion2", roles["Operación"]),
        "sup": nuevo_usuario("supervision", roles["Supervisión"]),
        "sup2": nuevo_usuario("supervision2", roles["Supervisión"]),
        "dir": nuevo_usuario("direccion", roles["Dirección"]),
    }


@pytest.fixture
def credencial(db):
    return equipo_aprobado()
