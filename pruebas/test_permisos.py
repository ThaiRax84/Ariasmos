import pytest
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from django.utils import timezone

from cobros.models import ConceptoCobro, PlanCobro, ReglaRecargo
from cuentas.models import CodigoUsado, Delegacion, Dispositivo, Rol
from solicitudes.models import PoliticaAccion, Solicitud
from titulares.models import Agrupacion, Contacto, Titular
from titulares.servicios import crear_titular

from .conftest import cliente, configurar, nuevo_usuario

ROLES = ("Operación", "Supervisión", "Dirección")

PUBLICAS = {"entrar", "entrar_codigo", "dispositivo_pendiente", "asistente:inicio", "asistente:conceptos", "asistente:usuario", "asistente:codigo"}

SOLO_SESION = {"inicio", "salir", "confirmar", "totp", "contrasena", "autorizaciones", "revisar_autorizacion", "aviso_enterado"}

MATRIZ = {
    "titulares:lista": ("ver_titulares",),
    "titulares:nuevo": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:detalle": ("ver_titulares",),
    "titulares:ficha_pago": ("ver_titulares",),
    "titulares:editar": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:contacto_nuevo": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:contacto_editar": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:baja": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:reactivar": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:solicitar_alta": ("solicitar_alta_baja", "alta_baja_directa"),
    "solicitudes:bandeja": ("solicitar_alta_baja", "alta_baja_directa", "aprobar_solicitudes"),
    "solicitudes:detalle": ("solicitar_alta_baja", "alta_baja_directa", "aprobar_solicitudes"),
    "solicitudes:aprobar": ("aprobar_solicitudes",),
    "solicitudes:rechazar": ("aprobar_solicitudes",),
    "solicitudes:codigo": ("solicitar_alta_baja",),
    "solicitudes:politicas": ("administrar_politicas",),
    "solicitudes:politica_editar": ("administrar_politicas",),
    "usuarios": ("administrar_usuarios",),
    "usuario_nuevo": ("administrar_usuarios",),
    "usuario_editar": ("administrar_usuarios",),
    "roles": ("administrar_roles",),
    "rol_nuevo": ("administrar_roles",),
    "rol_editar": ("administrar_roles",),
    "dispositivos": ("aprobar_dispositivos",),
    "dispositivos_descartar": ("aprobar_dispositivos",),
    "dispositivo_aprobar": ("aprobar_dispositivos",),
    "dispositivo_revocar": ("aprobar_dispositivos",),
    "delegaciones": ("otorgar_delegaciones",),
    "delegacion_nueva": ("otorgar_delegaciones",),
    "delegacion_revocar": ("otorgar_delegaciones",),
    "cobros:conceptos": ("administrar_conceptos",),
    "cobros:concepto_nuevo": ("administrar_conceptos",),
    "cobros:concepto_editar": ("administrar_conceptos",),
    "cobros:reglas": ("administrar_conceptos",),
    "cobros:regla_nueva": ("administrar_conceptos",),
    "cobros:regla_editar": ("administrar_conceptos",),
    "cobros:planes": ("administrar_conceptos",),
    "cobros:plan_nuevo": ("administrar_conceptos",),
    "cobros:plan_editar": ("administrar_conceptos",),
    "configuracion:indice": ("administrar_configuracion",),
    "configuracion:negocio": ("administrar_configuracion",),
    "configuracion:vocabulario": ("administrar_configuracion",),
    "configuracion:parametros": ("administrar_configuracion",),
    "configuracion:catalogo": ("administrar_configuracion",),
    "configuracion:catalogo_nuevo": ("administrar_configuracion",),
    "configuracion:catalogo_editar": ("administrar_configuracion",),
    "auditoria:lista": ("ver_auditoria",),
    "auditoria:verificar": ("ver_auditoria",),
}

OBJETO_PROPIO = {"solicitudes:codigo": {"Operación"}, "solicitudes:detalle": None}


def nombres_de_rutas(patrones=None, prefijo=""):
    for patron in patrones if patrones is not None else get_resolver().url_patterns:
        if isinstance(patron, URLResolver):
            espacio = f"{patron.namespace}:" if patron.namespace else ""
            yield from nombres_de_rutas(patron.url_patterns, prefijo + espacio)
        elif isinstance(patron, URLPattern) and patron.name:
            yield prefijo + patron.name


def vista_de(nombre, kwargs):
    return get_resolver().resolve(reverse(nombre, kwargs=kwargs)).func


def test_toda_ruta_esta_clasificada():
    todas = set(nombres_de_rutas())
    clasificadas = PUBLICAS | SOLO_SESION | set(MATRIZ)
    assert todas == clasificadas, todas.symmetric_difference(clasificadas)


