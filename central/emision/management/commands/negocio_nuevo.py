from django.core.management.base import BaseCommand, CommandError

from emision import servicios


class Command(BaseCommand):
    help = "Da de alta un negocio nuevo"

    def add_arguments(self, parser):
        parser.add_argument("--nombre", required=True)
        parser.add_argument("--contacto", default="")
        parser.add_argument("--plan", default="base")
        parser.add_argument(
            "--instalaciones",
            type=int,
            default=1,
            help="Cuántos equipos puede activar el negocio",
        )

    def handle(self, *args, **opciones):
        try:
            negocio = servicios.crear_negocio(
                opciones["nombre"],
                opciones["contacto"],
                opciones["plan"],
                instalaciones=opciones["instalaciones"],
            )
        except ValueError as error:
            raise CommandError(str(error))
        self.stdout.write(f"Negocio dado de alta: {negocio.nombre}")
        self.stdout.write(f"Identificador: {negocio.pk}")
        self.stdout.write(
            "Con ese identificador puedes sacar su código de activación y registrar sus pagos."
        )
