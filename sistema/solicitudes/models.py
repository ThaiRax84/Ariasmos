from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from cuentas.permisos import OPCIONES

ACCIONES = [("alta", "Alta"), ("baja", "Baja"), ("reactivacion", "Reactivación")]


class PoliticaAccion(models.Model):
    accion = models.CharField(max_length=30, unique=True, choices=ACCIONES)
    permiso_directo = models.CharField(max_length=40, choices=OPCIONES)
    permiso_solicitar = models.CharField(max_length=40, choices=OPCIONES)
    permiso_aprobar = models.CharField(max_length=40, choices=OPCIONES)
    horas_caducidad = models.PositiveIntegerField(default=72)
    horas_resaltar = models.PositiveIntegerField(default=24)
    permite_delegacion = models.BooleanField(default=True)
    permite_codigo = models.BooleanField(default=True)

    class Meta:
        ordering = ["accion"]

    def __str__(self):
        return self.get_accion_display()


class Solicitud(models.Model):
    PENDIENTE = "pendiente"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
    CADUCADA = "caducada"
    ESTADOS = [(PENDIENTE, "Pendiente"), (APROBADA, "Aprobada"), (RECHAZADA, "Rechazada"), (CADUCADA, "Caducada")]

    BANDEJA = "bandeja"
    CODIGO = "codigo"
    DELEGACION = "delegacion"
    VIAS = [(BANDEJA, "Bandeja"), (CODIGO, "Código por teléfono"), (DELEGACION, "Delegación temporal")]

    accion = models.CharField(max_length=30, choices=ACCIONES)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    titular = models.ForeignKey("titulares.Titular", on_delete=models.PROTECT, related_name="solicitudes")
    datos = models.JSONField(default=dict, blank=True)
    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="solicitudes")
    creada = models.DateTimeField(auto_now_add=True)
    caduca_en = models.DateTimeField()
    resuelta_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    resuelta_en = models.DateTimeField(null=True, blank=True)
    via = models.CharField(max_length=12, choices=VIAS, blank=True)
    nota_resolucion = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-creada"]

    def __str__(self):
        return f"{self.get_accion_display()} · {self.titular}"

    def politica(self):
        return PoliticaAccion.objects.get(accion=self.accion)

    @property
    def vencida(self):
        return self.estado == self.PENDIENTE and self.caduca_en <= timezone.now()

    def resaltada(self, politica=None):
        politica = politica or self.politica()
        return self.estado == self.PENDIENTE and timezone.now() - self.creada >= timedelta(hours=politica.horas_resaltar)


class IntentoCodigo(models.Model):
    FALLIDO = "fallido"
    BLOQUEO = "bloqueo"
    TIPOS = [(FALLIDO, "Código erróneo"), (BLOQUEO, "Vía de código bloqueada")]

    tipo = models.CharField(max_length=10, choices=TIPOS)
    capturista = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    autorizador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="intentos_de_codigo")
    solicitud = models.ForeignKey(Solicitud, null=True, blank=True, on_delete=models.PROTECT, related_name="intentos_de_codigo")
    motivo = models.CharField(max_length=20, blank=True)
    momento = models.DateTimeField(auto_now_add=True, db_index=True)
    visto = models.BooleanField(default=False)

    class Meta:
        ordering = ["-momento"]
