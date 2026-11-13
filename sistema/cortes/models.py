from django.conf import settings
from django.db import models
from django.db.models import Q

DIARIO = "diario"
MAYOR = "mayor"
COBRANZA = "cobranza"
TIPOS = [(DIARIO, "Corte diario de caja"), (MAYOR, "Corte mayor"), (COBRANZA, "Lista de cobranza")]
COMPLETO = "completo"
SOLO_NOMBRES = "solo_nombres"
SIN_NOMBRES = "sin_nombres"
NIVELES = [(COMPLETO, "Completo: nombres, matrícula y contacto"), (SOLO_NOMBRES, "Solo nombres: sin matrícula ni contacto"), (SIN_NOMBRES, "Sin nombres: solo matrícula")]


class CorteCerrado(Exception):
    pass


class DefinicionCorte(models.Model):
    tipo = models.CharField(max_length=10, choices=TIPOS, unique=True)
    nombre = models.CharField(max_length=60)
    activa = models.BooleanField(default=True)
    nivel = models.CharField(max_length=15, choices=NIVELES, default=SOLO_NOMBRES)

    class Meta:
        ordering = ["tipo"]

    def __str__(self):
        return self.nombre


class ConsultaCortes(models.QuerySet):
    def update(self, **kwargs):
        return super(ConsultaCortes, self.filter(estado=Corte.BORRADOR)).update(**kwargs)

    def delete(self):
        raise CorteCerrado("los cortes no se borran")


class Corte(models.Model):
    BORRADOR = "borrador"
    CERRADO = "cerrado"
    ESTADOS = [(BORRADOR, "Borrador"), (CERRADO, "Cerrado")]

    tipo = models.CharField(max_length=10, choices=TIPOS)
    fecha = models.DateField()
    periodo_inicio = models.DateField()
    periodo_fin = models.DateField()
    turno = models.OneToOneField("caja.Turno", null=True, blank=True, on_delete=models.PROTECT, related_name="corte")
    caja = models.ForeignKey("caja.Caja", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    numero = models.PositiveIntegerField(default=1)
    automatico = models.BooleanField(default=False)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=BORRADOR)
    tardio = models.BooleanField(default=False)
    sin_revisar = models.BooleanField(default=False)
    cifras = models.JSONField(default=dict)
    hash = models.CharField(max_length=64, blank=True)
    cerrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    cerrado_en = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    objects = ConsultaCortes.as_manager()

    class Meta:
        ordering = ["-fecha", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tipo", "fecha"], condition=Q(tipo=MAYOR), name="corte_mayor_unico"),
            models.UniqueConstraint(fields=["tipo", "fecha"], condition=Q(tipo=COBRANZA, automatico=True), name="cobranza_automatica_unica"),
            models.UniqueConstraint(fields=["tipo", "fecha", "caja", "numero"], condition=Q(tipo=DIARIO), name="corte_diario_numero"),
            models.CheckConstraint(condition=~Q(estado="cerrado") | ~Q(hash=""), name="corte_cerrado_con_hash"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.fecha:%d/%m/%Y}"

    def save(self, *args, **kwargs):
        if not self._state.adding and type(self).objects.filter(pk=self.pk, estado=self.CERRADO).exists():
            raise CorteCerrado("un corte cerrado no se modifica")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise CorteCerrado("los cortes no se borran")

    @property
    def cerrado(self):
        return self.estado == self.CERRADO


class Destino(models.Model):
    CARPETA = "carpeta"
    TIPOS = [(CARPETA, "Carpeta")]

    nombre = models.CharField(max_length=60)
    tipo = models.CharField(max_length=10, choices=TIPOS, default=CARPETA)
    ruta = models.CharField(max_length=400)
    activo = models.BooleanField(default=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class ReglaDestino(models.Model):
    destino = models.ForeignKey(Destino, on_delete=models.CASCADE, related_name="reglas")
    tipo = models.CharField(max_length=10, choices=TIPOS)
    entregar = models.BooleanField(default=True)
    nivel = models.CharField(max_length=15, choices=NIVELES, default=SOLO_NOMBRES)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["destino", "tipo"], name="regla_destino_unica")]


class Entrega(models.Model):
    PENDIENTE = "pendiente"
    ENTREGADA = "entregada"
    FALLIDA = "fallida"
    ESTADOS = [(PENDIENTE, "Pendiente"), (ENTREGADA, "Entregada"), (FALLIDA, "Fallida")]

    corte = models.ForeignKey(Corte, on_delete=models.PROTECT, related_name="entregas")
    destino = models.ForeignKey(Destino, on_delete=models.PROTECT, related_name="entregas")
    nivel = models.CharField(max_length=15, choices=NIVELES)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    intentos = models.PositiveIntegerField(default=0)
    ultimo_error = models.CharField(max_length=300, blank=True)
    proximo_intento = models.DateTimeField(null=True, blank=True)
    ocupada_hasta = models.DateTimeField(null=True, blank=True)
    entregada_en = models.DateTimeField(null=True, blank=True)
    archivos = models.JSONField(default=list, blank=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada", "-id"]
        constraints = [models.UniqueConstraint(fields=["corte", "destino"], name="entrega_unica")]
