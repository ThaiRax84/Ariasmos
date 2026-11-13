from django.core.management.base import BaseCommand, CommandError

from respaldos import servicios
from respaldos.models import Respaldo


class Command(BaseCommand):
    help = "Hace un respaldo cifrado de la base, las claves y el ancla en la carpeta de respaldo configurada"

    def handle(self, *args, **opciones):
        registro = servicios.respaldar()
        if registro is None or registro.resultado != Respaldo.CORRECTO:
            raise CommandError(f"El respaldo falló: {registro.mensaje if registro else 'otro respaldo está en curso'}")
        self.stdout.write(self.style.SUCCESS(f"Respaldo listo: {registro.archivo} ({registro.tamano} bytes)"))
