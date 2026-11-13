import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from auditoria.models import Evento
from cuentas import secretos
from cuentas.models import CodigoActivacion, Dispositivo, PermisoRol, Rol
from cuentas.permisos import PERMISOS
from solicitudes.models import Solicitud
from titulares.models import CampoContacto, RelacionContacto

from .conftest import CONTRASENA, cliente, codigo_actual, equipo_aprobado, nuevo_usuario


@pytest.fixture(autouse=True)
def limpiar_cache():
    cache.clear()
    yield
    cache.clear()


def datos_alta(n):
    relacion = RelacionContacto.objects.first()
    datos = {
        "nombre": f"Nombre{n}",
        "apellidos": "Apellido",
        "constancia_consentimiento": "on",
        "contacto_nombre": "Responsable",
        "contacto_relacion": relacion.pk if relacion else "",
    }
    for campo in CampoContacto.objects.filter(activo=True):
        if campo.tipo == "telefono":
            datos[f"campo_{campo.pk}"] = "5512345678"
        elif campo.tipo == "correo":
            datos[f"campo_{campo.pk}"] = "persona@ejemplo.mx"
        else:
            datos[f"campo_{campo.pk}"] = "dato"
    return datos


def solicitud_de_alta(c, n):
    respuesta = c.post(reverse("titulares:nuevo"), datos_alta(n))
    assert respuesta.status_code == 302
    return Solicitud.objects.order_by("-id").first()


def test_codigos_erroneos_se_limitan_por_persona_y_no_por_solicitud(personas):
    op = cliente(personas["op"])
    sup = personas["sup"]
    for n in range(5):
        solicitud = solicitud_de_alta(op, n)
        op.post(reverse("solicitudes:codigo", args=[solicitud.pk]), {"autorizador": str(sup.pk), "codigo": "000000"})
    cache.clear()
    otra = solicitud_de_alta(op, 50)
    op.post(reverse("solicitudes:codigo", args=[otra.pk]), {"autorizador": str(sup.pk), "codigo": codigo_actual(sup)})
    otra.refresh_from_db()
    sup.refresh_from_db()
    assert otra.estado == Solicitud.PENDIENTE
    assert sup.bloqueado_hasta is None
    assert Evento.objects.filter(accion="codigo_bloqueado").exists()


def test_el_limite_de_codigos_no_afecta_a_otra_persona(personas):
    op = cliente(personas["op"])
    sup = personas["sup"]
    for n in range(5):
        solicitud = solicitud_de_alta(op, n)
        op.post(reverse("solicitudes:codigo", args=[solicitud.pk]), {"autorizador": str(sup.pk), "codigo": "000000"})
    op2 = cliente(personas["op2"])
    ajena = solicitud_de_alta(op2, 70)
    op2.post(reverse("solicitudes:codigo", args=[ajena.pk]), {"autorizador": str(personas["sup2"].pk), "codigo": codigo_actual(personas["sup2"])})
    ajena.refresh_from_db()
    assert ajena.estado == Solicitud.APROBADA


def test_equipos_pendientes_tienen_tope(personas):
    antes = Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).count()
    for _ in range(120):
        respuesta = Client().get("/")
        assert respuesta.status_code in (302, 403, 429)
    creados = Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).count() - antes
    assert creados <= 50


def test_limite_de_inicio_de_sesion_es_por_equipo(personas):
    atacante = cliente()
    for _ in range(40):
        atacante.post(reverse("entrar"), {"usuario": "no-existe", "contrasena": "x"})
    assert atacante.post(reverse("entrar"), {"usuario": "no-existe", "contrasena": "x"}).status_code == 429
    legitimo = cliente()
    respuesta = legitimo.post(reverse("entrar"), {"usuario": "operacion", "contrasena": CONTRASENA})
    assert respuesta.status_code == 302


def test_sesion_no_sirve_en_otro_equipo(personas):
    original = cliente(personas["op"])
    sesion = original.cookies[settings.SESSION_COOKIE_NAME].value
    assert original.get(reverse("titulares:lista")).status_code == 200
    otro = Client()
    otro.cookies[settings.COOKIE_DISPOSITIVO] = equipo_aprobado()
    otro.cookies[settings.SESSION_COOKIE_NAME] = sesion
    respuesta = otro.get(reverse("titulares:lista"))
    assert respuesta.status_code == 302 and reverse("entrar") in respuesta.url
    assert Evento.objects.filter(accion="sesion_en_otro_equipo").exists()


