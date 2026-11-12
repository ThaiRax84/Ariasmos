from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.management.base import BaseCommand
from django.core.wsgi import get_wsgi_application
from waitress import serve


class Command(BaseCommand):
    help = "Arranca el servidor de producción (waitress)"

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--puerto", type=int, default=8000)
        parser.add_argument("--hilos", type=int, default=8)

    def handle(self, *args, **opciones):
        self.stdout.write(f"Sirviendo en http://{opciones['host']}:{opciones['puerto']}/")
        serve(
            StaticFilesHandler(get_wsgi_application()),
            host=opciones["host"],
            port=opciones["puerto"],
            threads=opciones["hilos"],
            ident="servidor",
            clear_untrusted_proxy_headers=False,
        )
