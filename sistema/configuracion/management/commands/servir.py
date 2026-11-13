from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.wsgi import get_wsgi_application
from waitress import serve


LOCALES = {"127.0.0.1", "localhost", "::1"}


class Command(BaseCommand):
    help = "Arranca el servidor de producción (waitress)"

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--puerto", type=int, default=8000)
        parser.add_argument("--hilos", type=int, default=8)
        parser.add_argument("--permitir-red", action="store_true", help="Escuchar fuera de este equipo aunque la instancia use https (normalmente lo atiende el servicio TLS)")

    def handle(self, *args, **opciones):
        if opciones["host"] not in LOCALES and getattr(settings, "HTTPS_ACTIVO", False) and not opciones["permitir_red"]:
            raise CommandError("Con https activo la aplicación solo escucha en 127.0.0.1: la red la atiende el servicio TLS. Usa --permitir-red si de verdad lo necesitas.")
        self.stdout.write(f"Sirviendo en http://{opciones['host']}:{opciones['puerto']}/")
        serve(
            StaticFilesHandler(get_wsgi_application()),
            host=opciones["host"],
            port=opciones["puerto"],
            threads=opciones["hilos"],
            ident="servidor",
            clear_untrusted_proxy_headers=False,
        )
