from django.db import models


class EnvioUsado(models.Model):
    ficha = models.CharField(max_length=64, unique=True)
    ruta = models.CharField(max_length=300)
    destino = models.CharField(max_length=500, blank=True, default="")
    creado = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "envío usado"
        verbose_name_plural = "envíos usados"
