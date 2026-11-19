import os
import shutil
from urllib.parse import urlparse

import pytest
from django.conf import settings

from .conftest import cliente

CHROME = os.environ.get("ARIASMOS_CHROME", "/usr/bin/google-chrome")
CAPTURAS = os.environ.get("ARIASMOS_CAPTURAS", "")


def chrome_disponible():
    return os.path.exists(CHROME) or shutil.which("google-chrome") is not None


class Sesion:
    def __init__(self, playwright, servidor):
        self.servidor = servidor
        self.navegador = playwright.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        self.errores = []
        self.paginas = []

    def pagina(self, usuario, ancho=1400, alto=900, movimiento=None):
        c = cliente(usuario)
        host = urlparse(self.servidor).hostname
        opciones = {"viewport": {"width": ancho, "height": alto}, "locale": "es-MX"}
        if movimiento:
            opciones["reduced_motion"] = movimiento
        contexto = self.navegador.new_context(**opciones)
        galletas = [{"name": nombre, "value": valor.value, "domain": host, "path": "/"} for nombre, valor in c.cookies.items() if nombre in (settings.SESSION_COOKIE_NAME, settings.COOKIE_DISPOSITIVO)]
        contexto.add_cookies(galletas)
        pagina = contexto.new_page()
        pagina.on("console", lambda m: self.errores.append(f"consola {m.type}: {m.text}") if m.type in ("error", "warning") else None)
        pagina.on("pageerror", lambda e: self.errores.append(f"error: {e}"))
        pagina.on("response", lambda r: self.errores.append(f"respuesta {r.status}: {r.url}") if r.status >= 400 else None)
        self.paginas.append(pagina)
        return pagina

    def ir(self, pagina, ruta):
        pagina.goto(self.servidor + ruta)
        pagina.wait_for_load_state("networkidle")

    def captura(self, pagina, nombre):
        if CAPTURAS:
            os.makedirs(CAPTURAS, exist_ok=True)
            pagina.screenshot(path=os.path.join(CAPTURAS, nombre + ".png"), full_page=True)

    def cerrar(self):
        self.navegador.close()


@pytest.fixture
def sesion_navegador(live_server):
    sync = pytest.importorskip("playwright.sync_api")
    if not chrome_disponible():
        pytest.skip("No hay navegador")
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    with sync.sync_playwright() as p:
        sesion = Sesion(p, live_server.url)
        try:
            yield sesion
        finally:
            sesion.cerrar()
