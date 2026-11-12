from django.db import models
from django.db.models import Q

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
