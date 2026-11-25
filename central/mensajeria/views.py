import base64
import binascii
import uuid

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse

from emision import reloj
from emision import servicios as emision
from emision import views as base
from emision.models import Negocio
from nucleo import sobre

from . import proveedores, servicios
from .models import Documento, Mensaje, Remitente

LIMITE_ENVIAR = 2 * 1024 * 1024
MAXIMO_DE_IDS = 100
RESPUESTAS_VACIAS = {"Cache-Control": "no-store"}


def _autenticar_servicio(cuerpo, accion):
    instalacion, carga, tolerancia = base._autenticar(cuerpo, "servicio")
    negocio = instalacion.negocio
    if carga["accion"] != accion:
        raise base.Denegado(403, "accion_distinta", negocio)
    if instalacion.revocada or negocio.revocado:
        raise base.Denegado(403, "revocada", negocio)
    if not emision.pago_al_corriente(negocio):
        raise base.Denegado(403, "pago_pendiente", negocio)
    return instalacion, carga, tolerancia


def _exigir(datos, requeridos, opcionales=None):
    opcionales = opcionales or {}
    nombres = set(datos)
    if not set(requeridos) <= nombres <= set(requeridos) | set(opcionales):
        raise base.Denegado(400, "datos_distintos")
    if any(
        type(datos[n]) is not t
        for n, t in {**requeridos, **opcionales}.items()
        if n in datos
    ):
        raise base.Denegado(400, "tipos_equivocados")


def _adjunto(cuerpo):
    texto = cuerpo.get("adjunto")
    if texto is None:
        return None
    try:
        return base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        raise base.Denegado(400, "adjunto_invalido")


def _servicio(accion, con_adjunto=False):
    def decorador(manejar):
        def autenticar(cuerpo):
            return _autenticar_servicio(cuerpo, accion)

        @base._post(
            base.CAMPOS_RENOVAR,
            autentica=autenticar,
            limite=LIMITE_ENVIAR if con_adjunto else base.LIMITE_CUERPO,
            opcionales=("adjunto",) if con_adjunto else (),
        )
        def vista(cuerpo):
            instalacion, carga, tolerancia = autenticar(cuerpo)
            with transaction.atomic():
                base._gastar_sello(instalacion, carga, tolerancia)
            extra = (_adjunto(cuerpo),) if con_adjunto else ()
            try:
                respuesta = manejar(instalacion, carga["datos"], *extra)
            except servicios.DatosInvalidos as error:
                raise base.Denegado(400, f"datos_{error}", instalacion.negocio)
            return base._con_acuse(respuesta, instalacion, carga)

        return vista

    return decorador


@_servicio("mensajes_estado")
def estado(instalacion, datos):
    _exigir(datos, {})
    return servicios.estado(instalacion.negocio)


@_servicio("mensajes_plantilla")
def plantilla(instalacion, datos):
    _exigir(datos, {"clave": str, "nombre": str, "texto": str, "con_documento": bool})
    return servicios.guardar_plantilla(instalacion.negocio, datos)


@_servicio("mensajes_tope")
def tope(instalacion, datos):
    _exigir(datos, {"tope": int})
    return servicios.fijar_tope(instalacion.negocio, datos["tope"])


def _validar_envio(datos):
    _exigir(
        datos,
        {"clave_envio": str, "plantilla": str, "destino": str, "valores": dict},
        {"adjunto_sha256": str},
    )
    if servicios.PATRON_CLAVE_ENVIO.fullmatch(datos["clave_envio"]) is None or any(
        type(n) is not str or type(v) is not str for n, v in datos["valores"].items()
    ):
        raise base.Denegado(400, "datos_envio")


@_servicio("mensajes_enviar", con_adjunto=True)
def enviar(instalacion, datos, adjunto):
    _validar_envio(datos)
    return servicios.enviar(instalacion, datos, adjunto)


def _identificadores(ids):
    try:
        return [uuid.UUID(texto) for texto in ids]
    except ValueError:
        raise base.Denegado(400, "ids_invalidos")


@_servicio("mensajes_consultar")
def consultar(instalacion, datos):
    _exigir(datos, {"ids": list})
    ids = datos["ids"]
    if len(ids) > MAXIMO_DE_IDS or any(type(i) is not str for i in ids):
        raise base.Denegado(400, "ids_invalidos")
    return servicios.consultar(instalacion, _identificadores(ids))


def documento(request, token):
    if request.method != "GET":
        return base._negar(405)
    servicios.purgar_documentos()
    contenido = (
        Documento.objects.filter(
            token=token,
            vence__gt=reloj.ahora(),
            mensaje__estado__in=(Mensaje.ACEPTADO, Mensaje.ENVIADO),
        )
        .values_list("contenido", flat=True)
        .first()
    )
    if contenido is None:
        return base._fuera_de_ruta(request, 404)
    respuesta = HttpResponse(bytes(contenido), content_type="application/pdf")
    respuesta["Cache-Control"] = "no-store"
    respuesta["X-Content-Type-Options"] = "nosniff"
    respuesta["Content-Disposition"] = 'attachment; filename="recibo.pdf"'
    return respuesta


def _exigir_firma(request, negocio):
    remitente = Remitente.objects.filter(negocio=negocio, activo=True).first()
    parametros = {nombre: request.POST.getlist(nombre) for nombre in request.POST}
    firma = request.META.get("HTTP_X_TWILIO_SIGNATURE", "")
    url = settings.URL_PUBLICA + request.get_full_path()
    try:
        valida = remitente is not None and proveedores.activo().firma_valida(
            remitente, url, parametros, firma
        )
    except sobre.ErrorSobre:
        raise base.Denegado(403, "secreto_ilegible", negocio)
    if not valida:
        raise base.Denegado(403, "firma_de_twilio", negocio)


def _webhook(atender):
    def vista(request, identificador):
        if request.method != "POST":
            return base._negar(405)
        if base._demasiados_rechazos(request):
            return base._negar(429)
        try:
            atender(request, identificador)
        except base.Denegado as error:
            base._anotar_rechazo(request, error)
            return base._negar(error.estado)
        return HttpResponse(headers=RESPUESTAS_VACIAS)

    return vista


@_webhook
def estado_twilio(request, identificador):
    mensaje = Mensaje.objects.select_related("negocio").filter(pk=identificador).first()
    if mensaje is None:
        raise base.Denegado(404, "mensaje_desconocido")
    _exigir_firma(request, mensaje.negocio)
    servicios.aplicar_estado(
        mensaje,
        request.POST.get("MessageStatus", ""),
        request.POST.get("ErrorCode", ""),
    )


@_webhook
def entrante_twilio(request, identificador):
    negocio = Negocio.objects.filter(pk=identificador).first()
    if negocio is None:
        raise base.Denegado(404, "negocio_desconocido")
    _exigir_firma(request, negocio)
    servicios.aplicar_entrante(
        negocio,
        request.POST.get("From", ""),
        request.POST.get("Body", ""),
        request.POST.get("MessageSid") or request.POST.get("SmsSid", ""),
    )
