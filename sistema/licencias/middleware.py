from django.http import HttpResponse
from django.urls import Resolver404, resolve

from . import servicios

METODOS_DE_CONSULTA = ("GET", "HEAD", "OPTIONS")
CABECERA = "X-Ariasmos-Licencia"
LIBRES = {
    "entrar",
    "entrar_codigo",
    "salir",
    "confirmar",
    "dispositivo_pendiente",
    "respaldos:respaldar",
    "respaldos:probar",
}
TEXTO = (
    "La licencia de Ariasmos venció, por eso el programa está en modo de solo consulta.\n"
    "Puedes ver tu información, descargar tus reportes y hacer respaldos, "
    "pero no se pueden registrar cobros ni otros movimientos.\n"
    "Para volver a trabajar con normalidad, ponte en contacto con quien te dio el programa "
    "y pídele que ponga al corriente tu licencia. Si te dio un código de activación nuevo, "
    "actívalo con el comando licencia_activar."
)


def _es_libre(request):
    try:
        coincidencia = resolve(request.path_info, getattr(request, "urlconf", None))
    except Resolver404:
        return False
    return coincidencia.view_name in LIBRES


class Candado:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.method not in METODOS_DE_CONSULTA
            and not _es_libre(request)
            and not servicios.permite_escribir()
        ):
            respuesta = HttpResponse(
                TEXTO, status=403, content_type="text/plain; charset=utf-8"
            )
            respuesta[CABECERA] = "solo-consulta"
            respuesta["Cache-Control"] = "no-store"
            return respuesta
        return self.get_response(request)
