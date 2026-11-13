from django.core.management.base import BaseCommand

from cuentas import secretos


class Command(BaseCommand):
    help = "Cifra los secretos del autenticador que todavía estén en claro y confirma que no queda ninguno"

    def handle(self, *args, **opciones):
        cambiados = secretos.cifrar_pendientes()
        restantes = secretos.en_claro()
        self.stdout.write(f"Secretos cifrados ahora: {cambiados}. En claro: {restantes}.")
