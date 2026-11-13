from django.db import models
from django.db.models import Q


class Respaldo(models.Model):
    RESPALDO = "respaldo"
    PRUEBA = "prueba"
    TIPOS = [(RESPALDO, "Respaldo"), (PRUEBA, "Prueba de restauración")]
    EN_CURSO = "en_curso"
    CORRECTO = "correcto"
    FALLO = "fallo"
    RESULTADOS = [(EN_CURSO, "En curso"), (CORRECTO, "Correcto"), (FALLO, "Falló")]

    tipo = models.CharField(max_length=10, choices=TIPOS)
    creado = models.DateTimeField(auto_now_add=True)
    terminado = models.DateTimeField(null=True, blank=True)
    archivo = models.CharField(max_length=120, blank=True)
    tamano = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    resultado = models.CharField(max_length=10, choices=RESULTADOS, default=EN_CURSO)
    mensaje = models.CharField(max_length=300, blank=True)
    conteos = models.JSONField(default=dict, blank=True)
    automatico = models.BooleanField(default=False)
    dia = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-creado", "-id"]
        constraints = [models.UniqueConstraint(fields=["tipo", "dia"], condition=Q(automatico=True), name="respaldo_automatico_unico")]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.creado:%d/%m/%Y %H:%M}"
