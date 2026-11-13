from django.core.management.base import BaseCommand, CommandError

from cortes.entrega import verificar


class Command(BaseCommand):
    help = "Verifica la firma del manifiesto y la huella de cada archivo en una carpeta de entrega"

    def add_arguments(self, parser):
        parser.add_argument("carpeta")

    def handle(self, *args, **opciones):
        problemas = verificar(opciones["carpeta"])
        if problemas:
            raise CommandError("\n".join(problemas))
        self.stdout.write(self.style.SUCCESS("Manifiesto firmado y todos los archivos coinciden con su huella."))
