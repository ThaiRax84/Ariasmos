import json
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from nucleo import cadena
from proyecto.red import ip_cliente

from . import ancla
from .models import Evento, Verificacion


def _ip(request):
    return ip_cliente(request)[:45]


def _limpiar(datos):
    return json.loads(json.dumps(datos or {}, default=str, ensure_ascii=False))


def titular_de(objeto):
    if objeto is None:
        return None
    if objeto._meta.label_lower == "titulares.titular":
        return objeto.pk
    if getattr(objeto, "titular_id", None):
        return objeto.titular_id
    solicitud = getattr(objeto, "solicitud", None) if getattr(objeto, "solicitud_id", None) else None
    if solicitud is not None:
        return solicitud.titular_id
    return None


def diferencias(antes, despues):
    cambios = {}
    for clave in sorted(set(antes) | set(despues)):
        anterior, nuevo = antes.get(clave), despues.get(clave)
        if anterior != nuevo:
            cambios[clave] = [anterior, nuevo]
    return cambios


def registrar(accion, usuario=None, objeto=None, datos=None, request=None, titular=None):
    if usuario is not None and not getattr(usuario, "is_authenticated", False):
        usuario = None
    if usuario is None and request is not None and getattr(request, "user", None) is not None:
        if request.user.is_authenticated:
            usuario = request.user
    dispositivo = getattr(request, "dispositivo", None) if request is not None else None
    with transaction.atomic():
        ultimo = Evento.objects.order_by("-numero").values_list("numero", "sello").first()
        numero, anterior = (ultimo[0] + 1, ultimo[1]) if ultimo else (1, cadena.GENESIS)
        evento = Evento(
            numero=numero,
            momento=timezone.now(),
            usuario=usuario,
            usuario_texto=usuario.usuario if usuario else "",
            equipo=dispositivo.pk if dispositivo is not None else None,
            accion=accion,
            objeto_tipo=objeto._meta.label_lower if objeto is not None else "",
            objeto_id=str(objeto.pk) if objeto is not None else "",
            titular=titular if titular is not None else titular_de(objeto),
            datos=_limpiar(datos),
            ip=_ip(request),
            sello_anterior=anterior,
        )
        evento.sello = cadena.sellar(settings.CLAVE_AUDITORIA, anterior, evento.contenido())
        evento.save()
        momento = evento.momento.isoformat()
        transaction.on_commit(lambda: ancla.escribir(numero, evento.sello, momento))
    return evento


@dataclass
class Resultado:
    valida: bool
    numero: int = None
    total: int = 0
    motivo: str = ""


MOTIVOS = {
    "hueco": "falta un evento en la numeración",
    "sello": "un evento fue alterado",
    "sin_ancla": "falta el ancla externa",
    "ancla_alterada": "el ancla externa no es auténtica",
    "ancla_no_coincide": "la base no contiene el último evento anclado (se borraron eventos o se restauró una copia vieja)",
}


def _revisar():
    clave = settings.CLAVE_AUDITORIA
    anterior = cadena.GENESIS
    esperado = 1
    ultimo = None
    for evento in Evento.objects.order_by("numero").iterator():
        if evento.numero != esperado:
            return Resultado(False, esperado, esperado - 1, "hueco")
        if evento.sello_anterior != anterior or cadena.sellar(clave, anterior, evento.contenido()) != evento.sello:
            return Resultado(False, evento.numero, esperado - 1, "sello")
        anterior = evento.sello
        ultimo = evento
        esperado += 1
    total = esperado - 1
    registro = ancla.leer()
    if registro is None:
        if total:
            return Resultado(False, None, total, "sin_ancla")
        return Resultado(True, None, 0)
    if not ancla.es_autentica(registro):
        return Resultado(False, None, total, "ancla_alterada")
    numero_ancla = registro["numero"]
    if ultimo is None or numero_ancla > ultimo.numero:
        return Resultado(False, numero_ancla, total, "ancla_no_coincide")
    if not Evento.objects.filter(numero=numero_ancla, sello=registro["sello"]).exists():
        return Resultado(False, numero_ancla, total, "ancla_no_coincide")
    return Resultado(True, None, total)


def verificar_cadena(usuario=None, guardar=False):
    resultado = _revisar()
    if guardar:
        Verificacion.objects.create(usuario=usuario, valida=resultado.valida, numero=resultado.numero, motivo=resultado.motivo, eventos=resultado.total)
    return resultado


def ultima_verificacion():
    return Verificacion.objects.first()
