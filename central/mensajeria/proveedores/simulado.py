import hmac
import secrets

from mensajeria.models import Plantilla

FIRMA = "firma-de-prueba"
MARCA_DE_RECHAZO = "[rechazar]"
MOTIVO_DE_RECHAZO = "Rechazada por la revisión simulada."
ENVIADOS = []


def _veredicto(plantilla):
    if MARCA_DE_RECHAZO in plantilla.texto:
        return Plantilla.RECHAZADA, MOTIVO_DE_RECHAZO
    return Plantilla.APROBADA, ""


def crear_plantilla(remitente, plantilla):
    estado, motivo = _veredicto(plantilla)
    return f"HX{secrets.token_hex(16)}", estado, motivo


def estado_plantilla(remitente, plantilla):
    return plantilla.estado, plantilla.motivo


def enviar(remitente, plantilla, destino, valores, url_documento, url_estado):
    ENVIADOS.append(
        {
            "numero": remitente.numero,
            "plantilla": plantilla.clave,
            "destino": destino,
            "valores": dict(valores),
            "url_documento": url_documento,
            "url_estado": url_estado,
        }
    )
    return f"SM{secrets.token_hex(16)}"


def firma_valida(remitente, url, parametros, firma):
    return hmac.compare_digest(str(firma).encode("utf-8"), FIRMA.encode("utf-8"))
