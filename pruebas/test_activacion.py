import re
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Evento
from cuentas.models import CodigoActivacion, PermisoRol, Rol, Usuario

from .conftest import CONTRASENA, cliente, codigo_actual, nuevo_usuario

NUEVA = "Mi-propia-clave-2026"


@pytest.fixture(autouse=True)
def limpiar_cache():
    cache.clear()
    yield
    cache.clear()


def crear_cuenta(admin, usuario, rol):
    respuesta = cliente(admin).post(reverse("usuario_nuevo"), {"usuario": usuario, "nombre": f"Persona {usuario}", "rol": rol.pk})
    assert respuesta.status_code == 200
    codigo = re.search(r'<p class="codigo-equipo">([A-Z0-9]{5}-[A-Z0-9]{5})</p>', respuesta.content.decode()).group(1)
    return Usuario.objects.get(usuario=usuario), codigo


def activar(c, usuario, codigo, clave=NUEVA):
    return c.post(reverse("activar"), {"usuario": usuario, "codigo": codigo, "contrasena1": clave, "contrasena2": clave})


def test_flujo_completo_de_activacion(personas, roles):
    nuevo, codigo = crear_cuenta(personas["dir"], "nueva", roles["Operación"])
    assert not nuevo.has_usable_password()
    registro = CodigoActivacion.objects.get(usuario=nuevo)
    assert codigo.replace("-", "") not in registro.hash_codigo and len(registro.hash_codigo) == 64
    assert set(codigo.replace("-", "")) <= set("ABCDEFGHJKMNPQRSTUVWXYZ23456789")
    evento = Evento.objects.get(accion="codigo_activacion_generado")
    assert evento.usuario == personas["dir"] and evento.datos["para"] == "nueva"
    c = cliente()
    assert "Tengo un código de activación" in c.get(reverse("entrar")).content.decode()
    respuesta = activar(c, "nueva", codigo.lower())
    assert respuesta.status_code == 302 and respuesta.url == reverse("inicio")
    assert c.get(reverse("titulares:lista")).status_code == 200
    nuevo.refresh_from_db()
    assert nuevo.check_password(NUEVA)
    assert Evento.objects.get(accion="cuenta_activada").equipo is not None
    otro = cliente()
    assert activar(otro, "nueva", codigo, "Otra-clave-distinta-1").status_code == 200
    nuevo.refresh_from_db()
    assert nuevo.check_password(NUEVA)


def test_rol_con_autenticador_pasa_a_darlo_de_alta(personas, roles):
    nuevo, codigo = crear_cuenta(personas["dir"], "supnueva", roles["Supervisión"])
    c = cliente()
    activar(c, "supnueva", codigo)
    assert c.get(reverse("titulares:lista")).url == reverse("totp")


def test_codigo_caducado_rechazado(personas, roles):
    nuevo, codigo = crear_cuenta(personas["dir"], "tarde", roles["Operación"])
    CodigoActivacion.objects.filter(usuario=nuevo).update(caduca=timezone.now() - timedelta(minutes=1))
    respuesta = activar(cliente(), "tarde", codigo)
    assert respuesta.status_code == 200 and "no válidos" in respuesta.content.decode()
    nuevo.refresh_from_db()
    assert not nuevo.has_usable_password() and nuevo.intentos_fallidos == 1
    assert Evento.objects.filter(accion="codigo_activacion_caducado").exists()


def test_mensaje_no_revela_si_el_usuario_existe(personas, roles):
    crear_cuenta(personas["dir"], "existe", roles["Operación"])
    uno = activar(cliente(), "existe", "AAAAA-AAAAA").content.decode()
    dos = activar(cliente(), "noexiste", "AAAAA-AAAAA").content.decode()
    assert "no válidos" in uno and "no válidos" in dos


def test_fallos_cuentan_para_bloqueo_y_limite_por_equipo(personas, roles):
    nuevo, codigo = crear_cuenta(personas["dir"], "bloq", roles["Operación"])
    c = cliente()
    for _ in range(5):
        activar(c, "bloq", "BBBBB-BBBBB")
    nuevo.refresh_from_db()
    assert nuevo.esta_bloqueado()
    assert activar(c, "bloq", codigo).status_code == 200
    nuevo.refresh_from_db()
    assert not nuevo.has_usable_password()
    for _ in range(30):
        activar(c, "nadie", "CCCCC-CCCCC")
    assert activar(c, "nadie", "CCCCC-CCCCC").status_code == 429


