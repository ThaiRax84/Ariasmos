from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from nucleo import sobre
from respaldos import servicios
from respaldos.restauracion import restaurar


class Command(BaseCommand):
    help = "Restaura una instalación desde un respaldo cifrado y la clave de recuperación"

    def add_arguments(self, parser):
        parser.add_argument("--archivo", required=True)
        clave = parser.add_mutually_exclusive_group(required=True)
        clave.add_argument("--clave", help="Clave de recuperación tal como se imprimió")
        clave.add_argument("--clave-archivo", help="Archivo de texto con la clave de recuperación (se lee y no se modifica)")
        parser.add_argument("--reemplazar", action="store_true", help="Sustituye la instalación existente (guarda antes una copia)")

    def handle(self, *args, **opciones):
        texto = opciones["clave"]
        if opciones["clave_archivo"]:
            try:
                texto = Path(opciones["clave_archivo"]).read_text(encoding="utf-8-sig").strip()
            except OSError as error:
                raise CommandError(f"No se pudo leer el archivo de la clave: {error}")
        try:
            resultado = restaurar(opciones["archivo"], texto, opciones["reemplazar"])
        except (sobre.ErrorSobre, servicios.ErrorRespaldo, OSError) as error:
            raise CommandError(str(error))
        self.stdout.write(self.style.SUCCESS(f"Instalación restaurada en {resultado['destino']}: {resultado['conteos']}, bitácora íntegra con {resultado['eventos']} eventos."))
        if resultado["copia_anterior"]:
            self.stdout.write(f"La instalación anterior quedó copiada en {resultado['copia_anterior']}.")
        self.stdout.write("Siguiente paso: python manage.py migrate y reinicia el servicio.")
