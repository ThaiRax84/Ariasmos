import time
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connection

from configuracion.models import Negocio, parametro
from configuracion.trabajador import ejecutar_ciclo


class Command(BaseCommand):
    help = "Ejecuta las tareas periódicas: cargos, recargos, solicitudes, equipos y verificación de la bitácora"

    def add_arguments(self, parser):
        parser.add_argument("--una-vez", action="store_true", help="Ejecuta un ciclo y termina")
        parser.add_argument("--fecha", help="Fecha del negocio a usar (AAAA-MM-DD); solo para pruebas o recuperación")

    def _renovar_conexion(self):
        if not connection.in_atomic_block:
            close_old_connections()

    def handle(self, *args, **opciones):
        negocio = Negocio.actual()
        if negocio is None or not negocio.configurado:
            raise CommandError("La instalación todavía no está configurada.")
        fecha = None
        if opciones["fecha"]:
            try:
                fecha = date.fromisoformat(opciones["fecha"])
            except ValueError:
                raise CommandError("Fecha no válida; usa AAAA-MM-DD.")
        while True:
            self._renovar_conexion()
            for nombre, exito, texto in ejecutar_ciclo(fecha):
                self.stdout.write(f"{'ok   ' if exito else 'FALLA'} {nombre}: {texto}")
            self._renovar_conexion()
            if opciones["una_vez"]:
                return
            try:
                time.sleep(max(parametro("segundos_ciclo_trabajador"), 30))
            except KeyboardInterrupt:
                return
