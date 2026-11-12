import importlib
import sys
from datetime import timedelta

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Evento
from configuracion.models import Parametro
from cuentas.models import Delegacion, Dispositivo, PermisoRol, Rol
from proyecto import instancia
from solicitudes.models import IntentoCodigo, Solicitud
from titulares.models import Titular

from .conftest import CONTRASENA, cliente, codigo_actual, equipo_aprobado, nuevo_usuario
from .test_endurecimiento import datos_alta, solicitud_de_alta


@pytest.fixture(autouse=True)
def limpiar_cache():
    cache.clear()
    yield
    cache.clear()


def fallar_codigos(c, autorizador, veces, desde=0):
    for n in range(veces):
        solicitud = solicitud_de_alta(c, desde + n)
        c.post(reverse("solicitudes:codigo", args=[solicitud.pk]), {"autorizador": str(autorizador.pk), "codigo": "000000"})


def test_x_forwarded_for_de_origen_no_confiable_se_ignora(personas):
    externo = Client(REMOTE_ADDR="10.0.0.5")
    externo.cookies[settings.COOKIE_DISPOSITIVO] = equipo_aprobado()
    externo.post(reverse("entrar"), {"usuario": "nadie", "contrasena": "x"}, HTTP_X_FORWARDED_FOR="1.2.3.4")
    assert Evento.objects.filter(accion="inicio_sesion_fallido").latest("id").ip == "10.0.0.5"
    proxy = cliente()
    proxy.post(reverse("entrar"), {"usuario": "nadie", "contrasena": "x"}, HTTP_X_FORWARDED_FOR="9.9.9.9, 192.168.1.20")
    assert Evento.objects.filter(accion="inicio_sesion_fallido").latest("id").ip == "192.168.1.20"
    proxy.post(reverse("entrar"), {"usuario": "nadie", "contrasena": "x"}, HTTP_X_FORWARDED_FOR="no-es-ip")
    assert Evento.objects.filter(accion="inicio_sesion_fallido").latest("id").ip == "127.0.0.1"
    Client(REMOTE_ADDR="10.0.0.6").get("/", HTTP_X_FORWARDED_FOR="5.5.5.5")
    Client().get("/", HTTP_X_FORWARDED_FOR="192.168.1.30")
    ips = set(Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).values_list("ip", flat=True))
    assert {"10.0.0.6", "192.168.1.30"} <= ips and "5.5.5.5" not in ips


def test_tope_de_altas_pendientes_por_capturista(personas):
    Parametro.objects.create(clave="maximo_altas_pendientes_por_capturista", valor="2")
    op = cliente(personas["op"])
    solicitud_de_alta(op, 1)
    solicitud_de_alta(op, 2)
    respuesta = op.post(reverse("titulares:nuevo"), datos_alta(3))
    assert respuesta.status_code == 429 and "altas pendientes" in respuesta.content.decode()
    assert Titular.objects.filter(creado_por=personas["op"]).count() == 2
    assert Evento.objects.filter(accion="alta_rechazada_por_tope").exists()
    assert cliente(personas["op2"]).post(reverse("titulares:nuevo"), datos_alta(4)).status_code == 302


def test_autorizador_ve_el_bloqueo_al_iniciar_sesion(personas):
    fallar_codigos(cliente(personas["op"]), personas["sup"], 5)
    assert IntentoCodigo.objects.filter(tipo=IntentoCodigo.BLOQUEO, autorizador=personas["sup"]).exists()
    entrada = cliente()
    entrada.post(reverse("entrar"), {"usuario": "supervision", "contrasena": CONTRASENA})
    respuesta = entrada.post(reverse("entrar_codigo"), {"codigo": codigo_actual(personas["sup"])})
    assert respuesta.url == reverse("autorizaciones")
    pagina = entrada.get(reverse("autorizaciones")).content.decode()
    assert "Códigos erróneos a tu nombre" in pagina
    aviso = IntentoCodigo.objects.filter(tipo=IntentoCodigo.BLOQUEO).first()
    assert cliente(personas["sup2"]).post(reverse("aviso_enterado", args=[aviso.pk])).status_code == 404
    entrada.post(reverse("aviso_enterado", args=[aviso.pk]))
    aviso.refresh_from_db()
    assert aviso.visto
    personas["sup"].refresh_from_db()
    assert personas["sup"].intentos_fallidos == 0 and personas["sup"].bloqueado_hasta is None


def test_limite_por_autorizador_objetivo(personas):
    fallar_codigos(cliente(personas["op"]), personas["sup"], 3)
    fallar_codigos(cliente(personas["op2"]), personas["sup"], 2, desde=10)
    tercero = nuevo_usuario("operacion3", personas["op"].rol)
    c = cliente(tercero)
    solicitud = solicitud_de_alta(c, 20)
    c.post(reverse("solicitudes:codigo", args=[solicitud.pk]), {"autorizador": str(personas["sup"].pk), "codigo": codigo_actual(personas["sup"])})
    solicitud.refresh_from_db()
    assert solicitud.estado == Solicitud.PENDIENTE
    assert Evento.objects.filter(accion="codigo_bloqueado", datos__motivo="autorizador").exists()


def test_bloqueo_de_codigo_vence_en_una_hora(personas):
    op = cliente(personas["op"])
    fallar_codigos(op, personas["sup"], 5)
    IntentoCodigo.objects.update(momento=timezone.now() - timedelta(hours=1, minutes=1))
    solicitud = solicitud_de_alta(op, 30)
    op.post(reverse("solicitudes:codigo", args=[solicitud.pk]), {"autorizador": str(personas["sup"].pk), "codigo": codigo_actual(personas["sup"])})
    solicitud.refresh_from_db()
    assert solicitud.estado == Solicitud.APROBADA


