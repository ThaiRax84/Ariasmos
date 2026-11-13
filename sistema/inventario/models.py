from django.conf import settings
from django.db import models
from django.db.models import F, Q

MAXIMO_CANTIDAD = 10000
MAXIMO_CONTEO = 1000000
PATRON_CLAVE = r"^[A-Z0-9][A-Z0-9._-]{0,29}$"


class RegistroInmutable(Exception):
    pass


class SinBorrado(models.QuerySet):
    def delete(self):
        raise models.ProtectedError("los registros de inventario no se borran", set())


class ConsultaInmutable(SinBorrado):
    def update(self, **kwargs):
        raise RegistroInmutable("este registro de inventario no se modifica")


class ConsultaParcial(SinBorrado):
    def update(self, **kwargs):
        if set(kwargs) - self.model.MUTABLES:
            raise RegistroInmutable("estos datos de inventario no se modifican")
        return super().update(**kwargs)


class Inmutable(models.Model):
    objects = ConsultaInmutable.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RegistroInmutable("este registro de inventario no se modifica")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RegistroInmutable("este registro de inventario no se borra")


class Parcial(models.Model):
    MUTABLES = frozenset()
    objects = ConsultaParcial.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            campos = set(kwargs.get("update_fields") or ())
            if not campos or campos - self.MUTABLES:
                raise RegistroInmutable("estos datos de inventario no se modifican")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RegistroInmutable("este registro de inventario no se borra")


POR_REVISAR = "por_revisar"
REVISADO = "revisado"
OBSERVADO = "observado"
NO_APLICA = "no_aplica"
REVISIONES = [(POR_REVISAR, "Por revisar"), (REVISADO, "Revisado"), (OBSERVADO, "Observado"), (NO_APLICA, "No requiere revisión")]


def revision_coherente(nombre, autor):
    return models.CheckConstraint(
        condition=(Q(revision__in=[POR_REVISAR, NO_APLICA]) & Q(revisado_por__isnull=True)) | (Q(revision__in=[REVISADO, OBSERVADO]) & Q(revisado_por__isnull=False) & ~Q(revisado_por=F(autor))),
        name=nombre,
    )


class Articulo(models.Model):
    clave = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=150)
    precio = models.PositiveBigIntegerField()
    minimo = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    concepto = models.ForeignKey("cobros.ConceptoCobro", on_delete=models.PROTECT, related_name="articulos")
    creado = models.DateTimeField(auto_now_add=True)

    objects = SinBorrado.as_manager()

    class Meta:
        ordering = ["nombre", "clave"]
        constraints = [
            models.CheckConstraint(condition=Q(clave__regex=PATRON_CLAVE), name="articulo_clave_valida"),
            models.CheckConstraint(condition=Q(precio__gt=0), name="articulo_precio_positivo"),
            models.CheckConstraint(condition=Q(minimo__lte=MAXIMO_CONTEO), name="articulo_minimo_razonable"),
        ]

    def __str__(self):
        return f"{self.clave} · {self.nombre}"

    def delete(self, *args, **kwargs):
        raise RegistroInmutable("los artículos no se borran; se desactivan")


class Venta(Parcial):
    AHORA = "ahora"
    ADEUDO = "adeudo"
    MODOS = [(AHORA, "Lo paga ahora"), (ADEUDO, "Se va a su adeudo")]
    MUTABLES = frozenset({"pago"})

    titular = models.ForeignKey("titulares.Titular", on_delete=models.PROTECT, related_name="ventas")
    modo = models.CharField(max_length=8, choices=MODOS)
    total = models.PositiveBigIntegerField()
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creada = models.DateTimeField(auto_now_add=True)
    pago = models.OneToOneField("cobros.Pago", null=True, blank=True, on_delete=models.PROTECT, related_name="venta")

    class Meta:
        ordering = ["-creada", "-id"]
        constraints = [models.CheckConstraint(condition=Q(total__gt=0), name="venta_total_positivo")]

    def __str__(self):
        return f"V-{self.pk}"


