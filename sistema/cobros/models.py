from django.db import models
from django.db.models import Q

from nucleo.dinero import formatear


class ReglaRecargo(models.Model):
    FIJO = "fijo"
    PORCENTAJE = "porcentaje"
    TIPOS = [(FIJO, "Importe fijo"), (PORCENTAJE, "Porcentaje")]

    nombre = models.CharField(max_length=100, unique=True)
    tipo = models.CharField(max_length=10, choices=TIPOS, default=FIJO)
    valor = models.PositiveIntegerField(default=0)
    dias_gracia = models.PositiveSmallIntegerField(default=0)
    se_repite = models.BooleanField(default=False)
    tope_centavos = models.PositiveIntegerField(null=True, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    @property
    def valor_texto(self):
        if self.tipo == self.PORCENTAJE:
            enteros, resto = divmod(self.valor, 100)
            return f"{enteros}.{resto:02d} %"
        return formatear(self.valor)


class ConceptoCobro(models.Model):
    UNICO = "unico"
    RECURRENTE = "recurrente"
    POR_EVENTO = "por_evento"
    TIPOS = [(UNICO, "Único"), (RECURRENTE, "Recurrente"), (POR_EVENTO, "Por evento")]

    PERIODICIDADES = [
        ("semanal", "Semanal"),
        ("quincenal", "Quincenal"),
        ("mensual", "Mensual"),
        ("bimestral", "Bimestral"),
        ("trimestral", "Trimestral"),
        ("semestral", "Semestral"),
        ("anual", "Anual"),
    ]

    NUEVOS = "nuevos"
    TODOS = "todos"
    AGRUPACION = "agrupacion"
    MANUAL = "manual"
    APLICA = [(NUEVOS, "Titulares nuevos"), (TODOS, "Todos los activos"), (AGRUPACION, "Una agrupación"), (MANUAL, "Manual")]

    nombre = models.CharField(max_length=100, unique=True)
    tipo = models.CharField(max_length=12, choices=TIPOS)
    importe_centavos = models.PositiveIntegerField(default=0)
    periodicidad = models.CharField(max_length=12, choices=PERIODICIDADES, blank=True)
    dia_vencimiento = models.PositiveSmallIntegerField(null=True, blank=True)
    regla_recargo = models.ForeignKey(ReglaRecargo, null=True, blank=True, on_delete=models.PROTECT, related_name="conceptos")
    aplica_a = models.CharField(max_length=12, choices=APLICA, default=MANUAL)
    agrupacion = models.ForeignKey("titulares.Agrupacion", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    prioridad = models.PositiveSmallIntegerField(default=100)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["prioridad", "nombre"]
        constraints = [
            models.CheckConstraint(condition=Q(dia_vencimiento__isnull=True) | Q(dia_vencimiento__gte=1, dia_vencimiento__lte=28), name="concepto_dia_valido"),
            models.CheckConstraint(condition=~Q(tipo="recurrente") | ~Q(periodicidad=""), name="concepto_recurrente_con_periodo"),
            models.CheckConstraint(condition=~Q(aplica_a="agrupacion") | Q(agrupacion__isnull=False), name="concepto_agrupacion_definida"),
        ]

    def __str__(self):
        return self.nombre

    @property
    def importe_texto(self):
        return formatear(self.importe_centavos)


class PlanCobro(models.Model):
    titular = models.ForeignKey("titulares.Titular", on_delete=models.PROTECT, related_name="planes")
    concepto = models.ForeignKey(ConceptoCobro, on_delete=models.PROTECT, related_name="planes")
    importe_centavos = models.PositiveIntegerField(null=True, blank=True)
    descuento_centesimas = models.PositiveIntegerField(null=True, blank=True)
    vigente_desde = models.DateField()
    vigente_hasta = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    nota = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-vigente_desde"]
        constraints = [
            models.CheckConstraint(condition=Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=models.F("vigente_desde")), name="plan_vigencia_valida"),
            models.CheckConstraint(condition=Q(descuento_centesimas__isnull=True) | Q(descuento_centesimas__lte=10000), name="plan_descuento_valido"),
        ]

    def __str__(self):
        return f"{self.concepto} · {self.titular}"

    @property
    def importe_texto(self):
        if self.importe_centavos is None:
            return ""
        return formatear(self.importe_centavos)

    @property
    def descuento_texto(self):
        if self.descuento_centesimas is None:
            return ""
        enteros, resto = divmod(self.descuento_centesimas, 100)
        return f"{enteros}.{resto:02d} %"
