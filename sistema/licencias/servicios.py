import base64
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from auditoria.models import Evento
from auditoria.servicios import registrar
from nucleo import licencia, sobre
from proyecto import version

from . import cliente, llaves, politica, reloj
from .models import Instalacion

CONTEXTO_LLAVE = "licencias|llave"
HORAS_ENTRE_AVISOS_DE_RELOJ = 6


@dataclass(frozen=True)
class Situacion:
    estado: str
    motivo: str
    vence: datetime | None
    limite: datetime | None


def _clave_secreta():
    return sobre.derivar(bytes(settings.CLAVE_SECRETOS), "licencias")


def _bytes_publicos(privada):
    return privada.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _fila_nueva():
    privada = Ed25519PrivateKey.generate()
    secreto = base64.b64encode(privada.private_bytes_raw()).decode("ascii")
    ahora = reloj.ahora()
    return Instalacion(
        pk=1,
        llave_cifrada=sobre.cifrar_texto(_clave_secreta(), secreto, CONTEXTO_LLAVE),
        huella=licencia.huella(_bytes_publicos(privada)),
        primer_arranque=ahora,
        mayor_momento=ahora,
    )


def instalacion():
    fila = Instalacion.objects.filter(pk=1).first()
    if fila is None:
        Instalacion.objects.bulk_create([_fila_nueva()], ignore_conflicts=True)
        fila = Instalacion.objects.get(pk=1)
    return fila


def identidad():
    fila = instalacion()
    secreto = sobre.descifrar_texto(_clave_secreta(), fila.llave_cifrada, CONTEXTO_LLAVE)
    return fila.huella, Ed25519PrivateKey.from_private_bytes(base64.b64decode(secreto))


def _avisar_reloj_atrasado(actual, mayor):
    desde = timezone.now() - timedelta(hours=HORAS_ENTRE_AVISOS_DE_RELOJ)
    if not Evento.objects.filter(accion="reloj_atrasado", momento__gte=desde).exists():
        registrar("reloj_atrasado", datos={"reloj": licencia.texto_de(actual), "mayor_visto": licencia.texto_de(mayor)})


def _efectivo(fila):
    actual = reloj.ahora()
    if actual > fila.mayor_momento + politica.PASO_RELOJ:
        Instalacion.objects.filter(pk=1, mayor_momento__lt=actual).update(mayor_momento=actual)
        fila.mayor_momento = actual
    elif actual < fila.mayor_momento - politica.TOLERANCIA_RELOJ:
        _avisar_reloj_atrasado(actual, fila.mayor_momento)
    return max(actual, fila.mayor_momento)


def momento_efectivo():
    return _efectivo(instalacion())


def _guardado(texto, tipo, claves):
    if not texto:
        return None
    try:
        return licencia.abrir(json.loads(texto), claves, tipo)
    except (ValueError, RecursionError, licencia.LicenciaInvalida):
        return None


def _antes(una, otra):
    return licencia.momento_de(una) < licencia.momento_de(otra)


def _revocada(fila, claves, vigente):
    revocacion = _guardado(fila.revocacion, "revocacion", claves)
    if revocacion is None or revocacion["instalacion"] != fila.huella:
        return False
    return vigente is None or not _antes(revocacion["emitida"], vigente["emitida"])


def _de_licencia(fila, vigente):
    vence = licencia.momento_de(vigente["vence"])
    limite = vence + timedelta(days=vigente["dias_gracia"])
    t = _efectivo(fila)
    if t <= vence:
        return Situacion("vigente", "", vence, limite)
    if t <= limite:
        return Situacion("gracia", "", vence, limite)
    return Situacion("solo_consulta", "vencida", vence, limite)


def _sin_licencia(fila):
    limite = fila.primer_arranque + timedelta(days=politica.DIAS_PARA_ACTIVAR)
    if _efectivo(fila) <= limite:
        return Situacion("por_activar", "", None, limite)
    return Situacion("solo_consulta", "sin_licencia", None, limite)


def _llaves():
    try:
        return llaves.publicas()
    except ImproperlyConfigured:
        return None


def situacion():
    claves = _llaves()
    if claves is None:
        return Situacion("solo_consulta", "llaves", None, None)
    if not claves:
        return Situacion("libre", "", None, None)
    fila = instalacion()
    vigente = _guardado(fila.documento, "licencia", claves)
    if vigente is not None and vigente["instalacion"] != fila.huella:
        vigente = None
    if _revocada(fila, claves, vigente):
        return Situacion("solo_consulta", "revocada", None, None)
    if vigente is not None:
        return _de_licencia(fila, vigente)
    return _sin_licencia(fila)


def permite_escribir():
    return situacion().estado != "solo_consulta"


