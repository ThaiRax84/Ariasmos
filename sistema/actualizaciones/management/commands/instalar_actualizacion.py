from django.core.management.base import BaseCommand, CommandError

from actualizaciones import servicios


class Command(BaseCommand):
    help = "Vuelve a comprobar la firma y la huella de la actualización descargada y, si coinciden, ejecuta su instalador"

    def add_arguments(self, parser):
        parser.add_argument("--si", action="store_true", help="No pide confirmación")

    def handle(self, *args, **opciones):
        try:
            preparada = servicios.preparar_instalacion()
        except servicios.ErrorActualizacion as error:
            raise CommandError(str(error))
        self.stdout.write(f"Firma y huella correctas: Ariasmos {preparada['version']} (SHA-256 {preparada['sha256']}).")
        if preparada["turnos_abiertos"]:
            self.stdout.write(f"AVISO: hay {preparada['turnos_abiertos']} turno(s) de caja abierto(s). Conviene cerrarlos antes de instalar.")
        self.stdout.write("Antes de seguir, haz un respaldo desde la pantalla Respaldos. El instalador detiene los servicios unos minutos, hace otro respaldo y los vuelve a arrancar.")
        if not opciones["si"]:
            respuesta = input("Escribe SI para ejecutar el instalador: ").strip().upper()
            if respuesta != "SI":
                servicios.descartar_preparada(preparada)
                raise CommandError("No se instaló nada.")
        try:
            servicios.instalar(preparada)
        except (servicios.ErrorActualizacion, OSError) as error:
            servicios.descartar_preparada(preparada)
            raise CommandError(f"No se pudo ejecutar el instalador: {error}")
        self.stdout.write("Instalador abierto. Sigue sus pasos en pantalla.")
