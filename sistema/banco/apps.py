from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _cargar_tras_migrar(sender, **kwargs):
    from .catalogo import cargar

    cargar()


class BancoConfig(AppConfig):
    name = "banco"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        post_migrate.connect(_cargar_tras_migrar, sender=self, dispatch_uid="banco_cargar_catalogo")
