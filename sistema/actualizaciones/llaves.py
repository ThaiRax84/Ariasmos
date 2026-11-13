import json
from pathlib import Path

from . import aviso

RUTA = Path(__file__).resolve().with_name("llaves.json")
LIMITE = 4096


def del_programa(ruta=None):
    ruta = Path(ruta) if ruta is not None else RUTA
    try:
        with ruta.open("rb") as archivo:
            crudos = archivo.read(LIMITE + 1)
    except OSError:
        return None
    if len(crudos) > LIMITE:
        return None
    try:
        datos = json.loads(crudos.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(datos, dict) or set(datos) != {"uso", "recuperacion"}:
        return None
    uso, recuperacion = datos["uso"], datos["recuperacion"]
    if not uso or not recuperacion or uso == recuperacion:
        return None
    try:
        aviso.llave_de_texto(uso)
        aviso.llave_de_texto(recuperacion)
    except aviso.AvisoInvalido:
        return None
    return {"uso": uso, "recuperacion": recuperacion}


def disponibles():
    return del_programa() is not None


def recuperacion():
    llaves = del_programa()
    return llaves["recuperacion"] if llaves else None


def de_uso():
    from .models import LlaveDeUso

    llaves = del_programa()
    if llaves is None:
        return None
    cambiada = LlaveDeUso.objects.filter(recuperacion=llaves["recuperacion"]).order_by("-contador").first()
    return cambiada.llave if cambiada is not None else llaves["uso"]
