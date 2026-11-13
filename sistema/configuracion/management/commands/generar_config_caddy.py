import json
import os
import secrets
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from proyecto import equipo


class Command(BaseCommand):
    help = "Escribe la configuración (JSON) del servicio TLS con el certificado único del servidor"

    def add_arguments(self, parser):
        parser.add_argument("--nombre", required=True, help="Nombre del equipo; se sanea a letras, dígitos y guion")
        parser.add_argument("--cert", required=True, help="Ruta absoluta del certificado del servidor")
        parser.add_argument("--clave", required=True, help="Ruta absoluta de la clave privada del servidor")
        parser.add_argument("--salida", required=True, help="Ruta absoluta del archivo de configuración")
        parser.add_argument("--sin-redireccion", action="store_true", help="No atender el puerto 80 (si otro programa lo usa)")

    def handle(self, *args, **opciones):
        salida, cert, clave = Path(opciones["salida"]), Path(opciones["cert"]), Path(opciones["clave"])
        if not all(p.is_absolute() for p in (salida, cert, clave)):
            raise CommandError("Las rutas deben ser absolutas.")
        try:
            datos = equipo.configuracion_caddy(opciones["nombre"], cert, clave, redirigir_http=not opciones["sin_redireccion"])
        except ValueError as error:
            raise CommandError(str(error))
        salida.parent.mkdir(parents=True, exist_ok=True)
        temporal = salida.with_name(f".{salida.name}.{secrets.token_hex(4)}.tmp")
        temporal.write_text(json.dumps(datos, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
        os.replace(temporal, salida)
        self.stdout.write(f"Configuración del servicio TLS escrita en {salida} para {equipo.sanear(opciones['nombre']) or 'localhost'}.")
