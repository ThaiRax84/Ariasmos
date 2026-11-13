from django.conf import settings
from django.db import models
from django.db.models import F, Q

from nucleo.dinero import formatear


class SinBorrado(models.QuerySet):
    def delete(self):
        raise models.ProtectedError("los registros de caja no se borran", set())


class Caja(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    serie_recibos = models.CharField(max_length=10, default="A")
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        constraints = [models.CheckConstraint(condition=Q(serie_recibos__regex=r"^[A-Z0-9]{1,10}$"), name="caja_serie_valida")]

    def __str__(self):
        return self.nombre


class Denominacion(models.Model):
    valor = models.PositiveIntegerField(unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["-valor"]
        constraints = [models.CheckConstraint(condition=Q(valor__gt=0), name="denominacion_positiva")]

    def __str__(self):
        return formatear(self.valor)


class Turno(models.Model):
    ABIERTO = "abierto"
    CERRADO = "cerrado"
    ESTADOS = [(ABIERTO, "Abierto"), (CERRADO, "Cerrado")]

    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name="turnos")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="turnos")
    fondo_inicial = models.PositiveBigIntegerField(default=0)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=ABIERTO)
    abierto_en = models.DateTimeField(auto_now_add=True)
    cerrado_en = models.DateTimeField(null=True, blank=True)

    objects = SinBorrado.as_manager()

    class Meta:
        ordering = ["-abierto_en"]
        constraints = [
            models.UniqueConstraint(fields=["usuario"], condition=Q(estado="abierto"), name="turno_uno_abierto_por_persona"),
            models.UniqueConstraint(fields=["caja"], condition=Q(estado="abierto"), name="turno_uno_abierto_por_caja"),
            models.CheckConstraint(condition=Q(estado="abierto", cerrado_en__isnull=True) | Q(estado="cerrado", cerrado_en__isnull=False), name="turno_cierre_coherente"),
        ]

    def __str__(self):
        return f"Turno {self.pk} · {self.caja} · {self.usuario}"

    @property
    def abierto(self):
        return self.estado == self.ABIERTO


class Arqueo(models.Model):
    turno = models.OneToOneField(Turno, on_delete=models.PROTECT, related_name="arqueo")
    conteo = models.JSONField(default=dict)
    contado = models.PositiveBigIntegerField()
    esperado = models.PositiveBigIntegerField()
    diferencia = models.BigIntegerField()
    nota = models.CharField(max_length=500, blank=True)
    supera_umbral = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    objects = SinBorrado.as_manager()

    class Meta:
        ordering = ["-creado"]
        constraints = [models.CheckConstraint(condition=Q(diferencia=F("contado") - F("esperado")), name="arqueo_diferencia_coherente")]


class Traslado(models.Model):
    ENTREGA = "entrega"
    DEPOSITO = "deposito"
    TIPOS = [(ENTREGA, "Entrega"), (DEPOSITO, "Depósito bancario")]
    PENDIENTE = "pendiente"
    CONFIRMADO = "confirmado"
    RECHAZADO = "rechazado"
    POR_CONCILIAR = "por_conciliar"
    CONCILIADO = "conciliado"
    ESTADOS = [(PENDIENTE, "Pendiente de confirmar"), (CONFIRMADO, "Confirmado"), (RECHAZADO, "Rechazado"), (POR_CONCILIAR, "Por conciliar"), (CONCILIADO, "Conciliado con el banco")]

    tipo = models.CharField(max_length=10, choices=TIPOS)
    origen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="traslados_enviados")
    destino = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="traslados_recibidos")
    importe = models.PositiveBigIntegerField()
    estado = models.CharField(max_length=15, choices=ESTADOS)
    nota = models.CharField(max_length=300, blank=True)
    cuenta_bancaria = models.ForeignKey("banco.CuentaBancaria", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    referencia = models.CharField(max_length=60, blank=True)
    fecha_deposito = models.DateField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    resuelto_en = models.DateTimeField(null=True, blank=True)

    objects = SinBorrado.as_manager()

    class Meta:
        ordering = ["-creado"]
        constraints = [
            models.CheckConstraint(condition=Q(importe__gt=0), name="traslado_importe_positivo"),
            models.CheckConstraint(condition=~Q(origen=F("destino")), name="traslado_a_otra_persona"),
            models.CheckConstraint(
                condition=(Q(tipo="entrega") & Q(destino__isnull=False) & Q(estado__in=["pendiente", "confirmado", "rechazado"]))
                | (Q(tipo="deposito") & Q(destino__isnull=True) & Q(cuenta_bancaria__isnull=False) & Q(fecha_deposito__isnull=False) & Q(estado__in=["por_conciliar", "conciliado"])),
                name="traslado_coherente",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {formatear(self.importe)}"
