from django.core.management.base import BaseCommand
from django.utils import timezone

from licencias import servicios
from licencias.models import Instalacion

ESTADOS = {
    "libre": "Este programa no usa licencia. Todo funciona con normalidad.",
    "por_activar": "La licencia todavía no está activada, pero el programa funciona con normalidad hasta que termine el plazo para activarla.",
    "vigente": "La licencia está vigente y todo funciona con normalidad.",
    "gracia": "La licencia ya venció, pero todavía estás en el plazo de gracia: todo funciona con normalidad. Pon al corriente el pago antes de que termine.",
}
MOTIVOS = {
    "revocada": "La licencia fue cancelada. El programa solo permite consultar, descargar y respaldar.",
    "vencida": "La licencia venció y el plazo de gracia terminó. El programa solo permite consultar, descargar y respaldar.",
    "llaves": "El archivo con las llaves de la licencia está dañado, por seguridad el programa solo permite consultar, descargar y respaldar. Pide ayuda a quien te dio el programa.",
    "sin_licencia": "No se activó la licencia a tiempo. El programa solo permite consultar, descargar y respaldar.",
}
RESULTADOS = {
    "renovada": "se renovó la licencia",
    "pago_pendiente": "Central dice que falta registrar el pago",
    "revocada": "Central avisó que la licencia fue cancelada",
    "rechazada": "Central no aceptó la solicitud",
    "sin_conexion": "no se pudo hablar con Central",
}


def _fecha(momento):
    return timezone.localtime(momento).strftime("%d/%m/%Y %H:%M")


class Command(BaseCommand):
    help = "Dice en palabras llanas cómo está la licencia de este programa"

    def handle(self, *args, **opciones):
        situacion = servicios.situacion()
        self.stdout.write(MOTIVOS.get(situacion.motivo) or ESTADOS[situacion.estado])
        if situacion.vence:
            self.stdout.write(f"Vence: {_fecha(situacion.vence)}")
        if situacion.limite:
            self.stdout.write(f"Fin del plazo de gracia: {_fecha(situacion.limite)}" if situacion.vence else f"Plazo para activar: hasta {_fecha(situacion.limite)}")
        fila = Instalacion.objects.filter(pk=1).first()
        if fila is not None and fila.ultimo_intento:
            self.stdout.write(f"Última vez que se intentó renovar: {_fecha(fila.ultimo_intento)}; {RESULTADOS.get(fila.ultimo_resultado, fila.ultimo_resultado)}.")
