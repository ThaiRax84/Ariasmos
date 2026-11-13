from django.shortcuts import render

from auditoria.servicios import MOTIVOS, ultima_verificacion
from banco import conciliacion
from banco.models import CuentaBancaria, Importacion, MovimientoBancario
from caja.models import Denominacion, Traslado
from caja import retiros
from caja.servicios import alertas as alertas_caja
from configuracion.models import Negocio, parametro
from cortes import servicios as cortes
from cortes.models import MAYOR, Corte
from cuentas import conectar
from cuentas.decoradores import requiere_sesion
from cuentas.models import Delegacion, Dispositivo
from cuentas.servicios import avisos_pendientes, por_revisar
from inventario import servicios as inventario
from respaldos import servicios as respaldos
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
    contexto["avisos_inventario"] = inventario.avisos(usuario)
    if usuario.tiene_permiso("aprobar_dispositivos"):
        datos_certificado = conectar.datos()
        if datos_certificado and datos_certificado["por_vencer"]:
            contexto["certificado_por_vencer"] = datos_certificado
    if usuario.tiene_permiso("recibir_efectivo"):
        contexto["diarios_pendientes"] = cortes.diarios_pendientes()
        contexto["alertas"] = alertas_caja(usuario)
        contexto["por_recibir"] = Traslado.objects.filter(destino=usuario, estado=Traslado.PENDIENTE).count()
    if usuario.tiene_permiso("revisar_retiros"):
        contexto["avisos_retiros"] = retiros.avisos(usuario)
    if usuario.tiene_permiso("conciliar_banco"):
        contexto["retenidas"] = list(conciliacion.con_retenidos())
        contexto["automaticas"] = list(Importacion.objects.filter(origen=Importacion.CARPETA).select_related("cuenta__banco")[:5])
        contexto["banco_pendientes"] = MovimientoBancario.objects.filter(estado=MovimientoBancario.POR_IDENTIFICAR).count()
        contexto["banco_propuestos"] = MovimientoBancario.objects.filter(estado=MovimientoBancario.POR_IDENTIFICAR, propuesta__isnull=False).count()
        contexto["ultima_importacion"] = Importacion.objects.order_by("-creada").first()
        contexto["muestra_banco"] = True
    if usuario.tiene_permiso("conciliar_banco") or usuario.tiene_permiso("ver_auditoria"):
        contexto["sin_respaldo"] = list(conciliacion.sin_respaldo_vigentes()[:50])
        contexto["antiguos_sin_respaldo"] = list(conciliacion.antiguos_sin_respaldo()[:50])
        contexto["dias_sin_respaldo"] = parametro("dias_sin_respaldo_alerta")
    if usuario.tiene_permiso("administrar_configuracion"):
        contexto["falta_cuenta"] = CuentaBancaria.principal_activa() is None
        contexto["faltan_denominaciones"] = not Denominacion.objects.filter(activa=True).exists()
        contexto["entregas_con_problema"] = cortes.entregas_con_problema().count()
    if usuario.tiene_permiso("administrar_respaldos"):
        contexto["alertas_respaldo"] = respaldos.alertas()
        contexto["clave_pendiente"] = Negocio.objects.filter(pk=1, clave_recuperacion_pendiente=True).exists()
    if usuario.tiene_permiso("cerrar_cortes"):
        contexto["mayores_borrador"] = Corte.objects.filter(tipo=MAYOR, estado=Corte.BORRADOR).order_by("fecha")
    if usuario.tiene_permiso("ver_auditoria"):
        contexto["importaciones_por_revisar"] = list(conciliacion.pendientes_de_revision()[:50])
        verificacion = ultima_verificacion()
        if verificacion is not None and not verificacion.valida:
            contexto["bitacora_fallida"] = verificacion
            contexto["bitacora_motivo"] = MOTIVOS.get(verificacion.motivo, verificacion.motivo)
    return render(request, "inicio.html", contexto)
