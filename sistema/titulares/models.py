from django.conf import settings
from django.db import models
from django.db.models import Q

from nucleo.matricula import formatear


class Agrupacion(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class MotivoBaja(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Familia(models.Model):
    nombre = models.CharField(max_length=100)
    activa = models.BooleanField(default=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class TitularesVisibles(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(interno=False)


MATRICULA_INTERNA = "PUBLICO"


class Titular(models.Model):
    PENDIENTE = "pendiente"
    ACTIVO = "activo"
    BAJA = "baja"
    RECHAZADO = "rechazado"
    ESTADOS = [(PENDIENTE, "Pendiente"), (ACTIVO, "Activo"), (BAJA, "Baja"), (RECHAZADO, "Rechazado")]

    matricula = models.CharField(max_length=12, unique=True, editable=False)
    nombre = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=150)
    agrupacion = models.ForeignKey(Agrupacion, null=True, blank=True, on_delete=models.PROTECT, related_name="titulares")
    familia = models.ForeignKey(Familia, null=True, blank=True, on_delete=models.PROTECT, related_name="miembros")
    activo_desde = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    notas = models.TextField(blank=True)
    constancia_consentimiento = models.BooleanField(default=False)
    conceptos_iniciales = models.ManyToManyField("cobros.ConceptoCobro", blank=True, related_name="+")
    motivo_baja = models.ForeignKey(MotivoBaja, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    fecha_baja = models.DateTimeField(null=True, blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)
    interno = models.BooleanField(default=False, editable=False)

    objects = TitularesVisibles()
    todos = models.Manager()

    class Meta:
        ordering = ["apellidos", "nombre"]
        default_manager_name = "objects"
        constraints = [
            models.CheckConstraint(condition=Q(estado__in=["pendiente", "activo", "baja", "rechazado"]), name="titular_estado_valido"),
            models.UniqueConstraint(fields=["interno"], condition=Q(interno=True), name="titular_una_cuenta_interna"),
            models.CheckConstraint(condition=Q(interno=False) | (Q(estado="activo") & Q(familia__isnull=True)), name="titular_interno_activo_sin_familia"),
        ]

    def __str__(self):
        return f"{self.nombre} {self.apellidos}"

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellidos}"

    @property
    def matricula_formateada(self):
        return "" if self.interno else formatear(self.matricula)

    @property
    def referencia_bancaria(self):
        return self.matricula


class RelacionContacto(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class CampoContacto(models.Model):
    TELEFONO = "telefono"
    CORREO = "correo"
    TEXTO = "texto"
    TIPOS = [(TELEFONO, "Teléfono"), (CORREO, "Correo electrónico"), (TEXTO, "Texto")]

    etiqueta = models.CharField(max_length=60, unique=True)
    tipo = models.CharField(max_length=10, choices=TIPOS)
    obligatorio = models.BooleanField(default=False)
    principal = models.BooleanField(default=False)
    orden = models.PositiveSmallIntegerField(default=10)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["orden", "etiqueta"]
        constraints = [
            models.UniqueConstraint(fields=["principal"], condition=Q(principal=True), name="campo_contacto_un_principal"),
        ]

    def __str__(self):
        return self.etiqueta

    @property
    def clave(self):
        return f"campo_{self.pk}"


class Contacto(models.Model):
    titular = models.ForeignKey(Titular, null=True, blank=True, on_delete=models.CASCADE, related_name="contactos")
    familia = models.ForeignKey(Familia, null=True, blank=True, on_delete=models.CASCADE, related_name="contactos")
    nombre = models.CharField(max_length=150)
    relacion = models.ForeignKey(RelacionContacto, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    valores = models.JSONField(default=dict, blank=True)
    principal = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-principal", "nombre"]
        constraints = [
            models.UniqueConstraint(fields=["titular"], condition=Q(principal=True, titular__isnull=False), name="contacto_un_principal"),
            models.UniqueConstraint(fields=["familia"], condition=Q(principal=True, familia__isnull=False), name="contacto_familia_un_principal"),
            models.CheckConstraint(condition=(Q(titular__isnull=False) & Q(familia__isnull=True)) | (Q(titular__isnull=True) & Q(familia__isnull=False)), name="contacto_de_titular_o_familia"),
        ]

    def __str__(self):
        return self.nombre

    def valor(self, campo):
        return self.valores.get(str(campo.pk), "")


class LotePadron(models.Model):
    nombre_archivo = models.CharField(max_length=120)
    sha256 = models.CharField(max_length=64)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado = models.DateTimeField(auto_now_add=True)
    filas = models.PositiveIntegerField(default=0)
    creados = models.PositiveIntegerField(default=0)
    duplicados = models.PositiveIntegerField(default=0)
    con_error = models.PositiveIntegerField(default=0)
    familias = models.PositiveIntegerField(default=0)
    cargos = models.PositiveIntegerField(default=0)
    a_favor = models.PositiveIntegerField(default=0)
    resultado = models.JSONField(default=dict)

    class Meta:
        ordering = ["-creado"]
