from django.http import JsonResponse

from cuentas.decoradores import requiere_sesion
from proyecto.frecuencia import excedida

from . import busqueda

IR_POR_MINUTO = 120


def _json(datos, status=200):
    respuesta = JsonResponse(datos, status=status)
    respuesta["Cache-Control"] = "no-store"
    return respuesta


def _equipo_aprobado(request):
    dispositivo = getattr(request, "dispositivo", None)
    return dispositivo is not None and dispositivo.aprobado


@requiere_sesion
def ir(request):
    if not _equipo_aprobado(request):
        return _json({"error": "equipo"}, status=403)
    if excedida(request, "ir", IR_POR_MINUTO, 60):
        return _json({"error": "espera"}, status=429)
    return _json({"resultados": busqueda.buscar(request.user, request.GET.get("q", ""))})


PULSO_POR_MINUTO = 40
ULTIMOS = 6


@requiere_sesion
def pulso(request):
    from . import pulso as contadores

    if not _equipo_aprobado(request):
        return _json({"error": "equipo"}, status=403)
    if excedida(request, "pulso", PULSO_POR_MINUTO, 60):
        return _json({"error": "espera"}, status=429)
    return _json({"t": contadores.valores()})


@requiere_sesion
def ultimo(request):
    from django.shortcuts import render

    from cobros.models import Pago
    from rezagos.presentacion import ve_saldos

    usuario = request.user
    if excedida(request, "ultimo", PULSO_POR_MINUTO, 60):
        return _json({"error": "espera"}, status=429)
    consulta = Pago.objects.select_related("titular", "recibo").prefetch_related("aplicaciones__cargo__concepto").order_by("-fecha", "-id")
    if usuario.tiene_permiso("ver_titulares"):
        pagos = list(consulta[:ULTIMOS])
    elif usuario.tiene_permiso("registrar_pago_efectivo"):
        pagos = list(consulta.filter(registrado_por=usuario)[:ULTIMOS])
    else:
        pagos = []
    saldos = ve_saldos(usuario)
    for pago in pagos:
        pago.ve_importe = saldos or pago.registrado_por_id == usuario.pk
        pago.conceptos = " + ".join(str(a.cargo) for a in pago.aplicaciones.all()[:3])
    return render(request, "vivo/ultimo.html", {"pagos": pagos})
