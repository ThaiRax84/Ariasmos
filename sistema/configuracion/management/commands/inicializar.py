import hashlib
import secrets

from django.core.management.base import BaseCommand

from proyecto import instancia


class Command(BaseCommand):
    help = "Crea la carpeta instancia/ con claves aleatorias y un token para el asistente"

    def add_arguments(self, parser):
        parser.add_argument("--sin-https", action="store_true", help="Cookies sin marca Secure (solo para pruebas locales sin TLS)")
        parser.add_argument("--nuevo-token", action="store_true", help="Genera otro token para el asistente si se perdió")

    def handle(self, *args, **opciones):
        datos = instancia.leer()
        token = secrets.token_urlsafe(18)
        if datos is None:
            datos = instancia.nueva(https=not opciones["sin_https"])
            datos["token_asistente_hash"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
            ruta = instancia.escribir(datos)
            self.stdout.write(self.style.SUCCESS(f"Instancia creada en {ruta.parent}"))
        elif opciones["nuevo_token"]:
            datos["token_asistente_hash"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
            instancia.reemplazar(datos)
            self.stdout.write(self.style.SUCCESS("Token del asistente renovado."))
        else:
            self.stdout.write(f"La instancia ya existe en {instancia.carpeta()}; no se cambió nada.")
            return
        self.stdout.write(f"Token del asistente: {token}")
        self.stdout.write("Guárdalo: se pide en el primer paso del asistente y no se vuelve a mostrar.")
        self.stdout.write("Siguiente paso: python manage.py migrate")
