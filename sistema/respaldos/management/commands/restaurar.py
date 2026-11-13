from django.core.management.base import BaseCommand, CommandError

from nucleo import sobre
from respaldos import servicios
from respaldos.restauracion import restaurar


class Command(BaseCommand):
    help = "Restaura una instalación desde un respaldo cifrado y la clave de recuperación"

    def add_arguments(self, parser):
        parser.add_argument("--archivo", required=True)
        parser.add_argument("--clave", required=True, help="Clave de recuperación tal como se imprimió")
        parser.add_argument("--reemplazar", action="store_true", help="Sustituye la instalación existente (guarda antes una copia)")

    def handle(self, *args, **opciones):
        try:
            resultado = restaurar(opciones["archivo"], opciones["clave"], opciones["reemplazar"])
        except (sobre.ErrorSobre, servicios.ErrorRespaldo, OSError) as error:
            raise CommandError(str(error))
        self.stdout.write(self.style.SUCCESS(f"Instalación restaurada en {resultado['destino']}: {resultado['conteos']}, bitácora íntegra con {resultado['eventos']} eventos."))
        if resultado["copia_anterior"]:
            self.stdout.write(f"La instalación anterior quedó copiada en {resultado['copia_anterior']}.")
        self.stdout.write("Siguiente paso: python manage.py migrate y reinicia el servicio.")
