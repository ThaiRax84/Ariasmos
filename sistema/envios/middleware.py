import re
import secrets
import threading
import time
from datetime import timedelta

from django.contrib import messages
from django.db import IntegrityError, OperationalError, connection, transaction
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
ESPERA_MAXIMA = 30
PAUSA = 0.05
ESPERAS_POR_FICHA = 1
ESPERAS_TOTALES = 3
_candado = threading.Lock()
_esperando = {}


def _entrar(valor):
    with _candado:
        if _esperando.get(valor, 0) >= ESPERAS_POR_FICHA or sum(_esperando.values()) >= ESPERAS_TOTALES:
            return False
        _esperando[valor] = _esperando.get(valor, 0) + 1
        return True


def _salir(valor):
    with _candado:
        resto = _esperando.get(valor, 0) - 1
        if resto > 0:
            _esperando[valor] = resto
        else:
            _esperando.pop(valor, None)


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
        limite = time.monotonic() + ESPERA_MAXIMA
        espera = False
        try:
            while True:
                reservada = self._reservar(valor, request.path)
                if reservada:
                    request.ficha_envio = valor
                    return None
                if reservada is None:
                    if time.monotonic() >= limite:
                        return None
                    time.sleep(PAUSA)
                    continue
                while True:
                    previo = EnvioUsado.objects.filter(ficha=valor).values_list("destino", flat=True).first()
                    if previo:
                        return self._repetido(request, previo)
                    if previo is None:
                        break
                    if not espera:
                        espera = _entrar(valor)
                        if not espera:
                            return self._repetido(request, "")
                    if time.monotonic() >= limite:
                        return self._repetido(request, "")
                    time.sleep(PAUSA)
        finally:
            if espera:
                _salir(valor)

    def _reservar(self, valor, ruta):
        try:
            with transaction.atomic():
                EnvioUsado.objects.filter(creado__lt=timezone.now() - VIGENCIA).delete()
                EnvioUsado.objects.create(ficha=valor, ruta=ruta[:300])
        except IntegrityError:
            return False
        except OperationalError as error:
            if not ocupada(error):
                raise
            return None
        return True

    def _seguro(self, request, destino):
        return bool(destino) and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}, require_https=request.is_secure())

    def _repetido(self, request, destino):
        if not self._seguro(request, destino):
            anterior = request.META.get("HTTP_REFERER", "")
            destino = anterior if self._seguro(request, anterior) else "/"
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


REINTENTOS = 3
OCUPADA = "La base de datos estuvo ocupada y no se pudo guardar. Vuelve a intentarlo."


def ocupada(error):
    texto = str(error).lower()
    return isinstance(error, OperationalError) and ("locked" in texto or "busy" in texto)


class BaseOcupada:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, vista, args, kwargs):
        request.vista_reintentable = (vista, args, kwargs)
        return None

    def process_exception(self, request, error):
        if not ocupada(error) or connection.in_atomic_block or not hasattr(request, "vista_reintentable"):
            return None
        vista, args, kwargs = request.vista_reintentable
        for intento in range(REINTENTOS):
            time.sleep(PAUSA * (intento + 1) * 4)
            for archivo in request.FILES.values():
                archivo.seek(0)
            try:
                return vista(request, *args, **kwargs)
            except OperationalError as otro:
                if not ocupada(otro) or connection.in_atomic_block:
                    raise
        messages.error(request, OCUPADA)
        anterior = request.META.get("HTTP_REFERER", "")
        seguro = anterior and url_has_allowed_host_and_scheme(anterior, allowed_hosts={request.get_host()}, require_https=request.is_secure())
        return HttpResponseRedirect(anterior if seguro else "/")
