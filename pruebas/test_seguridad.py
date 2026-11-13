from datetime import timedelta

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Evento
from cuentas.models import Dispositivo, Usuario
from cuentas.servicios import hash_credencial

from .conftest import CONTRASENA, cliente, codigo_actual


@pytest.fixture(autouse=True)
def limpiar_cache():
    cache.clear()
    yield
    cache.clear()


def test_equipo_nuevo_queda_pendiente_y_bloqueado(personas):
    c = Client()
    respuesta = c.get(reverse("entrar"))
    assert respuesta.status_code == 302 and respuesta.url == reverse("dispositivo_pendiente")
    galleta = respuesta.cookies[settings.COOKIE_DISPOSITIVO]
    assert galleta["httponly"] and galleta["secure"] and galleta["samesite"] == "Strict"
    dispositivo = Dispositivo.objects.get(hash_credencial=hash_credencial(galleta.value))
    assert dispositivo.estado == Dispositivo.PENDIENTE
    assert galleta.value not in str(Dispositivo.objects.values_list("hash_credencial", flat=True))
    pagina = c.get(reverse("dispositivo_pendiente"))
    assert pagina.status_code == 403 and dispositivo.codigo in pagina.content.decode()
    assert c.post(reverse("entrar"), {"usuario": "direccion", "contrasena": CONTRASENA}).url == reverse("dispositivo_pendiente")
    c.force_login(personas["dir"], backend="django.contrib.auth.backends.ModelBackend")
    assert c.get(reverse("titulares:lista")).url == reverse("dispositivo_pendiente")

    supervisor = cliente(personas["sup"])
    supervisor.post(reverse("dispositivo_aprobar", args=[dispositivo.pk]), {"nombre": "Caja"})
    dispositivo.refresh_from_db()
    assert dispositivo.estado == Dispositivo.APROBADO and dispositivo.aprobado_por == personas["sup"]
    assert c.get(reverse("entrar")).status_code == 200

    supervisor.post(reverse("dispositivo_revocar", args=[dispositivo.pk]))
    dispositivo.refresh_from_db()
    assert dispositivo.estado == Dispositivo.REVOCADO
    assert c.get(reverse("entrar")).url == reverse("dispositivo_pendiente")
    assert Evento.objects.filter(accion="dispositivo_revocado").exists()


def test_operacion_no_aprueba_equipos(personas):
    pendiente = Dispositivo.objects.create(hash_credencial="y" * 64, codigo="ZZZZZZ")
    assert cliente(personas["op"]).post(reverse("dispositivo_aprobar", args=[pendiente.pk]), {"nombre": "x"}).status_code == 403
    pendiente.refresh_from_db()
    assert pendiente.estado == Dispositivo.PENDIENTE


def test_credencial_inventada_no_entra(personas):
    c = Client()
    c.cookies[settings.COOKIE_DISPOSITIVO] = "inventada"
    assert c.get(reverse("entrar")).url == reverse("dispositivo_pendiente")


def test_bloqueo_progresivo_por_intentos(personas):
    c = cliente()
    for _ in range(5):
        respuesta = c.post(reverse("entrar"), {"usuario": "operacion", "contrasena": "equivocada"})
        assert respuesta.status_code == 200
    usuario = Usuario.objects.get(usuario="operacion")
    assert usuario.esta_bloqueado()
    primer_bloqueo = usuario.bloqueado_hasta
    respuesta = c.post(reverse("entrar"), {"usuario": "operacion", "contrasena": CONTRASENA})
    assert respuesta.status_code == 200 and "_auth_user_id" not in c.session
    Usuario.objects.filter(pk=usuario.pk).update(bloqueado_hasta=timezone.now() - timedelta(seconds=1))
    c.post(reverse("entrar"), {"usuario": "operacion", "contrasena": "otra-vez-mal"})
    usuario.refresh_from_db()
    assert usuario.bloqueado_hasta - timezone.now() > (primer_bloqueo - timezone.now()) + timedelta(seconds=30)
    Usuario.objects.filter(pk=usuario.pk).update(bloqueado_hasta=None)
    respuesta = c.post(reverse("entrar"), {"usuario": "operacion", "contrasena": CONTRASENA})
    assert respuesta.status_code == 302
    usuario.refresh_from_db()
    assert usuario.intentos_fallidos == 0
    assert Evento.objects.filter(accion="cuenta_bloqueada").count() >= 2


def test_codigos_fallidos_tambien_bloquean(personas):
    c = cliente()
    for _ in range(5):
        c.post(reverse("entrar"), {"usuario": "supervision", "contrasena": CONTRASENA})
        c.post(reverse("entrar_codigo"), {"codigo": "000000"})
    assert Usuario.objects.get(usuario="supervision").esta_bloqueado()


