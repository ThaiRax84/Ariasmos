import json

from django.db import transaction
from django.utils import timezone

from nucleo import cadena

from .models import Evento


def _ip(request):
    if request is None:
        return ""
    return request.META.get("REMOTE_ADDR", "")[:45]


def _limpiar(datos):
    return json.loads(json.dumps(datos or {}, default=str, ensure_ascii=False))


def registrar(accion, usuario=None, objeto=None, datos=None, request=None):
    if usuario is not None and not getattr(usuario, "is_authenticated", False):
        usuario = None
    if usuario is None and request is not None and getattr(request, "user", None) is not None:
        if request.user.is_authenticated:
            usuario = request.user
    with transaction.atomic():
        anterior = Evento.objects.order_by("-id").values_list("hash", flat=True).first() or cadena.GENESIS
        evento = Evento(
            momento=timezone.now(),
            usuario=usuario,
            usuario_texto=usuario.usuario if usuario else "",
            accion=accion,
            objeto_tipo=objeto._meta.label_lower if objeto is not None else "",
            objeto_id=str(objeto.pk) if objeto is not None else "",
            datos=_limpiar(datos),
            ip=_ip(request),
            hash_anterior=anterior,
        )
        evento.hash = cadena.encadenar(anterior, evento.contenido())
        evento.save()
    return evento


def verificar_cadena():
    anterior = cadena.GENESIS
    total = 0
    for evento in Evento.objects.order_by("id").iterator():
        if evento.hash_anterior != anterior or cadena.encadenar(anterior, evento.contenido()) != evento.hash:
            return False, evento.pk, total
        anterior = evento.hash
        total += 1
    return True, None, total
