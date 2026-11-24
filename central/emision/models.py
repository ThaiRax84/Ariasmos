import uuid

from django.db import models

from . import reloj


def _ahora():
    return reloj.ahora()


class Negocio(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=120)
    contacto = models.CharField(max_length=200, blank=True)
    plan = models.CharField(max_length=40, default="base")
    modulos = models.JSONField(default=list)
    instalaciones_permitidas = models.PositiveIntegerField(default=1)
    pagado_hasta = models.DateField(null=True, blank=True)
    revocado = models.BooleanField(default=False)
    creado = models.DateTimeField(default=_ahora)


class Instalacion(models.Model):
    negocio = models.ForeignKey(Negocio, on_delete=models.PROTECT)
    huella = models.CharField(max_length=64, unique=True)
    llave_publica = models.CharField(max_length=44)
    activada = models.BooleanField(default=False)
    revocada = models.BooleanField(default=False)
    serie = models.PositiveIntegerField(default=0)
    ultima_renovacion = models.DateTimeField(null=True, blank=True)
    ultima_version = models.CharField(max_length=20, blank=True)


class CodigoActivacion(models.Model):
    negocio = models.ForeignKey(Negocio, on_delete=models.PROTECT)
    resumen = models.CharField(max_length=64, unique=True)
    vence = models.DateTimeField()
    usado = models.DateTimeField(null=True, blank=True)
    instalacion = models.ForeignKey(
        "Instalacion", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )


class Sello(models.Model):
    instalacion = models.ForeignKey(Instalacion, on_delete=models.CASCADE)
    valor = models.CharField(max_length=32)
    momento = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["instalacion", "valor"], name="sello_unico_por_instalacion"
            )
        ]


class Rechazo(models.Model):
    origen = models.CharField(max_length=64, db_index=True)
    momento = models.DateTimeField(db_index=True)


class Bitacora(models.Model):
    momento = models.DateTimeField()
    accion = models.CharField(max_length=40)
    negocio = models.ForeignKey(
        Negocio, null=True, blank=True, on_delete=models.SET_NULL
    )
    origen = models.CharField(max_length=64, blank=True)
    datos = models.JSONField(default=dict)


class Ajuste(models.Model):
    clave = models.CharField(max_length=40, unique=True)
    valor = models.IntegerField()
