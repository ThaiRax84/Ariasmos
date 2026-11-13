import re

from django.conf import settings

PATRON = re.compile(r"^\d+\.\d+\.\d+$")


def actual():
    try:
        texto = (settings.RAIZ / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "desconocida"
    return texto if PATRON.match(texto) else "desconocida"