def test_contrasena_debil_no_quema_el_codigo(personas, roles):
    nuevo, codigo = crear_cuenta(personas["dir"], "debil", roles["Operación"])
    c = cliente()
    assert activar(c, "debil", codigo, "debil").status_code == 200
    assert activar(c, "debil", codigo).status_code == 302


def test_restablecer_acceso_cierra_sesiones(personas, roles):
    sesion_op = cliente(personas["op"])
    assert sesion_op.get(reverse("titulares:lista")).status_code == 200
    respuesta = cliente(personas["dir"]).post(reverse("usuario_editar", args=[personas["op"].pk]), {"nombre": personas["op"].nombre, "rol": roles["Operación"].pk, "activo": "on", "restablecer_acceso": "on"})
    codigo = re.search(r'<p class="codigo-equipo">([A-Z0-9]{5}-[A-Z0-9]{5})</p>', respuesta.content.decode()).group(1)
    assert sesion_op.get(reverse("titulares:lista")).status_code == 302
    personas["op"].refresh_from_db()
    assert not personas["op"].check_password(CONTRASENA)
    assert Evento.objects.filter(accion="acceso_restablecido", datos__sesiones_cerradas=1).exists()
    assert activar(cliente(), "operacion", codigo).url == reverse("inicio")


def test_restablecer_invalida_codigos_anteriores(personas, roles):
    nuevo, primero = crear_cuenta(personas["dir"], "doble", roles["Operación"])
    cliente(personas["dir"]).post(reverse("usuario_editar", args=[nuevo.pk]), {"nombre": nuevo.nombre, "rol": roles["Operación"].pk, "activo": "on", "restablecer_acceso": "on"})
    assert activar(cliente(), "doble", primero).status_code == 200
    assert CodigoActivacion.objects.filter(usuario=nuevo, invalidado=True).count() == 1


def test_con_autenticador_activo_pide_codigo_tras_activar(personas, roles):
    respuesta = cliente(personas["dir"]).post(reverse("usuario_editar", args=[personas["sup"].pk]), {"nombre": personas["sup"].nombre, "rol": roles["Supervisión"].pk, "activo": "on", "restablecer_acceso": "on"})
    codigo = re.search(r'<p class="codigo-equipo">([A-Z0-9]{5}-[A-Z0-9]{5})</p>', respuesta.content.decode()).group(1)
    c = cliente()
    assert activar(c, "supervision", codigo).url == reverse("entrar_codigo")
    assert c.get(reverse("titulares:lista")).status_code == 302
    assert c.post(reverse("entrar_codigo"), {"codigo": codigo_actual(personas["sup"])}).url == reverse("inicio")


def test_administrador_no_fija_contrasenas_por_post(personas, roles):
    c = cliente(personas["dir"])
    c.post(reverse("usuario_nuevo"), {"usuario": "fija", "nombre": "F", "rol": roles["Operación"].pk, "contrasena1": "Fijada-por-admin-1", "contrasena2": "Fijada-por-admin-1", "password": "Fijada-por-admin-1"})
    creado = Usuario.objects.get(usuario="fija")
    assert not creado.has_usable_password()
    c.post(reverse("usuario_editar", args=[personas["op"].pk]), {"nombre": personas["op"].nombre, "rol": roles["Operación"].pk, "activo": "on", "contrasena_nueva": "Fijada-por-admin-1", "password": "Fijada-por-admin-1"})
    personas["op"].refresh_from_db()
    assert personas["op"].check_password(CONTRASENA)
    assert not personas["op"].check_password("Fijada-por-admin-1")


def test_no_se_genera_codigo_para_alguien_con_mas_permisos(personas, roles):
    rol = Rol.objects.create(nombre="SoloUsuarios")
    PermisoRol.objects.create(rol=rol, permiso="administrar_usuarios")
    limitado = nuevo_usuario("limitado", rol)
    respuesta = cliente(limitado).post(reverse("usuario_editar", args=[personas["sup"].pk]), {"nombre": "x", "rol": roles["Supervisión"].pk, "activo": "on", "restablecer_acceso": "on"})
    assert respuesta.status_code == 403
    assert not CodigoActivacion.objects.filter(usuario=personas["sup"]).exists()
