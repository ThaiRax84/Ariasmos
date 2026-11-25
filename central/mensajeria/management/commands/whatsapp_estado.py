from django.core.management.base import BaseCommand

from emision.models import Negocio
from mensajeria import servicios
from mensajeria.models import Remitente


class Command(BaseCommand):
    help = "Muestra por negocio si tiene WhatsApp conectado, los mensajes del mes y su tope"

    def handle(self, *args, **opciones):
        conectados = set(
            Remitente.objects.filter(activo=True).values_list("negocio_id", flat=True)
        )
        lista = Negocio.objects.order_by("nombre")
        if not lista:
            self.stdout.write("Todavía no hay negocios dados de alta.")
        for negocio in lista:
            cuota = servicios.cuota_de(negocio)
            self.stdout.write(
                f"{negocio.nombre} | id {negocio.pk} | WhatsApp {'conectado' if negocio.pk in conectados else 'sin conectar'} | "
                f"enviados este mes {servicios.enviados_del_mes(negocio)} | tope {cuota.tope} de {cuota.tope_maximo}"
            )
