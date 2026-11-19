from django.db import models

TEMAS = ("cobros", "transferencias", "titulares", "solicitudes", "caja", "banco", "inventario")


class Contador(models.Model):
    tema = models.CharField(max_length=20, unique=True)
    valor = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["tema"]

    def __str__(self):
        return self.tema
