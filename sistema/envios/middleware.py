import re
import secrets
from datetime import timedelta

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .models import EnvioUsado

CAMPO = "ficha_envio"
PATRON = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
ENTRADA_CSRF = re.compile(rb'<input type="hidden" name="csrfmiddlewaretoken" value="[^"<>]*">')
VIGENCIA = timedelta(days=2)
REDIRECCIONES = (301, 302, 303, 307, 308)
MENSAJE = "Esa operación ya se había enviado; no se repitió."


def nueva_ficha():
    return secrets.token_urlsafe(32)


def _con_ficha(coincidencia):
    return coincidencia.group(0) + b'<input type="hidden" name="' + CAMPO.encode("ascii") + b'" value="' + nueva_ficha().encode("ascii") + b'">'


class FichaDeEnvio:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.ficha_envio = None
        respuesta = self.get_response(request)
        ficha = getattr(request, "ficha_envio", None)
        if ficha:
            self._cerrar(ficha, respuesta)
        return self._insertar(respuesta)

    def process_view(self, request, vista, args, kwargs):
        if request.method != "POST" or not getattr(request, "user", None) or not request.user.is_authenticated:
            return None
        valor = request.POST.get(CAMPO, "")
        if not PATRON.match(valor):
            return None
        try:
            with transaction.atomic():
                EnvioUsado.objects.filter(creado__lt=timezone.now() - VIGENCIA).delete()
                EnvioUsado.objects.create(ficha=valor, ruta=request.path[:300])
        except IntegrityError:
            return self._repetido(request, valor)
        request.ficha_envio = valor
        return None

    def _repetido(self, request, valor):
        previo = EnvioUsado.objects.filter(ficha=valor).first()
        destino = previo.destino if previo is not None else ""
        if not destino or not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            destino = request.path
        messages.info(request, MENSAJE)
        return HttpResponseRedirect(destino)

    def _cerrar(self, ficha, respuesta):
        ubicacion = respuesta.get("Location", "") if respuesta.status_code in REDIRECCIONES else ""
        if ubicacion and len(ubicacion) <= 500:
            EnvioUsado.objects.filter(ficha=ficha).update(destino=ubicacion)
        else:
            EnvioUsado.objects.filter(ficha=ficha).delete()

    def _insertar(self, respuesta):
        if getattr(respuesta, "streaming", False) or "text/html" not in respuesta.get("Content-Type", ""):
            return respuesta
        contenido = respuesta.content
        if b"csrfmiddlewaretoken" not in contenido:
            return respuesta
        respuesta.content = ENTRADA_CSRF.sub(_con_ficha, contenido)
        if respuesta.has_header("Content-Length"):
            respuesta["Content-Length"] = str(len(respuesta.content))
        return respuesta
