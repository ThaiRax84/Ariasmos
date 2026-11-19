from django.core.management.base import BaseCommand

from banco import llegadas


class Command(BaseCommand):
    help = "Consulta los orígenes de transferencias configurados y pasa lo que llegó por la puerta de llegada"

    def handle(self, *args, **opciones):
        for importacion in llegadas.consultar_todos():
            if importacion is not None:
                self.stdout.write(f"{importacion.nombre_archivo}: {importacion.aplicados} aplicados, {importacion.nuevos} nuevos")
