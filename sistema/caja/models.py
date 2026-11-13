from django.conf import settings
from django.db import models
from django.db.models import F, Q

from configuracion.moneda import formatear


class SinBorrado(models.QuerySet):
    def delete(self):
        raise models.ProtectedError("los registros de caja no se borran", set())


class RegistroInmutable(Exception):
    pass


class ConsultaInmutable(SinBorrado):
    def update(self, **kwargs):
        raise RegistroInmutable("este registro de caja no se modifica")


class Inmutable(models.Model):
    objects = ConsultaInmutable.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RegistroInmutable("este registro de caja no se modifica")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RegistroInmutable("este registro de caja no se borra")


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
    rechazos_retiro = models.PositiveSmallIntegerField(default=0)
    propuestas_cambio = models.PositiveIntegerField(default=0)

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


class ConteoArqueo(Inmutable):
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT, related_name="conteos")
    numero = models.PositiveSmallIntegerField()
    conteo = models.JSONField(default=dict)
    contado = models.PositiveBigIntegerField()
    nota = models.CharField(max_length=500, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["turno", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["turno", "numero"], name="conteo_unico_por_numero"),
            models.CheckConstraint(condition=Q(numero__in=[1, 2]), name="conteo_primero_o_reconteo"),
        ]


class Arqueo(models.Model):
    turno = models.OneToOneField(Turno, on_delete=models.PROTECT, related_name="arqueo")
    conteo = models.JSONField(default=dict)
    contado = models.PositiveBigIntegerField()
    esperado = models.PositiveBigIntegerField()
    diferencia = models.BigIntegerField()
    nota = models.CharField(max_length=500, blank=True)
    supera_umbral = models.BooleanField(default=False)
    primer_conteo = models.JSONField(default=dict)
    primer_contado = models.PositiveBigIntegerField(null=True, blank=True)
    con_reconteo = models.BooleanField(default=False)
    esperado_piezas = models.JSONField(default=dict)
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


class MotivoRetiro(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class ConsultaRetiros(SinBorrado):
    def update(self, **kwargs):
        if set(kwargs) - RetiroCaja.MUTABLES:
            raise RegistroInmutable("los datos de un retiro no se modifican")
        return super().update(**kwargs)


class RetiroCaja(models.Model):
    POR_REVISAR = "por_revisar"
    REVISADO = "revisado"
    OBSERVADO = "observado"
    REVISIONES = [(POR_REVISAR, "Por revisar"), (REVISADO, "Revisado"), (OBSERVADO, "Observado")]
    PENDIENTE = "pendiente"
    ADJUNTO = "adjunto"
    SIN_COMPROBANTE = "sin_comprobante"
    COMPROBANTES = [(PENDIENTE, "Comprobante pendiente"), (ADJUNTO, "Con comprobante"), (SIN_COMPROBANTE, "Sin comprobante")]
    MUTABLES = {"revision", "revisado_por", "revisado_en", "nota_revision", "comprobante", "motivo_sin_comprobante"}

    serie = models.CharField(max_length=10)
    folio = models.PositiveBigIntegerField()
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT, related_name="retiros")
    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name="retiros")
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="retiros")
    importe = models.PositiveBigIntegerField()
    motivo = models.ForeignKey(MotivoRetiro, on_delete=models.PROTECT, related_name="retiros")
    nota = models.CharField(max_length=300, blank=True)
    solicitud = models.ForeignKey("solicitudes.Solicitud", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    autorizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    creado = models.DateTimeField(auto_now_add=True)
    revision = models.CharField(max_length=12, choices=REVISIONES, default=POR_REVISAR)
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    revisado_en = models.DateTimeField(null=True, blank=True)
    nota_revision = models.CharField(max_length=300, blank=True)
    comprobante = models.CharField(max_length=16, choices=COMPROBANTES, default=PENDIENTE)
    motivo_sin_comprobante = models.CharField(max_length=300, blank=True)

    objects = ConsultaRetiros.as_manager()

    class Meta:
        ordering = ["-creado", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["serie", "folio"], name="retiro_folio_unico"),
            models.CheckConstraint(condition=Q(importe__gt=0), name="retiro_importe_positivo"),
            models.CheckConstraint(condition=Q(folio__gte=1), name="retiro_folio_positivo"),
            models.CheckConstraint(condition=~Q(revisado_por=F("registrado_por")), name="retiro_revision_ajena"),
            models.CheckConstraint(
                condition=(Q(revision="por_revisar") & Q(revisado_por__isnull=True)) | (Q(revision__in=["revisado", "observado"]) & Q(revisado_por__isnull=False)),
                name="retiro_revision_coherente",
            ),
        ]

    def __str__(self):
        return f"{self.serie}-{self.folio}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RegistroInmutable("los datos de un retiro no se modifican")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RegistroInmutable("los retiros no se borran")

    @property
    def revertido(self):
        return hasattr(self, "reversion")