def _abrir_propio(fila, documento, tipo, claves):
    carga = licencia.abrir(documento, claves, tipo)
    if carga["instalacion"] != fila.huella:
        raise licencia.LicenciaInvalida("ajena")
    guardada = _guardado(fila.documento, "licencia", claves)
    if guardada is not None and _antes(carga["emitida"], guardada["emitida"]):
        raise licencia.LicenciaInvalida("antigua")
    return carga


def _guardar_licencia(documento):
    fila = instalacion()
    claves = _llaves() or ()
    carga = _abrir_propio(fila, documento, "licencia", claves)
    revocacion = _guardado(fila.revocacion, "revocacion", claves)
    if revocacion is not None and _antes(revocacion["emitida"], carga["emitida"]):
        fila.revocacion = ""
    fila.documento = json.dumps(documento, sort_keys=True)
    fila.mayor_momento = max(fila.mayor_momento, licencia.momento_de(carga["emitida"]))
    fila.save(update_fields=["documento", "revocacion", "mayor_momento"])
    registrar("licencia_instalada", datos={"serie": carga["serie"], "vence": carga["vence"]})


def instalar(documento):
    try:
        with transaction.atomic():
            _guardar_licencia(documento)
    except licencia.LicenciaInvalida as error:
        registrar("licencia_rechazada", datos={"motivo": error.motivo})
        raise
    return situacion()


def _guardar_revocacion(documento):
    fila = instalacion()
    claves = _llaves() or ()
    _abrir_propio(fila, documento, "revocacion", claves)
    fila.revocacion = json.dumps(documento, sort_keys=True)
    fila.save(update_fields=["revocacion"])
    registrar("licencia_revocada")


def anotar_revocacion(documento):
    try:
        with transaction.atomic():
            _guardar_revocacion(documento)
    except licencia.LicenciaInvalida as error:
        registrar("licencia_rechazada", datos={"motivo": error.motivo})
        raise


def _peticion(tipo, huella, privada):
    carga = {
        "formato": licencia.FORMATO,
        "producto": licencia.PRODUCTO,
        "tipo": tipo,
        "instalacion": huella,
        "momento": licencia.texto_de(reloj.ahora()),
        "sello": secrets.token_hex(16),
        "version": version.actual(),
    }
    return licencia.firmar(carga, privada)


def _anotar_intento(resultado):
    Instalacion.objects.filter(pk=1).update(ultimo_intento=reloj.ahora(), ultimo_resultado=resultado)
    return resultado


def _recibir_renovacion(estado, respuesta):
    if estado != 200:
        return "rechazada"
    resultado, documento = respuesta.get("resultado"), respuesta.get("documento")
    try:
        if resultado == "renovada":
            instalar(documento)
        elif resultado == "revocada":
            anotar_revocacion(documento)
        elif resultado != "pago_pendiente":
            return "rechazada"
    except licencia.LicenciaInvalida:
        return "rechazada"
    return resultado


def renovar():
    if not _llaves():
        return "apagada"
    huella, privada = identidad()
    cuerpo = {"instalacion": huella, **_peticion("renovacion", huella, privada)}
    try:
        estado, respuesta = cliente.enviar("/v1/renovar", cuerpo)
    except cliente.SinConexion:
        return _anotar_intento("sin_conexion")
    return _anotar_intento(_recibir_renovacion(estado, respuesta))


def _recibir_activacion(estado, respuesta):
    if estado != 200:
        return "rechazada"
    resultado = respuesta.get("resultado")
    try:
        if resultado == "activada":
            instalar(respuesta.get("documento"))
        elif resultado != "pago_pendiente":
            return "rechazada"
    except licencia.LicenciaInvalida:
        return "rechazada"
    Instalacion.objects.filter(pk=1).update(activada=True)
    return resultado


def activar(codigo):
    if not _llaves():
        return "apagada"
    huella, privada = identidad()
    llave_publica = base64.b64encode(_bytes_publicos(privada)).decode("ascii")
    cuerpo = {"codigo": codigo, "llave_publica": llave_publica, **_peticion("activacion", huella, privada)}
    try:
        estado, respuesta = cliente.enviar("/v1/activar", cuerpo)
    except cliente.SinConexion:
        return "sin_conexion"
    return _recibir_activacion(estado, respuesta)


def tarea_renovar(hoy):
    if not _llaves():
        return "licencias apagadas en este programa"
    fila = instalacion()
    if not fila.activada:
        return "la licencia todavía no se activa en Central"
    if fila.ultimo_intento is not None and reloj.ahora() - fila.ultimo_intento < timedelta(hours=politica.HORAS_ENTRE_RENOVACIONES):
        return "todavía no toca renovar la licencia"
    return f"renovación de la licencia: {renovar()}"