def test_tope_por_solicitud_se_conserva(personas):
    Parametro.objects.create(clave="intentos_codigo_por_hora", valor="100")
    op = cliente(personas["op"])
    solicitud = solicitud_de_alta(op, 40)
    for _ in range(5):
        op.post(reverse("solicitudes:codigo", args=[solicitud.pk]), {"autorizador": str(personas["sup"].pk), "codigo": "000000"})
    op.post(reverse("solicitudes:codigo", args=[solicitud.pk]), {"autorizador": str(personas["sup"].pk), "codigo": codigo_actual(personas["sup"])})
    solicitud.refresh_from_db()
    assert solicitud.estado == Solicitud.PENDIENTE
    assert Evento.objects.filter(accion="codigo_bloqueado", datos__motivo="solicitud").exists()


def test_pendientes_viejos_se_depuran_y_tope_muestra_aviso(personas):
    viejo = Dispositivo.objects.create(hash_credencial="v" * 64, codigo="VIEJO1")
    Dispositivo.objects.filter(pk=viejo.pk).update(creado=timezone.now() - timedelta(hours=25))
    Parametro.objects.create(clave="maximo_equipos_pendientes", valor="2")
    Client().get("/")
    assert not Dispositivo.objects.filter(pk=viejo.pk).exists()
    Client().get("/")
    respuesta = Client().get("/")
    assert respuesta.status_code == 403
    texto = respuesta.content.decode()
    assert "Avisa a Supervisión" in texto and settings.COOKIE_DISPOSITIVO not in respuesta.cookies
    assert Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).count() == 2


def test_descartar_pendientes(personas):
    Client().get("/")
    Client().get("/")
    assert cliente(personas["op"]).post(reverse("dispositivos_descartar")).status_code == 403
    assert Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).count() == 2
    cliente(personas["sup"]).post(reverse("dispositivos_descartar"))
    assert not Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).exists()
    assert Dispositivo.objects.filter(estado=Dispositivo.APROBADO).exists()
    assert Evento.objects.get(accion="dispositivos_descartados").datos["cantidad"] == 2


def _rol(nombre, permisos):
    rol = Rol.objects.create(nombre=nombre, nivel=2)
    for permiso in permisos:
        PermisoRol.objects.create(rol=rol, permiso=permiso)
    return rol


def test_permisos_delegados_no_cuentan_para_otorgar(personas, roles):
    limitado = nuevo_usuario("limitado", _rol("Personal", ["administrar_usuarios", "ver_titulares"]))
    Delegacion.objects.create(otorgante=personas["sup"], receptor=limitado, permiso="aprobar_solicitudes", usos_maximos=5)
    aprobador = _rol("Aprobador", ["aprobar_solicitudes"])
    lectura = _rol("Lectura", ["ver_titulares"])
    c = cliente(limitado)
    c.post(reverse("usuario_nuevo"), {"usuario": "nuevo1", "nombre": "N", "rol": aprobador.pk, "contrasena1": CONTRASENA, "contrasena2": CONTRASENA})
    assert not aprobador.usuarios.exists()
    assert Evento.objects.filter(accion="escalada_rechazada", datos__motivo="crear_usuario_con_rol_superior").exists()
    c.post(reverse("usuario_nuevo"), {"usuario": "nuevo2", "nombre": "N", "rol": lectura.pk, "contrasena1": CONTRASENA, "contrasena2": CONTRASENA})
    assert lectura.usuarios.filter(usuario="nuevo2").exists()


def test_escaladas_quedan_auditadas(personas, roles):
    limitado = nuevo_usuario("limitado", _rol("Personal", ["administrar_usuarios", "administrar_roles"]))
    c = cliente(limitado)
    assert c.get(reverse("usuario_editar", args=[personas["dir"].pk])).status_code == 403
    assert c.get(reverse("rol_editar", args=[roles["Dirección"].pk])).status_code == 403
    motivos = set(Evento.objects.filter(accion="escalada_rechazada").values_list("datos__motivo", flat=True))
    assert {"editar_usuario_superior", "editar_rol_superior"} <= motivos


def ajustes_frescos():
    sys.modules.pop("proyecto.ajustes", None)
    return importlib.import_module("proyecto.ajustes")


def test_hsts_y_proxies_con_https(tmp_path, monkeypatch):
    monkeypatch.setenv("COBRO_INSTANCIA", str(tmp_path))
    datos = instancia.nueva(https=True)
    assert datos["proxies_confiables"] == ["127.0.0.1", "::1"]
    instancia.escribir(datos)
    recargado = ajustes_frescos()
    assert recargado.SECURE_HSTS_SECONDS == 31536000
    assert recargado.PROXIES_CONFIABLES == ["127.0.0.1", "::1"]
    instancia.reemplazar(dict(datos, https=False))
    assert not hasattr(ajustes_frescos(), "SECURE_HSTS_SECONDS")
    sys.modules.pop("proyecto.ajustes", None)


def test_cabeceras_de_proxy_solo_desde_proxies_confiables(personas):
    with override_settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"), SECURE_HSTS_SECONDS=31536000):
        confiable = cliente(personas["op"]).get(reverse("inicio"), HTTP_X_FORWARDED_PROTO="https")
        assert confiable.headers.get("Strict-Transport-Security") == "max-age=31536000"
        externo = Client(REMOTE_ADDR="10.0.0.5")
        externo.cookies[settings.COOKIE_DISPOSITIVO] = equipo_aprobado()
        respuesta = externo.get(reverse("entrar"), HTTP_X_FORWARDED_PROTO="https")
        assert "Strict-Transport-Security" not in respuesta.headers
