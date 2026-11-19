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
