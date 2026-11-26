import json
from functools import partial

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from auditoria.servicios import registrar
from cobros.models import Recibo
from cuentas.decoradores import requiere_permiso

from . import gestion_avisos, servicios, variables
from .formularios import (
    FormularioAviso,
    FormularioLimites,
    FormularioPlantilla,
    FormularioTope,
)
from .models import Aviso, Envio, PlantillaMensaje

ADMINISTRAR = "administrar_mensajes"
AVISOS_DE_REVISION = {
    PlantillaMensaje.EN_REVISION: "Guardado. Meta lo está revisando; suele tardar de minutos a un día.",
    PlantillaMensaje.APROBADA: "Guardado y listo para usar.",
    PlantillaMensaje.RECHAZADA: "Guardado, pero Meta no lo aceptó. Revisa el motivo y cámbialo.",
    PlantillaMensaje.BORRADOR: "Guardado como borrador.",
}


@requiere_permiso(ADMINISTRAR)
def panel(request):
    estado = servicios.estado()
    contexto = {
        "estado": estado,
        "plantillas": [
            (p, variables.para_mostrar(p.texto)) for p in PlantillaMensaje.objects.all()
        ],
        "formulario_tope": FormularioTope(initial={"tope": estado.get("tope")}),
    }
    return render(request, "mensajes/panel.html", contexto)


@requiere_permiso(ADMINISTRAR)
@require_POST
def tope(request):
    formulario = FormularioTope(request.POST)
    if not formulario.is_valid():
        messages.error(
            request, "Escribe un número entero de mensajes, de 1 en adelante."
        )
    else:
        try:
            servicios.fijar_tope(formulario.cleaned_data["tope"], request.user)
        except ValueError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Tope guardado.")
    return redirect("mensajes:panel")


def _editar(request, clave, objeto):
    formulario = FormularioPlantilla(
        request.POST if request.method == "POST" else None,
        initial={"nombre": objeto.nombre, "texto": objeto.texto} if objeto else None,
    )
    if request.method == "POST" and formulario.is_valid():
        try:
            guardada = servicios.guardar_plantilla(
                clave,
                formulario.cleaned_data["nombre"],
                formulario.cleaned_data["texto"],
                request.user,
            )
        except ValueError as error:
            formulario.add_error(None, str(error))
        else:
            messages.success(request, AVISOS_DE_REVISION[guardada.estado])
            return redirect("mensajes:panel")
    texto = formulario["texto"].value() or ""
    contexto = {
        "formulario": formulario,
        "objeto": objeto,
        "botones": variables.botones(),
        "vista_previa": variables.rellenar(texto, variables.EJEMPLOS),
        "ejemplos": json.dumps(variables.EJEMPLOS),
    }
    return render(request, "mensajes/plantilla.html", contexto)


@requiere_permiso(ADMINISTRAR, reingreso=True)
def plantilla(request, clave):
    return _editar(request, clave, get_object_or_404(PlantillaMensaje, clave=clave))


@requiere_permiso(ADMINISTRAR, reingreso=True)
def plantilla_nueva(request):
    clave = (
        servicios.clave_para(request.POST.get("nombre", ""))
        if request.method == "POST"
        else ""
    )
    return _editar(request, clave, None)


@requiere_permiso("enviar_whatsapp")
@require_POST
def enviar_recibo(request, pk):
    recibo = get_object_or_404(Recibo.objects.select_related("pago__titular"), pk=pk)
    try:
        envio = servicios.enviar_recibo(
            recibo, request.user, reenviar=request.POST.get("reenviar") == "1"
        )
    except PermissionDenied:
        registrar(
            "acceso_denegado",
            request=request,
            datos={
                "ruta": request.path,
                "permisos": ["enviar_whatsapp", "ver_ingresos"],
            },
        )
        raise
    except servicios.NoSePuedeEnviar as aviso:
        messages.error(request, str(aviso))
    else:
        if envio.estado in (Envio.NO_ENVIADO, Envio.INCIERTO):
            messages.error(request, envio.motivo)
        else:
            messages.success(
                request, "Recibo mandado por WhatsApp. Aquí verás cuándo se entregue."
            )
    return redirect("cobros:recibo", pk=pk)