def test_inicio_con_totp_y_reuso_rechazado(personas):
    c = cliente()
    assert c.post(reverse("entrar"), {"usuario": "supervision", "contrasena": CONTRASENA}).url == reverse("entrar_codigo")
    codigo = codigo_actual(personas["sup"])
    assert c.post(reverse("entrar_codigo"), {"codigo": codigo}).url == reverse("inicio")
    otro = cliente()
    otro.post(reverse("entrar"), {"usuario": "supervision", "contrasena": CONTRASENA})
    assert otro.post(reverse("entrar_codigo"), {"codigo": codigo}).status_code == 200
    assert "_auth_user_id" not in otro.session


def test_rol_que_aprueba_debe_activar_totp(personas, roles):
    sin = Usuario.objects.create_user("sintotp", CONTRASENA, nombre="Sin", rol=roles["Supervisión"])
    c = cliente(sin)
    assert c.get(reverse("titulares:lista")).url == reverse("totp")
    pagina = c.get(reverse("totp")).content.decode()
    assert 'class="segno"' in pagina and "Introducir clave manualmente" in pagina


def test_cierre_por_inactividad(personas):
    c = cliente(personas["op"])
    sesion = c.session
    sesion["ultima_actividad"] = timezone.now().timestamp() - (personas["op"].rol.minutos_inactividad * 60 + 5)
    sesion.save()
    respuesta = c.get(reverse("titulares:lista"))
    assert respuesta.status_code == 302 and respuesta.url == reverse("entrar")
    assert Evento.objects.filter(accion="cierre_por_inactividad").exists()


def test_reingreso_para_accion_delicada(personas):
    c = cliente(personas["dir"], reingreso=False)
    respuesta = c.get(reverse("usuario_nuevo"))
    assert respuesta.status_code == 302 and respuesta.url.startswith(reverse("confirmar"))
    c.post(reverse("confirmar") + "?siguiente=/cuentas/usuarios/nuevo/", {"contrasena": "mala"})
    assert c.get(reverse("usuario_nuevo")).status_code == 302
    respuesta = c.post(reverse("confirmar"), {"contrasena": CONTRASENA, "siguiente": reverse("usuario_nuevo")})
    assert respuesta.url == reverse("usuario_nuevo")
    assert c.get(reverse("usuario_nuevo")).status_code == 200


def test_redireccion_externa_ignorada(personas):
    c = cliente(personas["dir"], reingreso=False)
    respuesta = c.post(reverse("confirmar"), {"contrasena": CONTRASENA, "siguiente": "https://otro.ejemplo/"})
    assert respuesta.url == reverse("inicio")


def test_cabeceras_de_seguridad(personas):
    respuesta = cliente(personas["op"]).get(reverse("inicio"))
    csp = respuesta.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp and "http" not in csp
    assert respuesta.headers["X-Frame-Options"] == "DENY"
    assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
    assert respuesta.headers["Cache-Control"] == "no-store"
    assert "<script>" not in respuesta.content.decode()


def test_no_se_queda_sin_administradores(personas):
    c = cliente(personas["dir"])
    rol = personas["dir"].rol
    permisos = [p for p in rol.permisos() if p != "administrar_roles"]
    c.post(reverse("rol_editar", args=[rol.pk]), {"nombre": rol.nombre, "nivel": 3, "minutos_inactividad": 15, "requiere_totp": "on", "permisos": permisos})
    assert "administrar_roles" in rol.permisos()
    c.post(reverse("usuario_editar", args=[personas["dir"].pk]), {"nombre": "x", "rol": rol.pk})
    personas["dir"].refresh_from_db()
    assert personas["dir"].activo


def test_cambio_de_permisos_auditado(personas):
    c = cliente(personas["dir"])
    rol = personas["op"].rol
    permisos = sorted(rol.permisos() | {"administrar_conceptos"})
    c.post(reverse("rol_editar", args=[rol.pk]), {"nombre": rol.nombre, "nivel": 1, "minutos_inactividad": 30, "permisos": permisos})
    assert "administrar_conceptos" in rol.permisos()
    evento = Evento.objects.filter(accion="rol_cambiado").latest("id")
    antes, despues = evento.datos["cambios"]["permisos"]
    assert "administrar_conceptos" in despues and "administrar_conceptos" not in antes


def test_limite_por_ip(personas):
    c = cliente()
    for _ in range(30):
        c.post(reverse("entrar"), {"usuario": "nadie", "contrasena": "x"})
    assert c.post(reverse("entrar"), {"usuario": "nadie", "contrasena": "x"}).status_code == 429
