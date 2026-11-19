from django.db.models import F

from .models import TEMAS, Contador

MODELOS = {
    "cobros.Pago": "cobros",
    "cobros.ReversionPago": "cobros",
    "cobros.Cargo": "cobros",
    "titulares.Titular": "titulares",
    "solicitudes.Solicitud": "solicitudes",
    "caja.Turno": "caja",
    "caja.RetiroCaja": "caja",
    "caja.Traslado": "caja",
    "caja.Arqueo": "caja",
    "banco.MovimientoBancario": "banco",
    "banco.Importacion": "banco",
    "inventario.Venta": "inventario",
    "inventario.MovimientoInventario": "inventario",
    "inventario.Conteo": "inventario",
}


def subir(*temas):
    for tema in temas:
        if tema not in TEMAS:
            raise ValueError(tema)
        if not Contador.objects.filter(tema=tema).update(valor=F("valor") + 1):
            Contador.objects.get_or_create(tema=tema)
            Contador.objects.filter(tema=tema).update(valor=F("valor") + 1)


def valores():
    actuales = dict(Contador.objects.values_list("tema", "valor"))
    return {tema: actuales.get(tema, 0) for tema in TEMAS}


def _receptor(tema):
    def recibir(sender, **kwargs):
        if kwargs.get("raw"):
            return
        subir(tema)

    return recibir


def conectar():
    from django.apps import apps
    from django.db.models.signals import post_delete, post_save

    for nombre, tema in MODELOS.items():
        modelo = apps.get_model(nombre)
        receptor = _receptor(tema)
        post_save.connect(receptor, sender=modelo, weak=False, dispatch_uid=f"vivo-{nombre}-guardar")
        post_delete.connect(receptor, sender=modelo, weak=False, dispatch_uid=f"vivo-{nombre}-borrar")
