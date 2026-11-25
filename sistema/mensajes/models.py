from django.conf import settings
from django.db import models


class PlantillaMensaje(models.Model):
    BORRADOR = "borrador"
    EN_REVISION = "en_revision"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
    ESTADOS = [
        (BORRADOR, "Borrador"),
        (EN_REVISION, "Meta lo está revisando"),
        (APROBADA, "Listo para usar"),
        (RECHAZADA, "Meta lo rechazó"),
    ]

    clave = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=80)
    texto = models.CharField(max_length=900)
    con_documento = models.BooleanField(default=False)
    estado = models.CharField(max_length=12, choices=ESTADOS, default=BORRADOR)
    motivo = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.nombre


class Envio(models.Model):
    PENDIENTE = "pendiente"
    ACEPTADO = "aceptado"
    ENVIADO = "enviado"
    ENTREGADO = "entregado"
    LEIDO = "leido"
    FALLIDO = "fallido"
    NO_ENVIADO = "no_enviado"
    ESTADOS = [
        (PENDIENTE, "Pendiente"),
        (ACEPTADO, "Enviado, esperando entrega"),
        (ENVIADO, "Enviado, esperando entrega"),
        (ENTREGADO, "Entregado"),
        (LEIDO, "Leído"),
        (FALLIDO, "No se pudo entregar"),
        (NO_ENVIADO, "No se mandó"),
    ]
    EN_CURSO = (ACEPTADO, ENVIADO)
    AVANCES = (ENVIADO, ENTREGADO, LEIDO, FALLIDO)
    SIN_ENTREGAR = (FALLIDO, NO_ENVIADO)

    clave_envio = models.CharField(max_length=64, unique=True)
    plantilla = models.ForeignKey(
        PlantillaMensaje, on_delete=models.PROTECT, related_name="+"
    )
    contacto = models.ForeignKey(
        "titulares.Contacto", on_delete=models.PROTECT, related_name="+"
    )
    titular = models.ForeignKey(
        "titulares.Titular", on_delete=models.PROTECT, related_name="+"
    )
    recibo = models.ForeignKey(
        "cobros.Recibo",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="envios",
    )
    destino_final = models.CharField(max_length=4)
    id_central = models.UUIDField(null=True, blank=True)
    estado = models.CharField(max_length=12, choices=ESTADOS, default=PENDIENTE)
    motivo = models.CharField(max_length=300, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        ordering = ["-creado", "-id"]
        indexes = [models.Index(fields=["estado"], name="envio_estado")]
