import json

from django.conf import settings

from .models import SOPORTES, TIPOS

MEDIOS_POR_DEFECTO = ["Transferencia SPEI", "Depósito en ventanilla", "Efectivo en caja"]


class ErrorCatalogo(ValueError):
    pass


def ruta():
    return settings.RAIZ / "datos" / "bancos.json"


def leer():
    with ruta().open(encoding="utf-8") as archivo:
        datos = json.load(archivo)
    bancos = datos.get("bancos")
    if not isinstance(bancos, list):
        raise ErrorCatalogo("el catalogo no tiene la lista de bancos")
    tipos = {t for t, _ in TIPOS}
    soportes = {s for s, _ in SOPORTES}
    vistas = set()
    for banco in bancos:
        clave = banco.get("clave", "")
        if not (isinstance(clave, str) and len(clave) == 3 and clave.isascii() and clave.isdigit()) or clave in vistas:
            raise ErrorCatalogo(f"clave de banco invalida: {clave!r}")
        if not isinstance(banco.get("nombre"), str) or not 0 < len(banco["nombre"]) <= 80:
            raise ErrorCatalogo(f"nombre invalido para {clave}")
        if banco.get("tipo") not in tipos or banco.get("soporte") not in soportes:
            raise ErrorCatalogo(f"tipo o soporte invalido para {clave}")
        vistas.add(clave)
    return bancos


def cargar(modelo=None):
    if modelo is None:
        from .models import Banco as modelo
    creados = actualizados = 0
    for banco in leer():
        existente = modelo.objects.filter(clave=banco["clave"]).first()
        valores = {"nombre": banco["nombre"], "tipo": banco["tipo"], "soporte": banco["soporte"], "capturado_a_mano": False}
        if existente is None:
            modelo.objects.create(clave=banco["clave"], **valores)
            creados += 1
        elif any(getattr(existente, campo) != valor for campo, valor in valores.items()):
            modelo.objects.filter(pk=existente.pk).update(**valores)
            actualizados += 1
    return creados, actualizados


def sembrar_medios(modelo=None):
    if modelo is None:
        from .models import MedioPago as modelo
    for orden, nombre in enumerate(MEDIOS_POR_DEFECTO, start=1):
        modelo.objects.get_or_create(nombre=nombre, defaults={"orden": orden * 10})
