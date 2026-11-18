from django.db import models
from django.db.models import Q

from configuracion.moneda import formatear

CANTIDAD_TOPE = 10000


class OpcionConcepto(models.Model):
    concepto = models.OneToOneField("cobros.ConceptoCobro", on_delete=models.CASCADE, related_name="opciones_tarifa")
    por_cantidad = models.BooleanField(default=False)
    cantidad_maxima = models.PositiveIntegerField(default=1)
    solo_con_tarifa = models.BooleanField(default=False)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(cantidad_maxima__gte=1, cantidad_maxima__lte=CANTIDAD_TOPE), name="opcion_cantidad_maxima_valida"),
        ]

    def __str__(self):
        return f"Opciones de {self.concepto}"


class TarifaAgrupacion(models.Model):
    concepto = models.ForeignKey("cobros.ConceptoCobro", on_delete=models.PROTECT, related_name="tarifas")
    agrupacion = models.ForeignKey("titulares.Agrupacion", on_delete=models.PROTECT, related_name="tarifas")
    importe_centavos = models.PositiveBigIntegerField()
    periodicidad = models.CharField(max_length=12, blank=True)
    dia_vencimiento = models.PositiveSmallIntegerField(null=True, blank=True)
    activa = models.BooleanField(default=True)
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["concepto__prioridad", "concepto__nombre", "agrupacion__nombre"]
        constraints = [
            models.UniqueConstraint(fields=["concepto", "agrupacion"], name="tarifa_una_por_agrupacion"),
            models.CheckConstraint(condition=Q(importe_centavos__gt=0), name="tarifa_importe_positivo"),
            models.CheckConstraint(condition=Q(dia_vencimiento__isnull=True) | Q(dia_vencimiento__gte=1, dia_vencimiento__lte=28), name="tarifa_dia_valido"),
        ]

    def __str__(self):
        return f"{self.concepto} · {self.agrupacion}"

    @property
    def importe_texto(self):
        return formatear(self.importe_centavos)


class OrigenCargo(models.Model):
    cargo = models.OneToOneField("cobros.Cargo", on_delete=models.PROTECT, related_name="origen_tarifa")
    tarifa = models.ForeignKey(TarifaAgrupacion, null=True, blank=True, on_delete=models.PROTECT, related_name="cargos")
    periodicidad = models.CharField(max_length=12)
    inicio = models.DateField()
    fin = models.DateField()

    class Meta:
        ordering = ["inicio", "id"]
        constraints = [models.CheckConstraint(condition=Q(fin__gte=models.F("inicio")), name="origen_periodo_valido")]
