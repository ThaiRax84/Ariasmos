from django.core.management.base import BaseCommand, CommandError

from respaldos import servicios
from respaldos.models import Respaldo


class Command(BaseCommand):
    help = "Abre el último respaldo en una carpeta temporal, verifica la base, los conteos y la bitácora, y la borra"

    def add_arguments(self, parser):
        parser.add_argument("--archivo", help="Respaldo a probar (por defecto el último de la carpeta)")

    def handle(self, *args, **opciones):
        registro = servicios.probar(archivo=opciones.get("archivo"))
        if registro is None or registro.resultado != Respaldo.CORRECTO:
            raise CommandError(f"La prueba falló: {registro.mensaje if registro else 'otra prueba está en curso'}")
        self.stdout.write(self.style.SUCCESS(f"Prueba correcta: {registro.archivo} · {registro.conteos}"))
