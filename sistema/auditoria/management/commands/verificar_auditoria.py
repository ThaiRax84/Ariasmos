from django.core.management.base import BaseCommand, CommandError

from auditoria.servicios import verificar_cadena


class Command(BaseCommand):
    help = "Verifica la cadena de hashes de la auditoria"

    def handle(self, *args, **opciones):
        valida, evento_id, total = verificar_cadena()
        if not valida:
            raise CommandError(f"Cadena alterada en el evento {evento_id} (eventos verificados antes: {total})")
        self.stdout.write(self.style.SUCCESS(f"Cadena integra: {total} eventos verificados"))
