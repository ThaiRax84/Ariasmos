from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from nucleo import clabe as nucleo_clabe

TIPOS = [("banco", "Banco"), ("no_bancario", "Institución no bancaria"), ("banca_desarrollo", "Banca de desarrollo"), ("otro", "Otro")]
SOPORTES = [
    ("archivo_verificado", "Archivo verificado"),
    ("archivo_generico", "Archivo genérico"),
    ("convenio", "Convenio"),
    ("sin_probar", "Sin probar"),
]


class Banco(models.Model):
    clave = models.CharField(max_length=3, unique=True)
    nombre = models.CharField(max_length=80)
    tipo = models.CharField(max_length=20, choices=TIPOS, default="banco")
    soporte = models.CharField(max_length=20, choices=SOPORTES, default="sin_probar")
    activo = models.BooleanField(default=True)
    capturado_a_mano = models.BooleanField(default=False)

    class Meta:
        ordering = ["nombre"]
        constraints = [models.CheckConstraint(condition=Q(clave__regex=r"^[0-9]{3}$"), name="banco_clave_tres_digitos")]

    def __str__(self):
        return self.nombre


class MedioPago(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    orden = models.PositiveSmallIntegerField(default=10)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class CuentaBancaria(models.Model):
    NUMERICA = "numerica"
    CONCEPTO = "concepto"
    AMBOS = "ambos"
    REFERENCIA = [(AMBOS, "Referencia numérica y concepto"), (NUMERICA, "Solo referencia numérica"), (CONCEPTO, "Solo concepto")]

    banco = models.ForeignKey(Banco, on_delete=models.PROTECT, related_name="cuentas")
    clabe = models.CharField(max_length=18)
    beneficiario = models.CharField(max_length=150)
    numero_cuenta = models.CharField(max_length=30, blank=True)
    convenio = models.CharField(max_length=30, blank=True)
    medios = models.ManyToManyField(MedioPago, blank=True, related_name="cuentas")
    referencia_en = models.CharField(max_length=10, choices=REFERENCIA, default=AMBOS)
    contacto_dudas = models.CharField(max_length=150, blank=True)
    nota_adicional = models.TextField(blank=True)
    principal = models.BooleanField(default=False)
    activa = models.BooleanField(default=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-principal", "banco__nombre"]
        constraints = [
            models.UniqueConstraint(fields=["principal"], condition=Q(principal=True), name="cuenta_bancaria_una_principal"),
            models.CheckConstraint(condition=Q(clabe__regex=r"^[0-9]{18}$"), name="cuenta_bancaria_clabe_18"),
            models.CheckConstraint(condition=Q(principal=False) | Q(activa=True), name="cuenta_bancaria_principal_activa"),
        ]

    def __str__(self):
        return f"{self.banco} · {self.clabe_formateada}"

    @property
    def clabe_formateada(self):
        return nucleo_clabe.formatear(self.clabe)

    @classmethod
    def principal_activa(cls):
        return cls.objects.filter(principal=True, activa=True).select_related("banco").first()


class Importacion(models.Model):
    ESTADO_PDF = "estado_pdf"
    ARCHIVO = "archivo"
    ADAPTADORES = [(ESTADO_PDF, "Estado de cuenta en PDF"), (ARCHIVO, "Archivo de movimientos")]
    VERIFICADA = "verificada"
    PRIMERA = "primera"
    CON_HUECO = "con_hueco"
    NO_VERIFICABLE = "no_verificable"
    CONTINUIDADES = [(VERIFICADA, "Verificada: continúa el estado anterior"), (PRIMERA, "Primera de la cuenta"), (CON_HUECO, "Con hueco: hay días sin importar"), (NO_VERIFICABLE, "No verificable: archivo editable")]
    A_REVISAR = (CON_HUECO, NO_VERIFICABLE)

    cuenta = models.ForeignKey(CuentaBancaria, on_delete=models.PROTECT, related_name="importaciones")
    nombre_archivo = models.CharField(max_length=120)
    sha256 = models.CharField(max_length=64, db_index=True)
    adaptador = models.CharField(max_length=12, choices=ADAPTADORES)
    periodo_inicio = models.DateField(null=True, blank=True)
    periodo_fin = models.DateField(null=True, blank=True)
    saldo_inicial = models.BigIntegerField(null=True, blank=True)
    saldo_final = models.BigIntegerField(null=True, blank=True)
    depositos = models.BigIntegerField(default=0)
    retiros = models.BigIntegerField(default=0)
    movimientos = models.PositiveIntegerField(default=0)
    nuevos = models.PositiveIntegerField(default=0)
    duplicados = models.PositiveIntegerField(default=0)
    aplicados = models.PositiveIntegerField(default=0)
    sugeridos = models.PositiveIntegerField(default=0)
    sin_pista = models.PositiveIntegerField(default=0)
    depositos_emparejados = models.PositiveIntegerField(default=0)
    otra_via = models.PositiveIntegerField(default=0)
    continuidad = models.CharField(max_length=16, choices=CONTINUIDADES, default=CON_HUECO)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creada = models.DateTimeField(auto_now_add=True)
    revisada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    revisada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creada", "-id"]

    @property
    def requiere_revision(self):
        return self.continuidad in self.A_REVISAR

    def __str__(self):
        return f"{self.nombre_archivo} ({self.creada:%d/%m/%Y})"


class ConsultaMovimientos(models.QuerySet):
    def update(self, **kwargs):
        if set(kwargs) - MovimientoBancario.MUTABLES:
            raise models.ProtectedError("los datos de un movimiento bancario no se modifican", set())
        return super().update(**kwargs)

    def delete(self):
        raise models.ProtectedError("los movimientos bancarios no se borran", set())


class MovimientoBancario(models.Model):
    SPEI = "spei"
    MISMO_BANCO = "mismo_banco"
    EFECTIVO = "efectivo"
    DEVOLUCION = "devolucion"
    OTRO = "otro"
    ARCHIVO = "archivo"
    CLASES = [(SPEI, "SPEI"), (MISMO_BANCO, "Mismo banco"), (EFECTIVO, "Depósito en efectivo"), (DEVOLUCION, "Devolución"), (OTRO, "Otro"), (ARCHIVO, "Abono")]
    ABONO = "abono"
    CARGO = "cargo"
    SENTIDOS = [(ABONO, "Abono"), (CARGO, "Cargo")]
    APLICADO = "aplicado"
    POR_IDENTIFICAR = "por_identificar"
    CONCILIADO = "conciliado"
    NO_COBRO = "no_cobro"
    INFORMATIVO = "informativo"
    MISMO = "mismo"
    ESTADOS = [
        (APLICADO, "Aplicado"),
        (POR_IDENTIFICAR, "Por identificar"),
        (CONCILIADO, "Depósito de caja conciliado"),
        (NO_COBRO, "No es un cobro"),
        (INFORMATIVO, "Informativo"),
        (MISMO, "Mismo movimiento que otro ya importado"),
    ]
    COMPLETABLES = {"banco_origen", "cuenta_pagador", "nombre_pagador", "rastreo"}
    MUTABLES = {
        "estado", "pago", "traslado", "sugerencia", "alternativas", "motivo", "coincide_importe", "propuesta", "propuesta_por", "propuesta_en", "nota",
        "resuelto_por", "resuelto_en", "confirmado_por", "posible_duplicado",
    } | COMPLETABLES

    cuenta = models.ForeignKey(CuentaBancaria, on_delete=models.PROTECT, related_name="movimientos")
    importacion = models.ForeignKey(Importacion, on_delete=models.PROTECT, related_name="lista")
    fecha = models.DateField()
    folio = models.CharField(max_length=40, blank=True)
    descripcion = models.CharField(max_length=300, blank=True)
    importe = models.PositiveBigIntegerField()
    saldo = models.BigIntegerField(null=True, blank=True)
    sentido = models.CharField(max_length=6, choices=SENTIDOS)
    clase = models.CharField(max_length=12, choices=CLASES)
    hora = models.CharField(max_length=8, blank=True)
    banco_origen = models.CharField(max_length=80, blank=True)
    cuenta_pagador = models.CharField(max_length=18, blank=True, db_index=True)
    nombre_pagador = models.CharField(max_length=150, blank=True)
    rastreo = models.CharField(max_length=40, blank=True)
    referencia = models.CharField(max_length=40, blank=True)
    concepto = models.CharField(max_length=200, blank=True)
    huella = models.CharField(max_length=400, unique=True)
    mismo_que = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="otras_vias")
    confirmado_por = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="confirma_a")
    posible_duplicado = models.BooleanField(default=False)
    estado = models.CharField(max_length=16, choices=ESTADOS)
    pago = models.OneToOneField("cobros.Pago", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    traslado = models.OneToOneField("caja.Traslado", null=True, blank=True, on_delete=models.PROTECT, related_name="movimiento")
    sugerencia = models.CharField(max_length=12, blank=True)
    alternativas = models.JSONField(default=list, blank=True)
    motivo = models.CharField(max_length=40, blank=True)
    coincide_importe = models.BooleanField(default=False)
    propuesta = models.ForeignKey("titulares.Titular", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    propuesta_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    propuesta_en = models.DateTimeField(null=True, blank=True)
    nota = models.CharField(max_length=300, blank=True)
    resuelto_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    resuelto_en = models.DateTimeField(null=True, blank=True)

    objects = ConsultaMovimientos.as_manager()

    class Meta:
        ordering = ["fecha", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(importe__gt=0), name="movimiento_importe_positivo"),
            models.CheckConstraint(condition=~Q(estado="aplicado") | Q(pago__isnull=False), name="movimiento_aplicado_con_pago"),
            models.CheckConstraint(condition=~Q(estado="conciliado") | Q(traslado__isnull=False), name="movimiento_conciliado_con_traslado"),
        ]

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y} {self.descripcion[:40]}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            campos = set(kwargs.get("update_fields") or ())
            if not campos or campos - self.MUTABLES:
                raise models.ProtectedError("los datos de un movimiento bancario no se modifican", set())
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise models.ProtectedError("los movimientos bancarios no se borran", set())

    @property
    def cuenta_pagador_enmascarada(self):
        return f"•••• {self.cuenta_pagador[-4:]}" if self.cuenta_pagador else ""


