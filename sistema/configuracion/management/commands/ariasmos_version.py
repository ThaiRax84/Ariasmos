from django.core.management.base import BaseCommand

from proyecto.version import actual


class Command(BaseCommand):
    help = "Muestra la versión instalada de Ariasmos"

    def handle(self, *args, **opciones):
        self.stdout.write(f"Ariasmos {actual()}")
