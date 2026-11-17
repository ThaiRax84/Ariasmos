from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_POST

from cuentas.decoradores import requiere_permiso, requiere_sesion

from . import llaves, servicios
from .canales import NOMBRES
from .formularios import FormularioActualizaciones
from .models import Descarga

PERMISO = "administrar_configuracion"


@sensitive_variables("datos")
@sensitive_post_parameters("clave")
@requiere_permiso(PERMISO, reingreso=True)
def configurar(request):
    config = servicios.configuracion()
    disponibles = llaves.disponibles()
    inicial = {"activa": config.activa, "repositorio": config.repositorio}
    formulario = FormularioActualizaciones(request.POST if request.method == "POST" else None, initial=inicial, disponibles=disponibles)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            servicios.guardar_configuracion(bool(datos.get("activa")) and disponibles, datos["repositorio"], datos.get("clave", ""), usuario=request.user, request=request)
        except servicios.ErrorActualizacion as error:
            formulario.add_error(None, str(error))
        else:
            messages.success(request, "Actualizaciones guardadas.")
            return redirect("actualizaciones:configurar")
    contexto = {
        "formulario": formulario,
        "config": config,
        "disponibles": disponibles,
        "canal": NOMBRES.get(config.canal, config.canal),
        "instalada": servicios.instalada() or "desconocida",
        "vigente": servicios.vigente(),
        "descargas": Descarga.objects.select_related("version", "pedida_por")[:10],
    }
    respuesta = render(request, "actualizaciones/configurar.html", contexto)
    respuesta["Cache-Control"] = "no-store"
    return respuesta


@requiere_permiso(PERMISO)
@require_POST
def buscar(request):
    try:
        servicios.pedir_busqueda(request.user, request)
    except servicios.ErrorActualizacion as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Búsqueda pedida: el servicio la hará en unos minutos.")
    return redirect("actualizaciones:configurar")


@requiere_sesion
def descargar(request):
    if request.method != "POST":
        return redirect("inicio")
    try:
        servicios.pedir_descarga(request.user, request)
    except servicios.ErrorActualizacion as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Descarga pedida: el servicio la hará en unos minutos.")
    return redirect("inicio")
