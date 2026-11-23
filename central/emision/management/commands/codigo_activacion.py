from django.core.management.base import BaseCommand

from emision import ajustes, servicios

from ._negocio import negocio_de


class Command(BaseCommand):
    help = "Saca un código de activación nuevo para un negocio"

    def add_arguments(self, parser):
        parser.add_argument("negocio", help="Identificador del negocio")

    def handle(self, *args, **opciones):
        negocio = negocio_de(opciones["negocio"])
        codigo = servicios.crear_codigo(negocio)
        self.stdout.write(f"Código de activación para {negocio.nombre}: {codigo}")
        self.stdout.write(
            f"Sirve una sola vez y vence en {ajustes.valor('dias_codigo')} días. Anótalo ahora: no se vuelve a mostrar."
        )
