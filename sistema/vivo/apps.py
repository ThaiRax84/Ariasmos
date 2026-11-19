from django.apps import AppConfig


class VivoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "vivo"
    verbose_name = "Pantallas en vivo"

    def ready(self):
        from . import pulso

        pulso.conectar()
