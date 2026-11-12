from functools import wraps
from urllib.parse import urlencode

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

from auditoria.servicios import registrar

from .servicios import reingreso_vigente


def requiere_sesion(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse("entrar"), "siguiente")
        return vista(request, *args, **kwargs)

    envoltura.permisos_requeridos = ()
    return envoltura


def requiere_permiso(*permisos, reingreso=False):
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), reverse("entrar"), "siguiente")
            if not any(request.user.tiene_permiso(p) for p in permisos):
                registrar("acceso_denegado", request=request, datos={"ruta": request.path, "permisos": list(permisos)})
                raise PermissionDenied
            if reingreso and not reingreso_vigente(request):
                destino = request.get_full_path() if request.method == "GET" else request.path
                return redirect(reverse("confirmar") + "?" + urlencode({"siguiente": destino}))
            return vista(request, *args, **kwargs)

        envoltura.permisos_requeridos = permisos
        return envoltura

    return decorador
