from importlib import import_module

from django.conf import settings


class FalloProveedor(Exception):
    def __init__(self, motivo):
        super().__init__(motivo)
        self.motivo = motivo


def activo():
    return import_module(f"{__name__}.{settings.PROVEEDOR_MENSAJES}")
