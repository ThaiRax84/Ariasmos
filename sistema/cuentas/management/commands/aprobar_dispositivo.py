from django.core.management.base import BaseCommand, CommandError

from cuentas.models import Dispositivo
from cuentas.servicios import aprobar_dispositivo


class Command(BaseCommand):
    help = "Aprueba desde la consola del servidor un equipo pendiente por su código"

    def add_arguments(self, parser):
        parser.add_argument("codigo")
        parser.add_argument("--nombre", default="Aprobado desde el servidor")

    def handle(self, *args, **opciones):
        codigo = opciones["codigo"].strip().upper()
        candidatos = list(Dispositivo.objects.filter(codigo=codigo, estado=Dispositivo.PENDIENTE))
        if len(candidatos) != 1:
            raise CommandError("No hay exactamente un equipo pendiente con ese código.")
        aprobar_dispositivo(candidatos[0], None, opciones["nombre"])
        self.stdout.write(self.style.SUCCESS(f"Equipo {codigo} aprobado."))
