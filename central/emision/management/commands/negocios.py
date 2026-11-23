from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Q

from emision.models import Instalacion, Negocio


def _fecha(valor, formato):
    return valor.strftime(formato) if valor else "nunca"


class Command(BaseCommand):
    help = "Lista los negocios con su pago, sus equipos y su última renovación"

    def handle(self, *args, **opciones):
        versiones = {}
        for negocio, version in (
            Instalacion.objects.exclude(ultima_renovacion=None)
            .order_by("ultima_renovacion")
            .values_list("negocio_id", "ultima_version")
        ):
            versiones[negocio] = version
        lista = Negocio.objects.annotate(
            equipos=Count("instalacion", filter=Q(instalacion__revocada=False)),
            renovada=Max("instalacion__ultima_renovacion"),
        ).order_by("nombre")
        if not lista:
            self.stdout.write("Todavía no hay negocios dados de alta.")
        for negocio in lista:
            estado = " (cancelado)" if negocio.revocado else ""
            self.stdout.write(
                f"{negocio.nombre}{estado} | id {negocio.pk} | pagado hasta {_fecha(negocio.pagado_hasta, '%d/%m/%Y')} | "
                f"equipos {negocio.equipos} de {negocio.instalaciones_permitidas} | última renovación {_fecha(negocio.renovada, '%d/%m/%Y %H:%M')} | "
                f"versión {versiones.get(negocio.pk) or 'sin datos'}"
            )
