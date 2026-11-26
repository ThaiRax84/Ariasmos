import re

from django.core.management.base import BaseCommand, CommandError

from emision.management.commands._negocio import negocio_de
from emision.servicios import anotar
from mensajeria import servicios
from mensajeria.models import Cuota

PATRON_PREFIJO = re.compile(r"[0-9]{1,4}")


class Command(BaseCommand):
    help = "Muestra o cambia los países a los que un negocio puede mandar mensajes"

    def add_arguments(self, parser):
        parser.add_argument("negocio", help="Identificador del negocio")
        parser.add_argument(
            "prefijos",
            nargs="*",
            help="Prefijos de país sin +, por ejemplo 52 1. Sin prefijos muestra los actuales",
        )

    def handle(self, *args, **opciones):
        negocio = negocio_de(opciones["negocio"])
        prefijos = list(dict.fromkeys(opciones["prefijos"]))
        cuota = servicios.cuota_de(negocio)
        if not prefijos:
            self.stdout.write(f"{negocio.nombre}: {', '.join(cuota.paises)}")
            return
        if any(PATRON_PREFIJO.fullmatch(p) is None for p in prefijos):
            raise CommandError("Cada prefijo lleva solo dígitos, de 1 a 4, sin el +.")
        Cuota.objects.filter(pk=cuota.pk).update(paises=prefijos)
        anotar("paises_cambiados", negocio, paises=prefijos)
        self.stdout.write(f"{negocio.nombre}: {', '.join(prefijos)}")
