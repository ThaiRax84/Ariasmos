import base64
import binascii
import json
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.http import HttpResponse

from nucleo import licencia

from . import ajustes, origen, reloj, servicios
from .models import CodigoActivacion, Instalacion, Rechazo, Sello

LIMITE_CUERPO = 16 * 1024
LARGO_LLAVE_BASE64 = 44
LARGO_CODIGO_MAXIMO = 40
CAMPOS_ACTIVAR = ("codigo", "llave_publica", "carga", "firma")
CAMPOS_RENOVAR = ("instalacion", "carga", "firma")
RESPUESTAS = {
    400: {"error": "peticion"},
    403: {"error": "rechazada"},
    405: {"error": "peticion"},
    413: {"error": "peticion"},
    429: {"error": "espera"},
}


class Denegado(Exception):
    def __init__(self, estado, causa, negocio=None):
        super().__init__(causa)
        self.estado = estado
        self.causa = causa
        self.negocio = negocio


def _responder(datos, estado=200):
    respuesta = HttpResponse(json.dumps(datos, separators=(",", ":")), status=estado, content_type="application/json")
    respuesta["Cache-Control"] = "no-store"
    return respuesta


def _negar(estado):
    return _responder(RESPUESTAS[estado], estado)


def _anotar_rechazo(request, error):
    sitio = origen.de(request)
    with transaction.atomic():
        Rechazo.objects.create(origen=sitio, momento=reloj.ahora())
        servicios.anotar("rechazo", error.negocio, sitio, causa=error.causa, estado=error.estado, ruta=request.path)


def _demasiados_rechazos(request):
    desde = reloj.ahora() - timedelta(hours=1)
    return Rechazo.objects.filter(origen=origen.de(request), momento__gt=desde).count() >= ajustes.valor("rechazos_por_hora")


def _leer_cuerpo(request):
    largo = request.META.get("CONTENT_LENGTH", "")
    if largo.isascii() and largo.isdigit() and int(largo) > LIMITE_CUERPO:
        raise Denegado(413, "cuerpo_grande")
    crudo = request.read(LIMITE_CUERPO + 1)
    if len(crudo) > LIMITE_CUERPO:
        raise Denegado(413, "cuerpo_grande")
    return crudo


def _campos(request, esperados):
    try:
        cuerpo = licencia.leer_json(_leer_cuerpo(request))
    except licencia.LicenciaInvalida:
        raise Denegado(400, "json_invalido")
    if not isinstance(cuerpo, dict) or set(cuerpo) != set(esperados):
        raise Denegado(400, "campos_distintos")
    if not all(isinstance(valor, str) for valor in cuerpo.values()):
        raise Denegado(400, "tipos_equivocados")
    return cuerpo


def _post(campos):
    def decorador(proceso):
        def vista(request):
            if request.method != "POST":
                return _negar(405)
            if _demasiados_rechazos(request):
                return _negar(429)
            try:
                return _responder(proceso(_campos(request, campos)))
            except Denegado as error:
                _anotar_rechazo(request, error)
                return _negar(error.estado)

        return vista

    return decorador


def _documento(cuerpo):
    return {"carga": cuerpo["carga"], "firma": cuerpo["firma"]}


def _llave_de(texto):
    if len(texto) != LARGO_LLAVE_BASE64:
        raise Denegado(400, "llave_invalida")
    try:
        crudos = base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        raise Denegado(400, "llave_invalida")
    if len(crudos) != 32:
        raise Denegado(400, "llave_invalida")
    return crudos


def _abrir(cuerpo, llave_publica, tipo, negocio=None):
    try:
        carga = licencia.abrir(_documento(cuerpo), [llave_publica], tipo)
    except licencia.LicenciaInvalida as error:
        raise Denegado(403, f"documento_{error.motivo}", negocio)
    return carga


def _tolerancia():
    return timedelta(minutes=ajustes.valor("minutos_tolerancia"))


def _momento_reciente(carga, tolerancia, negocio=None):
    if abs(reloj.ahora() - licencia.momento_de(carga["momento"])) > tolerancia:
        raise Denegado(403, "hora_fuera_de_tolerancia", negocio)


def _anotar_renovacion(instalacion, version):
    Instalacion.objects.filter(pk=instalacion.pk).update(ultima_renovacion=reloj.ahora(), ultima_version=version[:20])


