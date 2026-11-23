from django.core.exceptions import ValidationError
from django.core.management.base import CommandError

from emision.models import Negocio


def negocio_de(texto):
    try:
        return Negocio.objects.get(pk=texto)
    except (Negocio.DoesNotExist, ValidationError):
        raise CommandError("No existe un negocio con ese identificador. Usa el comando negocios para ver la lista.")
