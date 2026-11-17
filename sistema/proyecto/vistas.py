from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils.http import quote_etag

from caja.servicios import turno_abierto
from configuracion import marca as marca_negocio
from cortes import servicios as cortes
from cuentas.decoradores import requiere_sesion
from cuentas.models import Delegacion
from solicitudes import motor
from solicitudes.models import Solicitud
from solicitudes.views import pendientes_para

from . import tablero
from proyecto.avisos import contexto_inicio


@requiere_sesion
def inicio(request):
    usuario = request.user
    motor.caducar_vencidas()
    turno = turno_abierto(usuario) if usuario.tiene_permiso("turno_caja") else None
    diarios = cortes.diarios_pendientes() if usuario.tiene_permiso("recibir_efectivo") else []
    certificado = tablero.certificado_para(usuario)
    dispositivos = tablero.dispositivos_para(usuario)
    contexto = {
        "perfil": tablero.perfil(usuario),
        "pendientes": pendientes_para(usuario),
        "propias": Solicitud.objects.filter(solicitante=usuario, estado=Solicitud.PENDIENTE).select_related("titular"),
        "delegaciones": Delegacion.objects.vigentes().filter(receptor=usuario).select_related("otorgante"),
        "dispositivos_pendientes": dispositivos,
        "cifras": tablero.cifras(usuario, diarios=diarios),
        "salud": tablero.salud(usuario, certificado, dispositivos),
        "avisos": tablero.ordenar(tablero.avisos_control(usuario, certificado, diarios)),
    }
    if turno is not None:
        contexto["cobros_turno"] = turno.pagos.count()
        contexto["corte_propio"] = tablero.corte_propio(turno)
    contexto.update(contexto_inicio(usuario))
    return render(request, "inicio.html", contexto)


def _guardable(respuesta, version, etiqueta):
    respuesta["Cache-Control"] = "private, max-age=31536000, immutable"
    respuesta["ETag"] = quote_etag(f"{etiqueta}-{version}")
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


@requiere_sesion
def marca_css(request):
    actual = marca_negocio.actual()
    version = actual.version if actual else 0
    respuesta = HttpResponse(marca_negocio.hoja(actual), content_type="text/css; charset=utf-8")
    if request.GET.get("v") != str(version):
        respuesta["Cache-Control"] = "no-store"
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta
    return _guardable(respuesta, version, "marca")


@requiere_sesion
def marca_logo(request):
    from caja import comprobantes

    actual = marca_negocio.actual()
    if actual is None or not actual.logo:
        raise Http404
    try:
        contenido = marca_negocio.leer_logo(actual)
    except (OSError, comprobantes.ComprobanteInvalido, marca_negocio.MarcaInvalida):
        marca_negocio.avisar_logo_alterado(actual, request)
        raise Http404
    respuesta = HttpResponse(contenido, content_type=comprobantes.TIPOS_MIME[actual.logo_tipo])
    respuesta["Content-Security-Policy"] = "default-src 'none'; sandbox"
    respuesta["Content-Disposition"] = "inline"
    if request.GET.get("v") != str(actual.version):
        respuesta["Cache-Control"] = "no-store"
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta
    return _guardable(respuesta, actual.version, "logo")

