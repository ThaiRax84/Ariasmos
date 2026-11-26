import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.servicios import registrar
from cobros.models import Recibo
from cuentas.decoradores import requiere_permiso

from . import servicios, variables
from .formularios import FormularioPlantilla, FormularioTope
from .models import Envio, PlantillaMensaje

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
