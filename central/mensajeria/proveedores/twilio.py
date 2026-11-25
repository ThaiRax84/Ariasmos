import base64
import hashlib
import hmac
import http.client
import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from mensajeria import secretos
from mensajeria.models import Plantilla
from mensajeria.plantillas import con_numeros

from . import FalloProveedor

TIEMPO_LIMITE = 15
CONTENIDO = "https://content.twilio.com/v1/Content"
MENSAJES = "https://api.twilio.com/2010-04-01/Accounts/{cuenta}/Messages.json"
CATEGORIA = "UTILITY"
ESTADOS_DE_REVISION = {
    "approved": Plantilla.APROBADA,
    "rejected": Plantilla.RECHAZADA,
    "paused": Plantilla.RECHAZADA,
    "disabled": Plantilla.RECHAZADA,
}


def urlopen(peticion):
    return urllib.request.urlopen(peticion, timeout=TIEMPO_LIMITE)


def _autorizacion(remitente):
    credenciales = f"{remitente.cuenta_sid}:{secretos.token_de(remitente)}"
    return "Basic " + base64.b64encode(credenciales.encode("utf-8")).decode("ascii")


def _peticion(remitente, direccion, cuerpo=None, formulario=None):
    cabeceras = {
        "Authorization": _autorizacion(remitente),
        "Accept": "application/json",
    }
    datos = None
    if cuerpo is not None:
        datos = json.dumps(cuerpo).encode("utf-8")
        cabeceras["Content-Type"] = "application/json"
    elif formulario is not None:
        datos = urllib.parse.urlencode(formulario).encode("utf-8")
        cabeceras["Content-Type"] = "application/x-www-form-urlencoded"
    return urllib.request.Request(
        direccion,
        data=datos,
        headers=cabeceras,
        method="GET" if datos is None else "POST",
    )


def _codigo_de(error):
    try:
        codigo = json.loads(error.read()).get("code")
    except (OSError, ValueError, AttributeError):
        return ""
    return f", código {codigo}" if isinstance(codigo, int) else ""


def _ejecutar(peticion):
    try:
        with urlopen(peticion) as respuesta:
            crudo = respuesta.read()
    except urllib.error.HTTPError as error:
        motivo = f"Twilio rechazó la petición ({error.code}{_codigo_de(error)})."
        error.close()
        raise FalloProveedor(motivo)
    except (OSError, ValueError, http.client.HTTPException):
        raise FalloProveedor("No se pudo hablar con Twilio.")
    try:
        datos = json.loads(crudo.decode("utf-8"))
    except (ValueError, RecursionError):
        raise FalloProveedor("La respuesta de Twilio no se entiende.")
    if not isinstance(datos, dict):
        raise FalloProveedor("La respuesta de Twilio no se entiende.")
    return datos


def _numero_del_documento(plantilla):
    return len(plantilla.variables) + 1


def _contenido(plantilla):
    cuerpo = con_numeros(plantilla.texto, plantilla.variables)
    muestras = {str(i): nombre for i, nombre in enumerate(plantilla.variables, 1)}
    if not plantilla.con_documento:
        return muestras, {"twilio/text": {"body": cuerpo}}
    numero = _numero_del_documento(plantilla)
    muestras[str(numero)] = "documento"
    direccion = f"{settings.URL_PUBLICA}/v1/documentos/{{{{{numero}}}}}.pdf"
    return muestras, {"twilio/media": {"body": cuerpo, "media": [direccion]}}


def peticion_contenido(remitente, plantilla):
    muestras, tipos = _contenido(plantilla)
    cuerpo = {
        "friendly_name": plantilla.clave,
        "language": "es",
        "variables": muestras,
        "types": tipos,
    }
    return _peticion(remitente, CONTENIDO, cuerpo=cuerpo)


def peticion_aprobacion(remitente, plantilla, sid):
    cuerpo = {"name": plantilla.clave, "category": CATEGORIA}
    return _peticion(
        remitente, f"{CONTENIDO}/{sid}/ApprovalRequests/WhatsApp", cuerpo=cuerpo
    )


def peticion_estado(remitente, plantilla):
    return _peticion(
        remitente, f"{CONTENIDO}/{plantilla.id_proveedor}/ApprovalRequests"
    )


def _variables_del_mensaje(plantilla, valores, url_documento):
    variables = {
        str(i): valores[nombre] for i, nombre in enumerate(plantilla.variables, 1)
    }
    if plantilla.con_documento:
        token = url_documento.rsplit("/", 1)[1].removesuffix(".pdf")
        variables[str(_numero_del_documento(plantilla))] = token
    return variables


def peticion_mensaje(remitente, plantilla, destino, valores, url_documento, url_estado):
    formulario = {
        "To": f"whatsapp:{destino}",
        "MessagingServiceSid": remitente.servicio_sid,
        "ContentSid": plantilla.id_proveedor,
        "ContentVariables": json.dumps(
            _variables_del_mensaje(plantilla, valores, url_documento)
        ),
        "StatusCallback": url_estado,
    }
    return _peticion(
        remitente, MENSAJES.format(cuenta=remitente.cuenta_sid), formulario=formulario
    )


def _revision(datos):
    revision = datos.get("whatsapp", datos)
    estado = ESTADOS_DE_REVISION.get(revision.get("status"), Plantilla.EN_REVISION)
    motivo = revision.get("rejection_reason") or ""
    return estado, str(motivo)[:300]


def crear_plantilla(remitente, plantilla):
    sid = _ejecutar(peticion_contenido(remitente, plantilla)).get("sid")
    if not isinstance(sid, str) or not sid:
        raise FalloProveedor("Twilio no devolvió el identificador de la plantilla.")
    estado, motivo = _revision(
        _ejecutar(peticion_aprobacion(remitente, plantilla, sid))
    )
    return sid, estado, motivo


def estado_plantilla(remitente, plantilla):
    return _revision(_ejecutar(peticion_estado(remitente, plantilla)))


def enviar(remitente, plantilla, destino, valores, url_documento, url_estado):
    sid = _ejecutar(
        peticion_mensaje(
            remitente, plantilla, destino, valores, url_documento, url_estado
        )
    ).get("sid")
    if not isinstance(sid, str) or not sid:
        raise FalloProveedor("Twilio no devolvió el identificador del mensaje.")
    return sid


def _valores(valor):
    return [valor] if isinstance(valor, str) else sorted(valor)


def firma_esperada(token, url, parametros):
    texto = url + "".join(
        nombre + valor
        for nombre in sorted(parametros)
        for valor in _valores(parametros[nombre])
    )
    resumen = hmac.new(token.encode("utf-8"), texto.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(resumen.digest()).decode("ascii")


def firma_valida(remitente, url, parametros, firma):
    esperada = firma_esperada(secretos.token_de(remitente), url, parametros)
    return hmac.compare_digest(str(firma).encode("utf-8"), esperada.encode("utf-8"))
