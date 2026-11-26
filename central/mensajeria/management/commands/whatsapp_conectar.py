import os
import re
from getpass import getpass

from django.core.management.base import BaseCommand, CommandError

from emision.management.commands._negocio import negocio_de
from emision.servicios import anotar
from mensajeria import secretos, servicios
from mensajeria.models import Remitente

VARIABLE_DEL_TOKEN = "TWILIO_TOKEN"
MENSAJE_OPCION = "Opción no reconocida. El token se pasa por la variable TWILIO_TOKEN o se escribe cuando se pide."
PATRON_SID = re.compile(r"[A-Za-z0-9]{4,64}")


def _sid(valor, prefijo, nombre):
    if not valor.startswith(prefijo) or PATRON_SID.fullmatch(valor) is None:
        raise CommandError(f"{nombre} no es válido: debe empezar con {prefijo}.")
    return valor


def _token():
    token = os.environ.get(VARIABLE_DEL_TOKEN) or getpass("Token de Twilio: ")
    if not token.strip():
        raise CommandError("Falta el token de Twilio.")
    return token.strip()


class Command(BaseCommand):
    help = "Conecta el número de WhatsApp de un negocio. El token se lee de la variable TWILIO_TOKEN o se pide por teclado"

    def create_parser(self, *args, **kwargs):
        parser = super().create_parser(*args, **kwargs)
        error = parser.error

        def sin_eco(mensaje):
            if mensaje.startswith("unrecognized arguments"):
                raise CommandError(MENSAJE_OPCION)
            error(mensaje)

        parser.error = sin_eco
        return parser

    def add_arguments(self, parser):
        parser.add_argument("negocio", help="Identificador del negocio")
        parser.add_argument(
            "--numero", required=True, help="Número con +, por ejemplo +5255…"
        )
        parser.add_argument(
            "--cuenta", required=True, help="Identificador de la cuenta de Twilio (AC…)"
        )
        parser.add_argument(
            "--servicio",
            required=True,
            help="Identificador del servicio de mensajes de Twilio (MG…)",
        )

    def handle(self, *args, **opciones):
        negocio = negocio_de(opciones["negocio"])
        numero = opciones["numero"]
        if servicios.PATRON_DESTINO.fullmatch(numero) is None:
            raise CommandError(
                "El número debe empezar con + y tener de 10 a 15 dígitos."
            )
        cuenta = _sid(opciones["cuenta"], "AC", "La cuenta")
        servicio = _sid(opciones["servicio"], "MG", "El servicio")
        Remitente.objects.update_or_create(
            negocio=negocio,
            defaults={
                "numero": numero,
                "cuenta_sid": cuenta,
                "servicio_sid": servicio,
                "token_cifrado": secretos.cifrar_token(_token()),
                "activo": True,
            },
        )
        anotar("whatsapp_conectado", negocio, numero_final=numero[-4:])
        self.stdout.write(
            f"WhatsApp conectado para {negocio.nombre}, número terminado en {numero[-4:]}."
        )
