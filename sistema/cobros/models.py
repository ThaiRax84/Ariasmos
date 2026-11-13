from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

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
    vigente_desde = models.DateField()
    vigente_hasta = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    nota = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-vigente_desde"]
        constraints = [
            models.CheckConstraint(condition=Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=models.F("vigente_desde")), name="plan_vigencia_valida"),
        ]

    def __str__(self):
        return f"{self.concepto} · {self.titular}"

    @property
    def importe_texto(self):
        if self.importe_centavos is None:
            return ""
        return formatear(self.importe_centavos)


class AsientoInmutable(Exception):
    pass


class ConsultaInmutable(models.QuerySet):
    def update(self, **kwargs):
        raise AsientoInmutable("los asientos del libro no se modifican")

    def delete(self):
        raise AsientoInmutable("los asientos del libro no se borran")


class Asiento(models.Model):
    objects = ConsultaInmutable.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AsientoInmutable("los asientos del libro no se modifican")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AsientoInmutable("los asientos del libro no se borran")


class Beca(Asiento):
    titular = models.ForeignKey("titulares.Titular", on_delete=models.PROTECT, related_name="becas")
    concepto = models.ForeignKey(ConceptoCobro, on_delete=models.PROTECT, related_name="becas")
    puntos_base = models.PositiveIntegerField()
    vigente_desde = models.DateField()
    vigente_hasta = models.DateField(null=True, blank=True)
    motivo = models.CharField(max_length=300)
    creada = models.DateTimeField(auto_now_add=True)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    autorizada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    solicitud = models.ForeignKey("solicitudes.Solicitud", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-vigente_desde", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(puntos_base__gte=1, puntos_base__lte=10000), name="beca_porcentaje_valido"),
            models.CheckConstraint(condition=Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=F("vigente_desde")), name="beca_vigencia_valida"),
        ]

    @property
    def porcentaje_texto(self):
        enteros, resto = divmod(self.puntos_base, 100)
        return f"{enteros}.{resto:02d} %" if resto else f"{enteros} %"


class Cargo(Asiento):
    AUTOMATICO = "automatico"
    MANUAL = "manual"
    RECARGO = "recargo"
    SALDO_INICIAL = "saldo_inicial"
    ORIGENES = [(AUTOMATICO, "Automático"), (MANUAL, "Manual"), (RECARGO, "Recargo"), (SALDO_INICIAL, "Saldo inicial")]

    titular = models.ForeignKey("titulares.Titular", on_delete=models.PROTECT, related_name="cargos")
    concepto = models.ForeignKey(ConceptoCobro, on_delete=models.PROTECT, related_name="cargos")
    periodo = models.CharField(max_length=7, blank=True)
    descripcion = models.CharField(max_length=200, blank=True)
    cantidad = models.PositiveIntegerField(default=1)
    importe_original = models.PositiveBigIntegerField()
    descuento = models.PositiveBigIntegerField(default=0)
    beca = models.ForeignKey(Beca, null=True, blank=True, on_delete=models.PROTECT, related_name="cargos")
    importe_final = models.PositiveBigIntegerField()
    vencimiento = models.DateField()
    origen = models.CharField(max_length=15, choices=ORIGENES)
    cargo_base = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="recargos")
    fecha_recargo = models.DateField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["vencimiento", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(importe_final=F("importe_original") - F("descuento")), name="cargo_importe_final"),
            models.CheckConstraint(condition=Q(descuento__lte=F("importe_original")), name="cargo_descuento_menor"),
            models.CheckConstraint(condition=Q(cantidad__gte=1), name="cargo_cantidad_positiva"),
            models.CheckConstraint(
                condition=(Q(origen="recargo") & Q(cargo_base__isnull=False) & Q(fecha_recargo__isnull=False)) | (~Q(origen="recargo") & Q(cargo_base__isnull=True) & Q(fecha_recargo__isnull=True)),
                name="cargo_recargo_ligado",
            ),
            models.UniqueConstraint(fields=["cargo_base", "fecha_recargo"], condition=Q(origen="recargo"), name="cargo_recargo_unico"),
            models.UniqueConstraint(fields=["titular", "concepto", "periodo"], condition=Q(origen="automatico"), name="cargo_automatico_unico"),
        ]

    def __str__(self):
        etiqueta = self.descripcion or str(self.concepto)
        return f"{etiqueta} {self.periodo}".strip()


