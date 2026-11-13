from django.shortcuts import render

from auditoria.servicios import MOTIVOS, ultima_verificacion
from banco.models import CuentaBancaria
from caja.models import Traslado
from caja.servicios import alertas as alertas_caja
from cuentas.decoradores import requiere_sesion
from cuentas.models import Delegacion, Dispositivo
from cuentas.servicios import avisos_pendientes, por_revisar
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
        "bloqueos": avisos_pendientes(usuario).count(),
        "delegaciones": Delegacion.objects.vigentes().filter(receptor=usuario).select_related("otorgante"),
        "dispositivos_pendientes": Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).count() if usuario.tiene_permiso("aprobar_dispositivos") else 0,
    }
    if usuario.tiene_permiso("recibir_efectivo"):
        contexto["alertas"] = alertas_caja()
        contexto["por_recibir"] = Traslado.objects.filter(destino=usuario, estado=Traslado.PENDIENTE).count()
    if usuario.tiene_permiso("administrar_configuracion"):
        contexto["falta_cuenta"] = CuentaBancaria.principal_activa() is None
    if usuario.tiene_permiso("ver_auditoria"):
        verificacion = ultima_verificacion()
        if verificacion is not None and not verificacion.valida:
            contexto["bitacora_fallida"] = verificacion
            contexto["bitacora_motivo"] = MOTIVOS.get(verificacion.motivo, verificacion.motivo)
    return render(request, "inicio.html", contexto)