class RenglonVenta(Parcial):
    MUTABLES = frozenset({"revisado_por", "revisado_en"})

    venta = models.ForeignKey(Venta, on_delete=models.PROTECT, related_name="renglones")
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT, related_name="vendidos")
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.PositiveBigIntegerField()
    cargo = models.OneToOneField("cobros.Cargo", on_delete=models.PROTECT, related_name="renglon_venta")
    existencia_antes = models.BigIntegerField()
    sin_existencia = models.BooleanField(default=False)
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    revisado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(cantidad__gte=1, cantidad__lte=MAXIMO_CANTIDAD), name="renglon_venta_cantidad"),
            models.CheckConstraint(condition=Q(precio_unitario__gt=0), name="renglon_venta_precio"),
            models.UniqueConstraint(fields=["venta", "articulo"], name="renglon_venta_articulo_unico"),
        ]

    @property
    def importe(self):
        return self.cantidad * self.precio_unitario


class Devolucion(Parcial):
    SALDO = "saldo"
    EFECTIVO = "efectivo"
    SIN_DINERO = "sin_dinero"
    REVERSION = "reversion"
    MEDIOS = [(SALDO, "Saldo a favor"), (EFECTIVO, "Efectivo"), (SIN_DINERO, "Se canceló lo pendiente"), (REVERSION, "Reversión del pago")]
    MUTABLES = frozenset({"revision", "revisado_por", "revisado_en", "nota_revision"})

    venta = models.ForeignKey(Venta, on_delete=models.PROTECT, related_name="devoluciones")
    medio = models.CharField(max_length=10, choices=MEDIOS)
    motivo = models.CharField(max_length=300)
    importe_cancelado = models.PositiveBigIntegerField(default=0)
    importe_dinero = models.PositiveBigIntegerField(default=0)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    autorizada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    solicitud = models.ForeignKey("solicitudes.Solicitud", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    turno = models.ForeignKey("caja.Turno", null=True, blank=True, on_delete=models.PROTECT, related_name="devoluciones_articulos")
    pago_credito = models.OneToOneField("cobros.Pago", null=True, blank=True, on_delete=models.PROTECT, related_name="devolucion_articulos")
    creada = models.DateTimeField(auto_now_add=True)
    revision = models.CharField(max_length=12, choices=REVISIONES, default=POR_REVISAR)
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    revisado_en = models.DateTimeField(null=True, blank=True)
    nota_revision = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-creada", "-id"]
        constraints = [
            models.CheckConstraint(condition=~Q(medio="efectivo") | (Q(turno__isnull=False) & Q(importe_dinero__gt=0) & Q(solicitud__isnull=False)), name="devolucion_efectivo_con_turno_y_solicitud"),
            models.CheckConstraint(condition=~Q(medio="saldo") | (Q(pago_credito__isnull=False) & Q(importe_dinero__gt=0)), name="devolucion_saldo_con_pago"),
            models.CheckConstraint(condition=~Q(medio="sin_dinero") | Q(importe_dinero=0), name="devolucion_sin_dinero"),
            revision_coherente("devolucion_revision_ajena", "usuario"),
        ]

    def __str__(self):
        return f"DV-{self.pk}"


class RenglonDevolucion(Inmutable):
    devolucion = models.ForeignKey(Devolucion, on_delete=models.PROTECT, related_name="renglones")
    renglon = models.ForeignKey(RenglonVenta, on_delete=models.PROTECT, related_name="devueltos")
    cantidad = models.PositiveIntegerField()
    buen_estado = models.BooleanField(default=True)
    importe_dinero = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=Q(cantidad__gte=1, cantidad__lte=MAXIMO_CANTIDAD), name="renglon_devolucion_cantidad")]


class RegistroInventario(Parcial):
    ENTRADA = "entrada"
    MERMA = "merma"
    TIPOS = [(ENTRADA, "Entrada"), (MERMA, "Merma")]
    SIN = "sin"
    ADJUNTO = "adjunto"
    COMPROBANTES = [(SIN, "Sin comprobante"), (ADJUNTO, "Con comprobante")]
    MUTABLES = frozenset({"revision", "revisado_por", "revisado_en", "nota_revision", "comprobante"})

    tipo = models.CharField(max_length=8, choices=TIPOS)
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT, related_name="registros")
    cantidad = models.PositiveIntegerField()
    motivo = models.CharField(max_length=150)
    nota = models.CharField(max_length=300, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado = models.DateTimeField(auto_now_add=True)
    comprobante = models.CharField(max_length=8, choices=COMPROBANTES, default=SIN)
    revision = models.CharField(max_length=12, choices=REVISIONES, default=POR_REVISAR)
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    revisado_en = models.DateTimeField(null=True, blank=True)
    nota_revision = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-creado", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(cantidad__gte=1, cantidad__lte=MAXIMO_CANTIDAD), name="registro_inventario_cantidad"),
            revision_coherente("registro_inventario_revision_ajena", "usuario"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.pk}"


class ComprobanteInventario(Inmutable):
    registro = models.OneToOneField(RegistroInventario, on_delete=models.PROTECT, related_name="archivo_comprobante")
    archivo = models.CharField(max_length=64, unique=True)
    tipo = models.CharField(max_length=4)
    tamano = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    subido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(archivo__regex=r"^[0-9a-f]{32}\.(jpg|png|pdf)$"), name="comprobante_inventario_nombre_aleatorio")]