class ReglaPagador(models.Model):
    cuenta_pagador = models.CharField(max_length=18, unique=True)
    titular = models.ForeignKey("titulares.Titular", on_delete=models.PROTECT, related_name="reglas_pagador")
    confirmaciones = models.PositiveIntegerField(default=0)
    ultima_vez = models.DateTimeField(null=True, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["cuenta_pagador"]


class MapeoColumnas(models.Model):
    cuenta = models.OneToOneField(CuentaBancaria, on_delete=models.CASCADE, related_name="mapeo")
    mapeo = models.JSONField(default=dict)
    actualizado = models.DateTimeField(auto_now=True)


class CargaTemporal(models.Model):
    BANCO_PDF = "banco_pdf"
    BANCO_ARCHIVO = "banco_archivo"
    PADRON = "padron"
    TIPOS = [(BANCO_PDF, "Estado de cuenta"), (BANCO_ARCHIVO, "Archivo de movimientos"), (PADRON, "Padrón")]

    token = models.CharField(max_length=43, unique=True)
    tipo = models.CharField(max_length=14, choices=TIPOS)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    nombre_archivo = models.CharField(max_length=120)
    sha256 = models.CharField(max_length=64)
    datos = models.JSONField(default=dict)
    creada = models.DateTimeField(auto_now_add=True)


HORAS_CARGA = 2


def depurar_cargas():
    return CargaTemporal.objects.filter(creada__lt=timezone.now() - timedelta(hours=HORAS_CARGA)).delete()[0]
