import http.client
import json
import ssl
import urllib.error
import urllib.request

from django.conf import settings

from nucleo.licencia import momento_de

TIEMPO_LIMITE = 15
TIEMPO_LIMITE_HORA = 5
LIMITE_RESPUESTA = 64 * 1024


class SinConexion(Exception):
    pass


# Una redirección podría llevar la petición firmada a una dirección sin https.
class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *argumentos, **opciones):
        return None


def _direccion(ruta):
    base = settings.CENTRAL_URL
    if not isinstance(base, str) or not base.startswith("https://"):
        raise SinConexion("No hay una dirección segura de Central configurada.")
    return base.rstrip("/") + ruta


def _pedir(peticion, tiempo):
    abridor = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        _SinRedireccion,
    )
    try:
        with abridor.open(peticion, timeout=tiempo) as respuesta:
            estado, crudos = respuesta.status, respuesta.read(LIMITE_RESPUESTA + 1)
    except urllib.error.HTTPError as error:
        error.close()
        return error.code, {}
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise SinConexion(str(error))
    if len(crudos) > LIMITE_RESPUESTA:
        raise SinConexion("La respuesta de Central es demasiado grande.")
    try:
        datos = json.loads(crudos.decode("utf-8"))
    except (ValueError, RecursionError):
        raise SinConexion("La respuesta de Central no se entiende.")
    if not isinstance(datos, dict):
        raise SinConexion("La respuesta de Central no se entiende.")
    return estado, datos


def enviar(ruta, cuerpo):
    peticion = urllib.request.Request(
        _direccion(ruta),
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    return _pedir(peticion, TIEMPO_LIMITE)


def hora_central():
    try:
        peticion = urllib.request.Request(
            _direccion("/v1/salud"),
            headers={"Accept": "application/json"},
            method="GET",
        )
        estado, datos = _pedir(peticion, TIEMPO_LIMITE_HORA)
        return momento_de(datos["hora"]) if estado == 200 else None
    except (SinConexion, KeyError, ValueError):
        return None