class Conteo(Parcial):
    ARCHIVO = "archivo"
    PANTALLA = "pantalla"
    ORIGENES = [(ARCHIVO, "Archivo subido"), (PANTALLA, "Capturado en pantalla")]
    MUTABLES = frozenset({"solicitud", "aplicado_en", "aplicado_por"})

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado = models.DateTimeField(auto_now_add=True)
    origen = models.CharField(max_length=8, choices=ORIGENES)
    nombre_archivo = models.CharField(max_length=120, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    inicial = models.BooleanField(default=False)
    solicitud = models.OneToOneField("solicitudes.Solicitud", null=True, blank=True, on_delete=models.PROTECT, related_name="conteo")
    aplicado_en = models.DateTimeField(null=True, blank=True)
    aplicado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-creado", "-id"]
        constraints = [models.CheckConstraint(condition=Q(aplicado_por__isnull=True) | ~Q(aplicado_por=F("usuario")), name="conteo_aprobado_por_otra_persona")]

    def __str__(self):
        return f"Conteo {self.pk}"


class RenglonConteo(Inmutable):
    conteo = models.ForeignKey(Conteo, on_delete=models.PROTECT, related_name="renglones")
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT, related_name="conteos")
    contado = models.BigIntegerField()
    esperado = models.BigIntegerField()
    diferencia = models.BigIntegerField()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["conteo", "articulo"], name="renglon_conteo_articulo_unico"),
            models.CheckConstraint(condition=Q(contado__gte=0, contado__lte=MAXIMO_CONTEO), name="renglon_conteo_contado"),
            models.CheckConstraint(condition=Q(diferencia=F("contado") - F("esperado")), name="renglon_conteo_diferencia"),
        ]


class MovimientoInventario(Inmutable):
    CARGA_INICIAL = "carga_inicial"
    ENTRADA = "entrada"
    VENTA = "venta"
    DEVOLUCION = "devolucion"
    MERMA = "merma"
    AJUSTE = "ajuste_conteo"
    TIPOS = [(CARGA_INICIAL, "Carga inicial"), (ENTRADA, "Entrada"), (VENTA, "Venta"), (DEVOLUCION, "Devolución"), (MERMA, "Merma"), (AJUSTE, "Ajuste por conteo")]

    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=14, choices=TIPOS)
    cantidad = models.BigIntegerField()
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado = models.DateTimeField(auto_now_add=True)
    nota = models.CharField(max_length=300, blank=True)
    venta = models.ForeignKey(Venta, null=True, blank=True, on_delete=models.PROTECT, related_name="movimientos")
    devolucion = models.ForeignKey(Devolucion, null=True, blank=True, on_delete=models.PROTECT, related_name="movimientos")
    registro = models.ForeignKey(RegistroInventario, null=True, blank=True, on_delete=models.PROTECT, related_name="movimientos")
    conteo = models.ForeignKey(Conteo, null=True, blank=True, on_delete=models.PROTECT, related_name="movimientos")

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=~Q(cantidad=0), name="movimiento_inventario_distinto_de_cero"),
            models.CheckConstraint(
                condition=(Q(tipo="venta") & Q(venta__isnull=False) & Q(cantidad__lt=0))
                | (Q(tipo="devolucion") & Q(devolucion__isnull=False) & Q(cantidad__gt=0))
                | (Q(tipo="merma") & (Q(registro__isnull=False) | Q(devolucion__isnull=False)) & Q(cantidad__lt=0))
                | (Q(tipo="entrada") & Q(registro__isnull=False) & Q(cantidad__gt=0))
                | (Q(tipo__in=["ajuste_conteo", "carga_inicial"]) & Q(conteo__isnull=False)),
                name="movimiento_inventario_coherente",
            ),
        ]
