import secrets
import uuid

from django.db import models

from emision import reloj
from emision.models import Negocio

TOPE_POR_OMISION = 500


def _ahora():
    return reloj.ahora()


def _token():
    return secrets.token_urlsafe(32)


class Remitente(models.Model):
    negocio = models.OneToOneField(Negocio, on_delete=models.CASCADE)
    numero = models.CharField(max_length=20)
    cuenta_sid = models.CharField(max_length=64)
    servicio_sid = models.CharField(max_length=64)
    token_cifrado = models.TextField()
    activo = models.BooleanField(default=True)


class Plantilla(models.Model):
    EN_REVISION = "en_revision"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
    ESTADOS = [
        (EN_REVISION, "En revisión"),
        (APROBADA, "Aprobada"),
        (RECHAZADA, "Rechazada"),
    ]

    negocio = models.ForeignKey(Negocio, on_delete=models.CASCADE)
    clave = models.CharField(max_length=40)
    nombre = models.CharField(max_length=80)
    texto = models.CharField(max_length=900)
    con_documento = models.BooleanField(default=False)
    variables = models.JSONField(default=list)
    estado = models.CharField(max_length=12, choices=ESTADOS, default=EN_REVISION)
    motivo = models.CharField(max_length=300, blank=True)
    id_proveedor = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["negocio", "clave"], name="plantilla_unica_por_negocio"
            )
        ]


class Mensaje(models.Model):
    ACEPTADO = "aceptado"
    ENVIADO = "enviado"
    ENTREGADO = "entregado"
    LEIDO = "leido"
    FALLIDO = "fallido"
    ESTADOS = [
        (ACEPTADO, "Aceptado"),
        (ENVIADO, "Enviado"),
        (ENTREGADO, "Entregado"),
        (LEIDO, "Leído"),
        (FALLIDO, "Fallido"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    negocio = models.ForeignKey(Negocio, on_delete=models.CASCADE)
    plantilla = models.ForeignKey(Plantilla, on_delete=models.CASCADE)
    clave_envio = models.CharField(max_length=64)
    destino_final = models.CharField(max_length=4)
    destino_resumen = models.CharField(max_length=64)
    id_proveedor = models.CharField(max_length=64, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=ACEPTADO)
    error = models.CharField(max_length=200, blank=True)
    creado = models.DateTimeField(default=_ahora)
    actualizado = models.DateTimeField(default=_ahora)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["negocio", "clave_envio"], name="mensaje_clave_unica"
            )
        ]
        indexes = [
            models.Index(fields=["negocio", "creado"], name="mensaje_negocio_creado"),
            models.Index(fields=["negocio", "destino_resumen"], name="mensaje_destino"),
        ]


class Documento(models.Model):
    mensaje = models.OneToOneField(Mensaje, on_delete=models.CASCADE)
    token = models.CharField(max_length=43, unique=True, default=_token)
    contenido = models.BinaryField()
    vence = models.DateTimeField(db_index=True)


class Baja(models.Model):
    negocio = models.ForeignKey(Negocio, on_delete=models.CASCADE)
    resumen = models.CharField(max_length=64)
    momento = models.DateTimeField(default=_ahora)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["negocio", "resumen"], name="baja_unica_por_negocio"
            )
        ]


class Cuota(models.Model):
    negocio = models.OneToOneField(Negocio, on_delete=models.CASCADE)
    tope_maximo = models.PositiveIntegerField(default=TOPE_POR_OMISION)
    tope = models.PositiveIntegerField(default=TOPE_POR_OMISION)
