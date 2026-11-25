from django.core.management.base import BaseCommand, CommandError

from emision.management.commands._negocio import negocio_de
from emision.servicios import anotar
from mensajeria.models import Remitente


class Command(BaseCommand):
    help = "Desconecta el WhatsApp de un negocio y borra su token"

    def add_arguments(self, parser):
        parser.add_argument("negocio", help="Identificador del negocio")

    def handle(self, *args, **opciones):
        negocio = negocio_de(opciones["negocio"])
        if not Remitente.objects.filter(negocio=negocio, activo=True).update(
            activo=False, token_cifrado=""
        ):
            raise CommandError("Ese negocio no tiene WhatsApp conectado.")
        anotar("whatsapp_desconectado", negocio)
        self.stdout.write(f"WhatsApp desconectado para {negocio.nombre}.")
