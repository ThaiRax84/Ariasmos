from django.core.management.base import BaseCommand, CommandError

from emision.management.commands._negocio import negocio_de
from emision.servicios import anotar
from mensajeria import servicios
from mensajeria.models import Cuota


class Command(BaseCommand):
    help = "Fija el máximo de mensajes al mes que un negocio puede elegir como tope"

    def add_arguments(self, parser):
        parser.add_argument("negocio", help="Identificador del negocio")
        parser.add_argument("--maximo", required=True, type=int, help="Mensajes al mes")

    def handle(self, *args, **opciones):
        negocio = negocio_de(opciones["negocio"])
        maximo = opciones["maximo"]
        if maximo < 1:
            raise CommandError("El máximo debe ser al menos 1.")
        cuota = servicios.cuota_de(negocio)
        Cuota.objects.filter(pk=cuota.pk).update(
            tope_maximo=maximo, tope=min(cuota.tope, maximo)
        )
        anotar("tope_maximo_cambiado", negocio, maximo=maximo)
        self.stdout.write(f"{negocio.nombre}: máximo de {maximo} mensajes al mes.")