class SerieRecibo(models.Model):
    nombre = models.CharField(max_length=10, unique=True)
    siguiente = models.PositiveBigIntegerField(default=1)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(siguiente__gte=1), name="serie_siguiente_positivo")]

    def __str__(self):
        return self.nombre


class Pago(Asiento):
    EFECTIVO = "efectivo"
    BANCO = "banco"
    SALDO_INICIAL = "saldo_inicial"
    MEDIOS = [(EFECTIVO, "Efectivo"), (BANCO, "Banco"), (SALDO_INICIAL, "Saldo inicial")]

    titular = models.ForeignKey("titulares.Titular", on_delete=models.PROTECT, related_name="pagos")
    importe = models.PositiveBigIntegerField()
    medio = models.CharField(max_length=15, choices=MEDIOS)
    fecha = models.DateTimeField(default=timezone.now)
    turno = models.ForeignKey("caja.Turno", null=True, blank=True, on_delete=models.PROTECT, related_name="pagos")
    movimiento = models.ForeignKey("banco.MovimientoBancario", null=True, blank=True, on_delete=models.PROTECT, related_name="pagos")
    ficha = models.CharField(max_length=64, null=True, blank=True, unique=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    solicitud = models.ForeignKey("solicitudes.Solicitud", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["fecha", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(importe__gt=0), name="pago_importe_positivo"),
            models.CheckConstraint(condition=~Q(medio="efectivo") | Q(turno__isnull=False), name="pago_efectivo_con_turno"),
        ]

    def __str__(self):
        return f"Pago {self.pk} · {formatear(self.importe)}"


class Aplicacion(Asiento):
    pago = models.ForeignKey(Pago, on_delete=models.PROTECT, related_name="aplicaciones")
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name="aplicaciones")
    importe = models.PositiveBigIntegerField()
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=Q(importe__gt=0), name="aplicacion_importe_positivo")]


class Recibo(Asiento):
    pago = models.OneToOneField(Pago, on_delete=models.PROTECT, related_name="recibo")
    serie = models.CharField(max_length=10)
    folio = models.PositiveBigIntegerField()
    codigo = models.CharField(max_length=11)
    emitido = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["serie", "folio"]
        constraints = [
            models.UniqueConstraint(fields=["serie", "folio"], name="recibo_folio_unico"),
            models.CheckConstraint(condition=Q(folio__gte=1), name="recibo_folio_positivo"),
        ]

    def __str__(self):
        return f"{self.serie}-{self.folio}"


class Prorroga(Asiento):
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name="prorrogas")
    fecha_limite = models.DateField()
    motivo = models.CharField(max_length=300)
    creada = models.DateTimeField(auto_now_add=True)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    autorizada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    solicitud = models.ForeignKey("solicitudes.Solicitud", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-fecha_limite", "-id"]


class CancelacionCargo(Asiento):
    CANCELACION = "cancelacion"
    CONDONACION = "condonacion"
    TIPOS = [(CANCELACION, "Cancelación"), (CONDONACION, "Condonación de recargo")]

    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name="cancelaciones")
    tipo = models.CharField(max_length=12, choices=TIPOS)
    importe = models.PositiveBigIntegerField()
    motivo = models.CharField(max_length=300)
    creada = models.DateTimeField(auto_now_add=True)
    ejecutada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    autorizada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    solicitud = models.ForeignKey("solicitudes.Solicitud", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=Q(importe__gt=0), name="cancelacion_importe_positivo")]


class ReversionPago(Asiento):
    pago = models.OneToOneField(Pago, on_delete=models.PROTECT, related_name="reversion")
    motivo = models.CharField(max_length=300)
    turno = models.ForeignKey("caja.Turno", null=True, blank=True, on_delete=models.PROTECT, related_name="devoluciones")
    creada = models.DateTimeField(auto_now_add=True)
    ejecutada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    autorizada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    solicitud = models.ForeignKey("solicitudes.Solicitud", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["id"]
