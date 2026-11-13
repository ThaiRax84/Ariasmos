from django.conf import settings
from django.db import models
from django.db.models import Q


class Configuracion(models.Model):
    activa = models.BooleanField(default=False)
    canal = models.CharField(max_length=20, default="github")
    repositorio = models.CharField(max_length=140, blank=True)
    clave_cifrada = models.TextField(blank=True)
    cambiada_en = models.DateTimeField(null=True, blank=True)
    cambiada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    ultima_busqueda = models.DateTimeField(null=True, blank=True)
    proxima_busqueda = models.DateTimeField(null=True, blank=True)
    busqueda_pedida = models.BooleanField(default=False)
    busqueda_pedida_en = models.DateTimeField(null=True, blank=True)
    ultimo_resultado = models.CharField(max_length=200, blank=True)
    contador_version = models.BigIntegerField(default=0)
    contador_llave = models.BigIntegerField(default=0)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name="actualizaciones_configuracion_unica")]

    @property
    def tiene_clave(self):
        return bool(self.clave_cifrada)


class LlaveDeUso(models.Model):
    llave = models.CharField(max_length=44)
    recuperacion = models.CharField(max_length=44)
    contador = models.BigIntegerField()
    aviso = models.BinaryField()
    firma = models.BinaryField()
    aceptada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-contador"]
        constraints = [models.UniqueConstraint(fields=["recuperacion", "contador"], name="llave_de_uso_contador_por_recuperacion")]


class VersionPublicada(models.Model):
    version = models.CharField(max_length=20)
    contador = models.BigIntegerField()
    aviso = models.BinaryField()
    firma = models.BinaryField()
    llave = models.CharField(max_length=44)
    datos = models.JSONField(default=dict)
    recibida_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-contador"]
        constraints = [models.UniqueConstraint(fields=["llave", "contador"], name="version_publicada_contador_por_llave")]

    def __str__(self):
        return self.version

    @property
    def cambios(self):
        return list(self.datos.get("cambios") or [])

    @property
    def minimo(self):
        return self.datos.get("minimo", "")


class Descarga(models.Model):
    PENDIENTE = "pendiente"
    EN_CURSO = "en_curso"
    LISTA = "lista"
    FALLIDA = "fallida"
    ESTADOS = [(PENDIENTE, "Pendiente"), (EN_CURSO, "Descargando"), (LISTA, "Lista para instalar"), (FALLIDA, "Fallida")]

    version = models.ForeignKey(VersionPublicada, on_delete=models.PROTECT, related_name="descargas")
    pedida_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    pedida_en = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    en_proceso = models.BooleanField(null=True, default=True)
    iniciada_en = models.DateTimeField(null=True, blank=True)
    terminada_en = models.DateTimeField(null=True, blank=True)
    motivo = models.CharField(max_length=200, blank=True)
    archivo = models.CharField(max_length=120, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-pedida_en", "-id"]
        constraints = [models.UniqueConstraint(fields=["en_proceso"], condition=Q(en_proceso=True), name="una_descarga_a_la_vez")]


class RechazoReciente(models.Model):
    motivo = models.CharField(max_length=60, unique=True)
    ultimo = models.DateTimeField()
