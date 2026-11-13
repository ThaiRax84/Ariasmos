import os
import secrets
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from proyecto import equipo


class Command(BaseCommand):
    help = "Escribe el Caddyfile del servicio TLS para el nombre del equipo"

    def add_arguments(self, parser):
        parser.add_argument("--nombre", required=True, help="Nombre del equipo; se sanea a letras, dígitos y guion")
        parser.add_argument("--salida", required=True)
        parser.add_argument("--sin-redireccion", action="store_true", help="No atender el puerto 80 (si otro programa lo usa)")

    def handle(self, *args, **opciones):
        salida = Path(opciones["salida"])
        if not salida.is_absolute():
            raise CommandError("La salida debe ser una ruta absoluta.")
        contenido = equipo.caddyfile(opciones["nombre"], redirigir_http=not opciones["sin_redireccion"])
        salida.parent.mkdir(parents=True, exist_ok=True)
        temporal = salida.with_name(f".{salida.name}.{secrets.token_hex(4)}.tmp")
        temporal.write_text(contenido, encoding="utf-8")
        os.replace(temporal, salida)
        self.stdout.write(f"Caddyfile escrito en {salida} para {equipo.sanear(opciones['nombre']) or 'localhost'}.")