@pytest.fixture
def escenario(db):
    roles = configurar("escuela")
    usuarios = {nombre: nuevo_usuario(f"u{rol.nivel}", rol) for nombre, rol in roles.items()}
    titular = crear_titular(usuarios["Operación"], {"nombre": "Ana", "apellidos": "Prueba"}, contacto={"nombre": "Resp", "valores": {}})
    solicitud = Solicitud.objects.create(accion="alta", titular=titular, solicitante=usuarios["Operación"], caduca_en=timezone.now() + timezone.timedelta(days=1))
    otro = Rol.objects.create(nombre="Extra")
    dispositivo = Dispositivo.objects.create(hash_credencial="x" * 64, codigo="ABCDEF")
    delegacion = Delegacion.objects.create(otorgante=usuarios["Supervisión"], receptor=usuarios["Operación"], permiso="alta_baja_directa", usos_maximos=1)
    regla = ReglaRecargo.objects.create(nombre="Regla")
    plan = PlanCobro.objects.create(titular=titular, concepto=ConceptoCobro.objects.filter(tipo="recurrente").first(), vigente_desde=timezone.now().date())
    agrupacion = Agrupacion.objects.create(nombre="G1")
    argumentos = {
        "titulares:detalle": {"pk": titular.pk},
        "titulares:ficha_pago": {"pk": titular.pk},
        "titulares:editar": {"pk": titular.pk},
        "titulares:contacto_nuevo": {"pk": titular.pk},
        "titulares:contacto_editar": {"pk": titular.pk, "contacto_pk": Contacto.objects.get(titular=titular).pk},
        "titulares:baja": {"pk": titular.pk},
        "titulares:reactivar": {"pk": titular.pk},
        "titulares:solicitar_alta": {"pk": titular.pk},
        "solicitudes:detalle": {"pk": solicitud.pk},
        "solicitudes:aprobar": {"pk": solicitud.pk},
        "solicitudes:rechazar": {"pk": solicitud.pk},
        "solicitudes:codigo": {"pk": solicitud.pk},
        "solicitudes:politica_editar": {"pk": PoliticaAccion.objects.first().pk},
        "usuario_editar": {"pk": usuarios["Operación"].pk},
        "rol_editar": {"pk": otro.pk},
        "dispositivo_aprobar": {"pk": dispositivo.pk},
        "dispositivo_revocar": {"pk": dispositivo.pk},
        "delegacion_revocar": {"pk": delegacion.pk},
        "cobros:concepto_editar": {"pk": ConceptoCobro.objects.first().pk},
        "cobros:regla_editar": {"pk": regla.pk},
        "cobros:plan_editar": {"pk": plan.pk},
        "configuracion:catalogo": {"catalogo": "agrupaciones"},
        "configuracion:catalogo_nuevo": {"catalogo": "agrupaciones"},
        "configuracion:catalogo_editar": {"catalogo": "agrupaciones", "pk": agrupacion.pk},
    }
    return usuarios, argumentos


def permitido(rol, nombre):
    if nombre in OBJETO_PROPIO and OBJETO_PROPIO[nombre] is not None:
        return rol.nombre in OBJETO_PROPIO[nombre]
    return bool(rol.permisos() & set(MATRIZ[nombre]))


@pytest.mark.parametrize("nombre", sorted(MATRIZ))
def test_matriz_url_por_rol(escenario, nombre):
    usuarios, argumentos = escenario
    url = reverse(nombre, kwargs=argumentos.get(nombre))
    assert set(vista_de(nombre, argumentos.get(nombre)).permisos_requeridos) == set(MATRIZ[nombre])
    anonimo = cliente().get(url)
    assert anonimo.status_code == 302 and reverse("entrar") in anonimo.url
    for nombre_rol in ROLES:
        usuario = usuarios[nombre_rol]
        respuesta = cliente(usuario).get(url)
        if permitido(usuario.rol, nombre):
            assert respuesta.status_code in (200, 302, 405), (nombre, nombre_rol, respuesta.status_code)
            if respuesta.status_code == 302:
                assert reverse("entrar") not in respuesta.url
        else:
            assert respuesta.status_code == 403, (nombre, nombre_rol, respuesta.status_code)


@pytest.mark.parametrize("nombre", sorted(SOLO_SESION - {"revisar_autorizacion", "aviso_enterado", "salir"}))
def test_rutas_de_sesion_piden_sesion(escenario, nombre):
    usuarios, _ = escenario
    respuesta = cliente().get(reverse(nombre))
    assert respuesta.status_code == 302 and reverse("entrar") in respuesta.url
    assert cliente(usuarios["Operación"]).get(reverse(nombre)).status_code in (200, 302)


def test_revision_de_codigo_ajeno_no_permitida(escenario):
    usuarios, _ = escenario
    usado = CodigoUsado.objects.create(autorizador=usuarios["Supervisión"], paso=1, proposito=CodigoUsado.AUTORIZACION, revision=CodigoUsado.POR_REVISAR)
    url = reverse("revisar_autorizacion", args=[usado.pk])
    assert cliente(usuarios["Dirección"]).post(url, {"decision": "confirmar"}).status_code == 404
    assert cliente(usuarios["Supervisión"]).post(url, {"decision": "confirmar"}).status_code == 302
    usado.refresh_from_db()
    assert usado.revision == CodigoUsado.CONFIRMADO


def test_solicitud_ajena_no_visible_para_operacion(escenario):
    usuarios, argumentos = escenario
    otro = nuevo_usuario("otro_op", usuarios["Operación"].rol)
    url = reverse("solicitudes:detalle", kwargs=argumentos["solicitudes:detalle"])
    assert cliente(otro).get(url).status_code == 403
    assert cliente(usuarios["Operación"]).get(url).status_code == 200
    assert cliente(usuarios["Supervisión"]).get(url).status_code == 200


def test_quitar_permiso_en_base_bloquea_al_momento(escenario):
    usuarios, _ = escenario
    rol = usuarios["Operación"].rol
    rol.asignaciones.filter(permiso="ver_titulares").delete()
    assert cliente(usuarios["Operación"]).get(reverse("titulares:lista")).status_code == 403


def test_csrf_activo(escenario):
    from django.test import Client

    from .conftest import equipo_aprobado

    usuarios, _ = escenario
    c = Client(enforce_csrf_checks=True)
    c.cookies["dispositivo"] = equipo_aprobado()
    c.force_login(usuarios["Dirección"], backend="django.contrib.auth.backends.ModelBackend")
    assert c.post(reverse("auditoria:verificar")).status_code == 403
