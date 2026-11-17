from reportlab.lib.pagesizes import A4, letter

from .models import parametro

TAMANOS = {"carta": letter, "a4": A4}
OPCIONES = (("carta", "Carta"), ("a4", "A4"))


def tamano():
    return TAMANOS.get(str(parametro("tamano_hoja")).strip().lower(), letter)
