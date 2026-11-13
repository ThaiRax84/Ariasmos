from zoneinfo import ZoneInfo

from django.shortcuts import redirect
from django.utils import timezone

from . import moneda
from .models import Negocio

LIBRES = ("/static/", "/asistente/")


class Instalacion:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        negocio = Negocio.actual()
        request.negocio = negocio
        configurado = bool(negocio and negocio.configurado)
        request.instalacion_configurada = configurado
        if negocio:
            try:
                timezone.activate(ZoneInfo(negocio.zona_horaria))
            except Exception:
                timezone.deactivate()
        if not configurado and not request.path.startswith(LIBRES):
            return redirect("asistente:inicio")
        marca = moneda.fijar(negocio.moneda if negocio else moneda.POR_DEFECTO)
        try:
            return self.get_response(request)
        finally:
            moneda.soltar(marca)
            timezone.deactivate()
