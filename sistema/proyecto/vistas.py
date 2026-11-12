from django.shortcuts import render

from cuentas.decoradores import requiere_sesion
from cuentas.models import Delegacion, Dispositivo
from cuentas.servicios import por_revisar
from solicitudes import motor
from solicitudes.models import Solicitud
from solicitudes.views import pendientes_para


@requiere_sesion
def inicio(request):
    usuario = request.user
    motor.caducar_vencidas()
    contexto = {
        "pendientes": pendientes_para(usuario),
        "propias": Solicitud.objects.filter(solicitante=usuario, estado=Solicitud.PENDIENTE).select_related("titular"),
        "por_revisar": por_revisar(usuario).select_related("usado_por", "solicitud__titular"),
        "delegaciones": Delegacion.objects.vigentes().filter(receptor=usuario).select_related("otorgante"),
        "dispositivos_pendientes": Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).count() if usuario.tiene_permiso("aprobar_dispositivos") else 0,
    }
    return render(request, "inicio.html", contexto)
