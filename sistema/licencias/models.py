from django.db import models
from django.db.models import Q
from django.utils import timezone


class Instalacion(models.Model):
    llave_cifrada = models.TextField()
    huella = models.CharField(max_length=64)
    activada = models.BooleanField(default=False)
    primer_arranque = models.DateTimeField()
    mayor_momento = models.DateTimeField()
    ultimo_reloj = models.DateTimeField(default=timezone.now)
    documento = models.TextField(blank=True)
    revocacion = models.TextField(blank=True)
    ultimo_intento = models.DateTimeField(null=True, blank=True)
    ultimo_resultado = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(id=1), name="licencias_instalacion_unica"
            )
        ]
