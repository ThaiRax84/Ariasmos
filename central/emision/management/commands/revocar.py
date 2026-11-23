from django.core.management.base import BaseCommand, CommandError

from emision import servicios

from ._negocio import negocio_de


class Command(BaseCommand):
    help = "Cancela la licencia de un negocio (o de uno solo de sus equipos), o la restablece"

    def add_arguments(self, parser):
        parser.add_argument("negocio", help="Identificador del negocio")
        parser.add_argument(
            "--instalacion",
            help="Huella de un solo equipo; sin ella se cancela todo el negocio",
        )
        parser.add_argument(
            "--deshacer",
            action="store_true",
            help="Restablece lo que se había cancelado",
        )

    def handle(self, *args, **opciones):
        negocio = negocio_de(opciones["negocio"])
        try:
            servicios.revocar(negocio, opciones["instalacion"], opciones["deshacer"])
        except LookupError as error:
            raise CommandError(str(error))
        alcance = (
            "un equipo de " + negocio.nombre
            if opciones["instalacion"]
            else negocio.nombre
        )
        if opciones["deshacer"]:
            self.stdout.write(
                f"Listo: se restableció la licencia de {alcance}. Recuperará el permiso en su próxima renovación."
            )
        else:
            self.stdout.write(
                f"Listo: se canceló la licencia de {alcance}. Quedará en solo consulta en su próxima renovación."
            )