def _rol_con(nombre, permisos, totp=False):
    rol = Rol.objects.create(nombre=nombre, nivel=2, requiere_totp=totp)
    for permiso in permisos:
        PermisoRol.objects.create(rol=rol, permiso=permiso)
    return rol


def test_nadie_se_asigna_un_rol_con_mas_permisos(personas, roles):
    limitado = nuevo_usuario("limitado", _rol_con("Personal", ["administrar_usuarios"]))
    c = cliente(limitado)
    c.post(reverse("usuario_editar", args=[limitado.pk]), {"nombre": limitado.nombre, "rol": roles["Dirección"].pk, "activo": "on"})
    limitado.refresh_from_db()
    assert limitado.rol.nombre == "Personal"
    c.post(reverse("usuario_editar", args=[personas["op"].pk]), {"nombre": "x", "rol": roles["Dirección"].pk, "activo": "on"})
    personas["op"].refresh_from_db()
    assert personas["op"].rol.nombre == "Operación"
    c.post(reverse("usuario_nuevo"), {"usuario": "complice", "nombre": "Complice", "rol": roles["Dirección"].pk})
    assert not roles["Dirección"].usuarios.filter(usuario="complice").exists()


def test_nadie_toma_la_cuenta_de_alguien_con_mas_permisos(personas, roles):
    limitado = nuevo_usuario("limitado", _rol_con("Personal", ["administrar_usuarios"]))
    c = cliente(limitado)
    direccion = personas["dir"]
    secreto = secretos.leer(direccion)
    c.post(
        reverse("usuario_editar", args=[direccion.pk]),
        {"nombre": direccion.nombre, "rol": roles["Dirección"].pk, "activo": "on", "restablecer_acceso": "on", "reiniciar_totp": "on"},
    )
    direccion.refresh_from_db()
    assert direccion.check_password(CONTRASENA)
    assert not CodigoActivacion.objects.filter(usuario=direccion).exists()
    assert secretos.leer(direccion) == secreto and direccion.totp_confirmado
    c.post(reverse("usuario_editar", args=[direccion.pk]), {"nombre": direccion.nombre, "rol": roles["Dirección"].pk})
    direccion.refresh_from_db()
    assert direccion.activo


def test_nadie_agrega_a_un_rol_permisos_que_no_tiene(personas, roles):
    rol = _rol_con("Configurador", ["administrar_roles"], totp=True)
    usuario = nuevo_usuario("configurador", rol)
    c = cliente(usuario)
    c.post(reverse("rol_editar", args=[rol.pk]), {"nombre": "Configurador", "nivel": 2, "minutos_inactividad": 30, "requiere_totp": "on", "permisos": list(PERMISOS)})
    assert rol.permisos() == {"administrar_roles"}
    c.post(reverse("rol_editar", args=[roles["Operación"].pk]), {"nombre": "Operación", "nivel": 1, "minutos_inactividad": 30, "requiere_totp": "on", "permisos": ["administrar_roles", "aprobar_solicitudes"]})
    assert "aprobar_solicitudes" not in roles["Operación"].permisos()
    c.post(reverse("rol_nuevo"), {"nombre": "Todo", "nivel": 3, "minutos_inactividad": 30, "requiere_totp": "on", "permisos": list(PERMISOS)})
    assert not Rol.objects.filter(nombre="Todo").exists()


def test_direccion_conserva_sus_facultades(personas, roles):
    c = cliente(personas["dir"])
    permisos = sorted(roles["Operación"].permisos() | {"ver_cortes"})
    c.post(reverse("rol_editar", args=[roles["Operación"].pk]), {"nombre": "Operación", "nivel": 1, "minutos_inactividad": 20, "permisos": permisos})
    roles["Operación"].refresh_from_db()
    assert roles["Operación"].minutos_inactividad == 20
    c.post(reverse("usuario_editar", args=[personas["op"].pk]), {"nombre": "Nuevo nombre", "rol": roles["Supervisión"].pk, "activo": "on"})
    personas["op"].refresh_from_db()
    assert personas["op"].rol.nombre == "Supervisión"
