from datetime import date

from django.core.management.base import BaseCommand, CommandError

from emision import servicios

from ._negocio import negocio_de


class Command(BaseCommand):
    help = "Registra hasta qué día tiene pagada su licencia un negocio"

    def add_arguments(self, parser):
        parser.add_argument("negocio", help="Identificador del negocio")
        parser.add_argument("--hasta", required=True, help="Último día pagado, como AAAA-MM-DD")

    def handle(self, *args, **opciones):
        negocio = negocio_de(opciones["negocio"])
        try:
            hasta = date.fromisoformat(opciones["hasta"])
        except ValueError:
            raise CommandError("La fecha no es válida; escríbela como AAAA-MM-DD.")
        servicios.registrar_pago(negocio, hasta)
        self.stdout.write(f"Pago registrado: {negocio.nombre} queda pagado hasta el {hasta.strftime('%d/%m/%Y')}.")
