from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


MAXIMO_DIAS_ANTES = 60
MAXIMO_DIAS_ATRASO = 365


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


class Aviso(models.Model):
    PAGO = "pago"
    ANTES = "antes"
    ATRASO = "atraso"
    MOMENTOS = [
        (PAGO, "Al registrar un pago"),
        (ANTES, "Antes de que venza"),
        (ATRASO, "Cuando ya está atrasado"),
    ]
    MAXIMO_DE_AVISOS = 10
    MAXIMO_DIAS = {ANTES: MAXIMO_DIAS_ANTES, ATRASO: MAXIMO_DIAS_ATRASO}

    activo = models.BooleanField(default=False)
    momento = models.CharField(max_length=6, choices=MOMENTOS)
    dias = models.PositiveSmallIntegerField(default=0)
    plantilla = models.ForeignKey(
        PlantillaMensaje, on_delete=models.PROTECT, related_name="+"
    )
    agrupaciones = models.ManyToManyField(
        "titulares.Agrupacion", blank=True, related_name="+"
    )
    activado = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(momento="pago", dias=0)
                | Q(momento="antes", dias__gte=1, dias__lte=MAXIMO_DIAS_ANTES)
                | Q(momento="atraso", dias__gte=1, dias__lte=MAXIMO_DIAS_ATRASO),
                name="aviso_dias_del_momento",
            ),
            models.UniqueConstraint(
                fields=["momento"],
                condition=Q(momento="pago"),
                name="aviso_un_solo_pago",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.activo and self.activado is None:
            self.activado = timezone.now()
        super().save(*args, **kwargs)


class Envio(models.Model):
    PENDIENTE = "pendiente"
    ACEPTADO = "aceptado"
    ENVIADO = "enviado"
    ENTREGADO = "entregado"
    LEIDO = "leido"
    FALLIDO = "fallido"
    NO_ENVIADO = "no_enviado"
    INCIERTO = "incierto"
    ESTADOS = [
        (PENDIENTE, "Pendiente"),
        (ACEPTADO, "Enviado, esperando entrega"),
        (ENVIADO, "Enviado, esperando entrega"),
        (ENTREGADO, "Entregado"),
        (LEIDO, "Leído"),
        (FALLIDO, "No se pudo entregar"),
        (NO_ENVIADO, "No se mandó"),
        (INCIERTO, "No sabemos si salió"),
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
    aviso = models.ForeignKey(
        Aviso,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="envios",
    )
    cargo = models.ForeignKey(
        "cobros.Cargo",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    momento = models.CharField(max_length=6, blank=True)
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

    def save(self, *args, **kwargs):
        if self.aviso_id and not self.momento:
            self.momento = self.aviso.momento
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-creado", "-id"]
        indexes = [models.Index(fields=["estado"], name="envio_estado")]
        constraints = [
            models.UniqueConstraint(
                fields=["aviso", "cargo"],
                condition=Q(aviso__isnull=False, cargo__isnull=False),
                name="envio_un_aviso_por_cargo",
            )
        ]