def salud(request):
    if request.method not in ("GET", "HEAD"):
        return _negar(405)
    return _responder({"estado": "ok"})


@_post(CAMPOS_RENOVAR)
def renovar(cuerpo):
    huella = cuerpo["instalacion"]
    if licencia.PATRON_INSTALACION.fullmatch(huella) is None:
        raise Denegado(400, "huella_invalida")
    instalacion = Instalacion.objects.select_related("negocio").filter(huella=huella).first()
    if instalacion is None:
        raise Denegado(403, "instalacion_desconocida")
    negocio = instalacion.negocio
    carga = _abrir(cuerpo, base64.b64decode(instalacion.llave_publica), "renovacion", negocio)
    if carga["instalacion"] != huella:
        raise Denegado(403, "instalacion_distinta", negocio)
    tolerancia = _tolerancia()
    _momento_reciente(carga, tolerancia, negocio)
    with transaction.atomic():
        _, nuevo = Sello.objects.get_or_create(instalacion=instalacion, valor=carga["sello"], defaults={"momento": reloj.ahora()})
        if not nuevo:
            raise Denegado(403, "peticion_repetida", negocio)
        Sello.objects.filter(momento__lt=reloj.ahora() - 2 * tolerancia).delete()
        if instalacion.revocada or negocio.revocado:
            servicios.anotar("revocada_avisada", negocio, instalacion=huella)
            return {"resultado": "revocada", "documento": servicios.revocacion_de(instalacion)}
        if not servicios.pago_al_corriente(negocio):
            return {"resultado": "pago_pendiente"}
        documento = servicios.emitir(instalacion)
        _anotar_renovacion(instalacion, carga["version"])
    return {"resultado": "renovada", "documento": documento}


def _validar_codigo(cuerpo):
    codigo = cuerpo["codigo"]
    if len(codigo) > LARGO_CODIGO_MAXIMO:
        raise Denegado(400, "codigo_largo")
    if not servicios.codigo_valido(codigo):
        raise Denegado(403, "codigo_invalido")
    return servicios.resumen_de(codigo)


def _comprobar_permiso(codigo, huella):
    negocio = codigo.negocio
    ahora = reloj.ahora()
    if codigo.usado is not None or codigo.vence <= ahora:
        raise Denegado(403, "codigo_gastado_o_vencido", negocio)
    if negocio.revocado:
        raise Denegado(403, "negocio_revocado", negocio)
    if Instalacion.objects.filter(huella=huella).exists():
        raise Denegado(403, "huella_repetida", negocio)
    if Instalacion.objects.filter(negocio=negocio, revocada=False).count() >= negocio.instalaciones_permitidas:
        raise Denegado(403, "sin_cupo", negocio)
    return negocio


def _crear_instalacion(codigo, huella, llave_texto):
    negocio = _comprobar_permiso(codigo, huella)
    if not CodigoActivacion.objects.filter(pk=codigo.pk, usado__isnull=True).update(usado=reloj.ahora()):
        raise Denegado(403, "codigo_gastado_o_vencido", negocio)
    instalacion = Instalacion.objects.create(negocio=negocio, huella=huella, llave_publica=llave_texto, activada=True)
    servicios.anotar("instalacion_activada", negocio, instalacion=huella)
    return instalacion


@_post(CAMPOS_ACTIVAR)
def activar(cuerpo):
    resumen = _validar_codigo(cuerpo)
    llave_publica = _llave_de(cuerpo["llave_publica"])
    huella = licencia.huella(llave_publica)
    carga = _abrir(cuerpo, llave_publica, "activacion")
    if carga["instalacion"] != huella:
        raise Denegado(403, "instalacion_distinta")
    _momento_reciente(carga, _tolerancia())
    try:
        with transaction.atomic():
            codigo = CodigoActivacion.objects.select_related("negocio").filter(resumen=resumen).first()
            if codigo is None:
                raise Denegado(403, "codigo_desconocido")
            instalacion = _crear_instalacion(codigo, huella, cuerpo["llave_publica"])
            if not servicios.pago_al_corriente(codigo.negocio):
                return {"resultado": "pago_pendiente"}
            documento = servicios.emitir(instalacion)
            _anotar_renovacion(instalacion, carga["version"])
    except IntegrityError:
        raise Denegado(403, "huella_repetida")
    return {"resultado": "activada", "documento": documento}
