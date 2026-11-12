from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone

from auditoria.servicios import registrar

from .servicios import buscar_dispositivo, poner_cookie_dispositivo, registrar_dispositivo

LIBRES_DISPOSITIVO = ("/static/", "/dispositivo/", "/asistente/")
LIBRES_TOTP = ("/static/", "/cuentas/totp/", "/cuentas/salir/", "/dispositivo/")


class ControlDispositivo:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.dispositivo = None
        if request.path.startswith("/static/"):
            return self.get_response(request)
        credencial = request.COOKIES.get(settings.COOKIE_DISPOSITIVO)
        dispositivo = buscar_dispositivo(credencial)
        nueva = None
        if dispositivo is None:
            nueva, dispositivo = registrar_dispositivo(request)
        request.dispositivo = dispositivo
        if dispositivo.aprobado:
            ahora = timezone.now()
            if dispositivo.ultimo_uso is None or (ahora - dispositivo.ultimo_uso).total_seconds() > 300:
                type(dispositivo).objects.filter(pk=dispositivo.pk).update(ultimo_uso=ahora)
        if getattr(request, "instalacion_configurada", False) and not dispositivo.aprobado and not request.path.startswith(LIBRES_DISPOSITIVO):
            if request.user.is_authenticated:
                logout(request)
            respuesta = redirect("dispositivo_pendiente")
        else:
            respuesta = self.get_response(request)
        if nueva:
            poner_cookie_dispositivo(respuesta, nueva)
        return respuesta


class ControlSesion:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = request.user
        if usuario.is_authenticated and not request.path.startswith("/static/"):
            ahora = timezone.now().timestamp()
            minutos = usuario.rol.minutos_inactividad if usuario.rol_id else 15
            ultima = request.session.get("ultima_actividad")
            if ultima is not None and ahora - ultima > minutos * 60:
                registrar("cierre_por_inactividad", usuario=usuario, request=request)
                logout(request)
                messages.info(request, "Tu sesión se cerró por inactividad.")
                return redirect("entrar")
            request.session["ultima_actividad"] = ahora
            if usuario.rol_id and usuario.rol.requiere_totp and not usuario.totp_confirmado:
                if not request.path.startswith(LIBRES_TOTP):
                    return redirect("totp")
        return self.get_response(request)
