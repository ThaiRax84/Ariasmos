from django.core.management.base import BaseCommand

from banco.catalogo import cargar


class Command(BaseCommand):
    help = "Carga o actualiza el catalogo de bancos sin borrar ni duplicar"

    def handle(self, *args, **opciones):
        creados, actualizados = cargar()
        self.stdout.write(self.style.SUCCESS(f"Bancos nuevos: {creados}; actualizados: {actualizados}"))
