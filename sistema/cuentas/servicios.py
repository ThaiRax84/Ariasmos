import hashlib
import hmac
import secrets
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from auditoria.servicios import registrar
from configuracion.models import parametro
from nucleo import totp
from proyecto.red import ip_cliente

from . import secretos
from .models import CodigoActivacion, CodigoUsado, Delegacion, Dispositivo, Usuario
from .permisos import INDISPENSABLES

ALFABETO_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def hash_credencial(credencial):
    return hashlib.sha256(credencial.encode("utf-8")).hexdigest()


def buscar_dispositivo(credencial):
    if not credencial or len(credencial) > 200:
        return None
    return Dispositivo.objects.filter(hash_credencial=hash_credencial(credencial)).first()


def depurar_pendientes():
    limite = timezone.now() - timedelta(hours=24)
    return Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE, creado__lt=limite).delete()[0]


def hay_cupo_pendientes():
    depurar_pendientes()
    return Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).count() < parametro("maximo_equipos_pendientes")


def registrar_dispositivo(request):
    if not hay_cupo_pendientes():
        return None, None
    credencial = secrets.token_urlsafe(32)
    codigo = "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(6))
    dispositivo = Dispositivo.objects.create(
        hash_credencial=hash_credencial(credencial),
        codigo=codigo,
        agente=request.META.get("HTTP_USER_AGENT", "")[:300],
        ip=ip_cliente(request)[:45],
    )
    return credencial, dispositivo


def poner_cookie_dispositivo(respuesta, credencial):
    respuesta.set_cookie(
        settings.COOKIE_DISPOSITIVO,
        credencial,
        max_age=settings.EDAD_COOKIE_DISPOSITIVO,
        httponly=True,
        secure=settings.COOKIE_DISPOSITIVO_SEGURA,
        samesite="Strict",
    )


def aprobar_dispositivo(dispositivo, usuario, nombre, request=None):
    dispositivo.estado = Dispositivo.APROBADO
    dispositivo.nombre = nombre[:100]
    dispositivo.aprobado_por = usuario
    dispositivo.aprobado_en = timezone.now()
    dispositivo.save()
    registrar("dispositivo_aprobado", usuario=usuario, objeto=dispositivo, datos={"nombre": dispositivo.nombre, "codigo": dispositivo.codigo}, request=request)


def revocar_dispositivo(dispositivo, usuario, request=None):
    dispositivo.estado = Dispositivo.REVOCADO
    dispositivo.revocado_por = usuario
    dispositivo.revocado_en = timezone.now()
    dispositivo.save()
    registrar("dispositivo_revocado", usuario=usuario, objeto=dispositivo, datos={"nombre": dispositivo.nombre}, request=request)


def verificar_codigo(usuario, codigo):
    secreto = secretos.leer(usuario) if usuario.totp_confirmado else ""
    if not secreto:
        return None
    return totp.verificar(secreto, codigo, ventana=parametro("ventana_codigo_pasos"))


def consumir_codigo(autorizador, codigo, proposito, usado_por=None, solicitud=None, secreto=None):
    if secreto is None:
        paso = verificar_codigo(autorizador, codigo)
    else:
        paso = totp.verificar(secreto, codigo, ventana=parametro("ventana_codigo_pasos"))
    if paso is None:
        return None, "invalido"
    revision = CodigoUsado.POR_REVISAR if proposito == CodigoUsado.AUTORIZACION else CodigoUsado.SIN_REVISION
    try:
        with transaction.atomic():
            usado = CodigoUsado.objects.create(
                autorizador=autorizador,
                paso=paso,
                proposito=proposito,
                usado_por=usado_por,
                solicitud=solicitud,
                revision=revision,
            )
    except IntegrityError:
        return None, "reutilizado"
    return usado, "ok"


def usar_delegacion(usuario, permiso, request=None, contexto=None):
    ahora = timezone.now()
    for delegacion in Delegacion.objects.vigentes(ahora).filter(receptor=usuario, permiso=permiso).order_by("vence", "creada"):
        actualizadas = (
            Delegacion.objects.filter(pk=delegacion.pk, revocada=False)
            .filter(Q(vence__isnull=True) | Q(vence__gt=ahora))
            .filter(Q(usos_maximos__isnull=True) | Q(usos__lt=F("usos_maximos")))
            .update(usos=F("usos") + 1)
        )
        if actualizadas:
            delegacion.refresh_from_db()
            registrar(
                "delegacion_usada",
                usuario=usuario,
                objeto=delegacion,
                datos={"permiso": permiso, "uso": delegacion.usos, "usos_maximos": delegacion.usos_maximos, **(contexto or {})},
                request=request,
            )
            return delegacion
    return None


def _clave_intentos(request):
    dispositivo = getattr(request, "dispositivo", None)
    if dispositivo is not None:
        return f"intentos-equipo:{dispositivo.pk}"
    return f"intentos-ip:{ip_cliente(request)}"


def limite_intentos_superado(request):
    return cache.get(_clave_intentos(request), 0) >= parametro("intentos_por_equipo_cada_5_minutos")


def contar_intento(request):
    clave = _clave_intentos(request)
    if not cache.add(clave, 1, 300):
        try:
            cache.incr(clave)
        except ValueError:
            cache.set(clave, 1, 300)


