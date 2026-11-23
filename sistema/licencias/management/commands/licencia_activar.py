from django.core.management.base import BaseCommand

from licencias import servicios

MENSAJES = {
    "activada": "Listo: la licencia quedó activada y el programa ya puede usarse con normalidad.",
    "pago_pendiente": "El código es correcto y este equipo quedó registrado, pero el pago de la licencia aún no está al corriente. Cuando se registre el pago, el programa activará la licencia solo.",
    "rechazada": "Central no aceptó el código. Revisa que esté bien escrito y que no haya vencido ni se haya usado antes; si sigue fallando, pide uno nuevo.",
    "sin_conexion": "No se pudo hablar con Central. Revisa la conexión a internet de este equipo y vuelve a intentarlo.",
    "apagada": "Este programa no usa licencia, así que no hay nada que activar.",
}


class Command(BaseCommand):
    help = "Activa la licencia de este programa con el código que te dio quien te lo entregó"

    def add_arguments(self, parser):
        parser.add_argument("codigo", help="Código de activación, por ejemplo XXXXX-XXXXX-XXXXX-XXXXX")

    def handle(self, *args, **opciones):
        self.stdout.write(MENSAJES[servicios.activar(opciones["codigo"])])
