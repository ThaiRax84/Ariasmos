from django.core.management.base import BaseCommand, CommandError

from auditoria.servicios import MOTIVOS, verificar_cadena


class Command(BaseCommand):
    help = "Verifica la cadena de hashes de la auditoria"

    def handle(self, *args, **opciones):
        resultado = verificar_cadena(guardar=True)
        if not resultado.valida:
            raise CommandError(f"Bitacora no integra: {MOTIVOS[resultado.motivo]} (evento {resultado.numero}; verificados antes: {resultado.total})")
        self.stdout.write(self.style.SUCCESS(f"Bitacora integra: {resultado.total} eventos verificados"))