class ComprobanteRetiro(Inmutable):
    JPEG = "jpeg"
    PNG = "png"
    PDF = "pdf"
    TIPOS = [(JPEG, "Imagen JPEG"), (PNG, "Imagen PNG"), (PDF, "PDF")]

    retiro = models.OneToOneField(RetiroCaja, on_delete=models.PROTECT, related_name="archivo_comprobante")
    archivo = models.CharField(max_length=64, unique=True)
    tipo = models.CharField(max_length=4, choices=TIPOS)
    tamano = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    subido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(archivo__regex=r"^[0-9a-f]{32}\.(jpg|png|pdf)$"), name="comprobante_nombre_aleatorio")]


class ReversionRetiro(Inmutable):
    retiro = models.OneToOneField(RetiroCaja, on_delete=models.PROTECT, related_name="reversion")
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT, related_name="retiros_devueltos")
    motivo = models.CharField(max_length=300)
    ejecutada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    autorizada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    solicitud = models.ForeignKey("solicitudes.Solicitud", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    creada = models.DateTimeField(auto_now_add=True)


class MovimientoPiezas(Inmutable):
    APERTURA = "apertura"
    RECIBIDO = "recibido"
    CAMBIO = "cambio"
    RETIRO = "retiro"
    REVERSION_RETIRO = "reversion_retiro"
    DEVOLUCION = "devolucion"
    TRASLADO = "traslado"
    ORIGENES = [
        (APERTURA, "Fondo de apertura"),
        (RECIBIDO, "Recibido en un cobro"),
        (CAMBIO, "Cambio entregado"),
        (RETIRO, "Retiro de caja"),
        (REVERSION_RETIRO, "Reversión de retiro"),
        (DEVOLUCION, "Devolución de un pago"),
        (TRASLADO, "Entrega o depósito"),
    ]

    turno = models.ForeignKey(Turno, null=True, blank=True, on_delete=models.PROTECT, related_name="piezas")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    origen = models.CharField(max_length=20, choices=ORIGENES)
    denominacion = models.PositiveIntegerField()
    piezas = models.BigIntegerField()
    pago = models.ForeignKey("cobros.Pago", null=True, blank=True, on_delete=models.PROTECT, related_name="piezas")
    retiro = models.ForeignKey(RetiroCaja, null=True, blank=True, on_delete=models.PROTECT, related_name="piezas")
    traslado = models.ForeignKey(Traslado, null=True, blank=True, on_delete=models.PROTECT, related_name="piezas")
    reversion = models.ForeignKey("cobros.ReversionPago", null=True, blank=True, on_delete=models.PROTECT, related_name="piezas")
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=~Q(piezas=0), name="piezas_distinto_de_cero"),
            models.CheckConstraint(condition=Q(denominacion__gt=0), name="piezas_denominacion_positiva"),
        ]