def registrar_fallo(usuario, request=None, motivo="contrasena"):
    with transaction.atomic():
        Usuario.objects.filter(pk=usuario.pk).update(intentos_fallidos=F("intentos_fallidos") + 1)
        usuario.refresh_from_db(fields=["intentos_fallidos", "bloqueado_hasta"])
        umbral = parametro("intentos_antes_de_bloqueo")
        if usuario.intentos_fallidos >= umbral:
            exceso = usuario.intentos_fallidos - umbral
            minutos = min(parametro("minutos_bloqueo_inicial") * (2 ** min(exceso, 20)), parametro("minutos_bloqueo_maximo"))
            usuario.bloqueado_hasta = timezone.now() + timedelta(minutes=minutos)
            Usuario.objects.filter(pk=usuario.pk).update(bloqueado_hasta=usuario.bloqueado_hasta)
            registrar("cuenta_bloqueada", objeto=usuario, datos={"intentos": usuario.intentos_fallidos, "minutos": minutos}, request=request)
        registrar("inicio_sesion_fallido", objeto=usuario, datos={"motivo": motivo, "intentos": usuario.intentos_fallidos}, request=request)


def reiniciar_intentos(usuario):
    Usuario.objects.filter(pk=usuario.pk).update(intentos_fallidos=0, bloqueado_hasta=None)
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None


def marcar_reingreso(request):
    request.session["reingreso_en"] = timezone.now().timestamp()


def reingreso_vigente(request):
    marca = request.session.get("reingreso_en")
    if not marca:
        return False
    return timezone.now().timestamp() - marca <= parametro("minutos_validez_reingreso") * 60


def quedan_administradores(excluir_usuario=None, rol_modificado=None, permisos_nuevos=None):
    usuarios = Usuario.objects.filter(activo=True).select_related("rol")
    if excluir_usuario is not None:
        usuarios = usuarios.exclude(pk=excluir_usuario.pk)
    for permiso in INDISPENSABLES:
        alguno = False
        for usuario in usuarios:
            if usuario.rol_id is None:
                continue
            if rol_modificado is not None and usuario.rol_id == rol_modificado.pk:
                permisos = permisos_nuevos
            else:
                permisos = usuario.rol.permisos()
            if permiso in permisos:
                alguno = True
                break
        if not alguno:
            return False
    return True


def por_revisar(usuario):
    return CodigoUsado.objects.filter(autorizador=usuario, revision=CodigoUsado.POR_REVISAR)


def permisos_que_exceden(actor, permisos):
    return set(permisos) - actor.permisos_de_rol()


def rechazar_escalada(actor, request, motivo, objeto=None, exceso=()):
    registrar("escalada_rechazada", usuario=actor, objeto=objeto, datos={"motivo": motivo, "permisos": sorted(exceso)}, request=request)


def avisos_pendientes(usuario):
    intentos = apps.get_model("solicitudes", "IntentoCodigo")
    return intentos.objects.filter(autorizador=usuario, tipo="bloqueo", visto=False)


def tiene_avisos(usuario):
    return por_revisar(usuario).exists() or avisos_pendientes(usuario).exists()


CLAVE_SESION_EQUIPO = "dispositivo_id"


def ligar_sesion(request):
    dispositivo = getattr(request, "dispositivo", None)
    if dispositivo is not None:
        request.session[CLAVE_SESION_EQUIPO] = dispositivo.pk


def normalizar_activacion(texto):
    return "".join(c for c in str(texto or "").upper() if c.isascii() and c.isalnum())


def hash_activacion(codigo):
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), ("activacion|" + normalizar_activacion(codigo)).encode("utf-8"), hashlib.sha256).hexdigest()


def invalidar_activaciones(usuario):
    return CodigoActivacion.objects.filter(usuario=usuario, usado_en__isnull=True, invalidado=False).update(invalidado=True)


def generar_activacion(usuario, creado_por, request=None):
    invalidar_activaciones(usuario)
    codigo = "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(10))
    caduca = timezone.now() + timedelta(hours=parametro("horas_validez_codigo_activacion"))
    CodigoActivacion.objects.create(usuario=usuario, hash_codigo=hash_activacion(codigo), creado_por=creado_por, caduca=caduca)
    registrar("codigo_activacion_generado", usuario=creado_por, objeto=usuario, datos={"para": usuario.usuario, "caduca": caduca}, request=request)
    return f"{codigo[:5]}-{codigo[5:]}", caduca


def cerrar_sesiones(usuario):
    cerradas = 0
    for sesion in Session.objects.filter(expire_date__gt=timezone.now()):
        if sesion.get_decoded().get("_auth_user_id") == str(usuario.pk):
            sesion.delete()
            cerradas += 1
    return cerradas


def restablecer_acceso(usuario, actor, request=None):
    usuario.set_unusable_password()
    usuario.save(update_fields=["password"])
    cerradas = cerrar_sesiones(usuario)
    registrar("acceso_restablecido", usuario=actor, objeto=usuario, datos={"para": usuario.usuario, "sesiones_cerradas": cerradas}, request=request)
    return generar_activacion(usuario, actor, request)


def buscar_activacion(usuario, codigo):
    return CodigoActivacion.objects.filter(usuario=usuario, hash_codigo=hash_activacion(codigo)).first()