def _pantalla_de_avisos(request, formulario, limites):
    receptores = gestion_avisos.receptores()
    contexto = {
        "filas": gestion_avisos.filas(),
        "limites": limites,
        "sin_envio": ", ".join(
            gestion_avisos.DIAS_DE_LA_SEMANA[d] for d in limites["dias_sin_envio"]
        )
        or "Ninguno",
        "formulario": formulario,
        "aceptaron": sum(r.falta is None for r in receptores),
        "total": len(receptores),
        "caben_mas": Aviso.objects.count() < Aviso.MAXIMO_DE_AVISOS,
    }
    return render(request, "mensajes/avisos.html", contexto)


@requiere_permiso(ADMINISTRAR, reingreso=True)
def avisos(request):
    limites = gestion_avisos.limites()
    if request.method != "POST":
        inicial = {**limites, "dias_sin_envio": [str(d) for d in limites["dias_sin_envio"]]}
        return _pantalla_de_avisos(request, FormularioLimites(initial=inicial), limites)
    if request.POST.get("accion") != "limites":
        return redirect("mensajes:avisos")
    formulario = FormularioLimites(request.POST)
    if not formulario.is_valid():
        return _pantalla_de_avisos(request, formulario, limites)
    datos = formulario.cleaned_data
    gestion_avisos.guardar_limites(
        datos["inicio"],
        datos["fin"],
        datos["maximo"],
        datos["dias_sin_envio"],
        request.user,
    )
    messages.success(request, "Guardado.")
    return redirect("mensajes:avisos")


def _guardar_aviso(request, aviso):
    formulario = FormularioAviso(
        request.POST if request.method == "POST" else None, aviso=aviso
    )
    if request.method == "POST" and formulario.is_valid():
        nuevo = aviso or Aviso(momento=formulario.cleaned_data["momento"])
        try:
            gestion_avisos.guardar(
                nuevo,
                formulario.cleaned_data["plantilla"],
                formulario.cleaned_data.get("dias"),
                list(formulario.cleaned_data.get("agrupaciones") or []),
                request.user,
            )
        except ValueError as error:
            formulario.add_error(None, str(error))
        else:
            messages.success(request, "Aviso guardado.")
            return redirect("mensajes:avisos")
    return render(
        request, "mensajes/aviso.html", {"formulario": formulario, "aviso": aviso}
    )


ACCIONES_DEL_AVISO = {
    "activar": partial(gestion_avisos.cambiar_activo, activo=True),
    "desactivar": partial(gestion_avisos.cambiar_activo, activo=False),
    "borrar": gestion_avisos.borrar,
}


@requiere_permiso(ADMINISTRAR, reingreso=True)
def aviso_nuevo(request):
    return _guardar_aviso(request, None)


@requiere_permiso(ADMINISTRAR, reingreso=True)
def aviso(request, pk):
    objeto = get_object_or_404(Aviso.objects.select_related("plantilla"), pk=pk)
    accion = ACCIONES_DEL_AVISO.get(request.POST.get("accion"))
    if request.method != "POST" or accion is None:
        return _guardar_aviso(request, objeto)
    try:
        accion(objeto, usuario=request.user)
    except ValueError as error:
        messages.error(request, str(error))
    return redirect("mensajes:avisos")


@requiere_permiso(ADMINISTRAR, reingreso=True)
@require_GET
def faltan(request):
    filas = [
        (
            r,
            gestion_avisos.FALTAS[r.falta],
            servicios.enlace_al_consentimiento(r.contacto, request.user),
        )
        for r in gestion_avisos.receptores()
        if r.falta
    ]
    return render(request, "mensajes/faltan.html", {"filas": filas})
