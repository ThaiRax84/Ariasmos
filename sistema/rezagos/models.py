from django.conf import settings
from django.db import models
from django.db.models import Q

ILIMITADO = "ilimitado"
VALOR = "valor"
NEGOCIO = "negocio"
MODOS_NEGOCIO = [(ILIMITADO, "Ilimitado"), (VALOR, "Hasta un valor")]
MODOS_EXCEPCION = [(NEGOCIO, "Como el negocio"), (ILIMITADO, "Ilimitado"), (VALOR, "Hasta un valor")]
TOPE_IMPORTE = 10 ** 12
TOPE_DIAS = 3650
LARGO_TEXTO = 60


class LimiteAdeudo(models.Model):
    modo_importe = models.CharField(max_length=10, choices=MODOS_NEGOCIO, default=ILIMITADO)
    importe_maximo = models.PositiveBigIntegerField(default=0)
    modo_dias = models.CharField(max_length=10, choices=MODOS_NEGOCIO, default=ILIMITADO)
    dias_maximos = models.PositiveIntegerField(default=0)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="limite_adeudo_unico"),
            models.CheckConstraint(condition=Q(modo_importe__in=[ILIMITADO, VALOR]), name="limite_modo_importe_valido"),
            models.CheckConstraint(condition=Q(modo_dias__in=[ILIMITADO, VALOR]), name="limite_modo_dias_valido"),
        ]

    def __str__(self):
        return "Límite de adeudo del negocio"

    @classmethod
    def actual(cls):
        return cls.objects.filter(pk=1).first() or cls(pk=1)


class ExcepcionLimite(models.Model):
    titular = models.OneToOneField("titulares.Titular", on_delete=models.PROTECT, related_name="excepcion_limite")
    modo_importe = models.CharField(max_length=10, choices=MODOS_EXCEPCION, default=NEGOCIO)
    importe_maximo = models.PositiveBigIntegerField(default=0)
    modo_dias = models.CharField(max_length=10, choices=MODOS_EXCEPCION, default=NEGOCIO)
    dias_maximos = models.PositiveIntegerField(default=0)
    motivo = models.CharField(max_length=300)
    vigente_hasta = models.DateField(null=True, blank=True)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["titular__apellidos", "titular__nombre"]
        constraints = [
            models.CheckConstraint(condition=Q(modo_importe__in=[NEGOCIO, ILIMITADO, VALOR]), name="excepcion_modo_importe_valido"),
            models.CheckConstraint(condition=Q(modo_dias__in=[NEGOCIO, ILIMITADO, VALOR]), name="excepcion_modo_dias_valido"),
        ]

    def __str__(self):
        return f"Excepción de {self.titular}"


class ReglaRezago(models.Model):
    TODOS = "todos"
    AGRUPACION = "agrupacion"
    TITULAR = "titular"
    ALCANCES = [(TODOS, "Todos"), (AGRUPACION, "{agrupacion}"), (TITULAR, "{titular}")]
    NIVEL = {TODOS: 0, AGRUPACION: 1, TITULAR: 2}
    ACCIONES = ("aviso_inicio", "marca", "sin_credito", "cobranza")

    nombre = models.CharField(max_length=100)
    texto = models.CharField(max_length=LARGO_TEXTO)
    alcance = models.CharField(max_length=12, choices=ALCANCES, default=TODOS)
    agrupacion = models.ForeignKey("titulares.Agrupacion", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    titular = models.ForeignKey("titulares.Titular", null=True, blank=True, on_delete=models.PROTECT, related_name="reglas_rezago")
    dias_minimos = models.PositiveIntegerField(null=True, blank=True)
    importe_minimo = models.PositiveBigIntegerField(null=True, blank=True)
    al_rebasar_limite = models.BooleanField(default=False)
    aviso_inicio = models.BooleanField(default=False)
    marca = models.BooleanField(default=False)
    sin_credito = models.BooleanField(default=False)
    cobranza = models.BooleanField(default=False)
    activa = models.BooleanField(default=True)
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["alcance", "dias_minimos", "nombre", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(alcance="todos") & Q(agrupacion__isnull=True) & Q(titular__isnull=True))
                | (Q(alcance="agrupacion") & Q(agrupacion__isnull=False) & Q(titular__isnull=True))
                | (Q(alcance="titular") & Q(titular__isnull=False) & Q(agrupacion__isnull=True)),
                name="regla_rezago_alcance_coherente",
            ),
            models.CheckConstraint(condition=Q(dias_minimos__isnull=False) | Q(importe_minimo__isnull=False) | Q(al_rebasar_limite=True), name="regla_rezago_con_condicion"),
            models.CheckConstraint(condition=Q(aviso_inicio=True) | Q(marca=True) | Q(sin_credito=True) | Q(cobranza=True), name="regla_rezago_con_accion"),
            models.CheckConstraint(condition=Q(dias_minimos__isnull=True) | Q(dias_minimos__gte=1), name="regla_rezago_dias_positivos"),
            models.CheckConstraint(condition=Q(importe_minimo__isnull=True) | Q(importe_minimo__gte=1), name="regla_rezago_importe_positivo"),
        ]

    def __str__(self):
        return self.nombre

    @property
    def nivel(self):
        return self.NIVEL[self.alcance]

    def aplica_a(self, titular_id, agrupacion_id):
        if self.alcance == self.TITULAR:
            return self.titular_id == titular_id
        if self.alcance == self.AGRUPACION:
            return agrupacion_id is not None and self.agrupacion_id == agrupacion_id
        return True

    def se_cumple(self, vencido, dias, rebasa):
        if self.dias_minimos is not None and dias >= self.dias_minimos:
            return True
        if self.importe_minimo is not None and vencido >= self.importe_minimo:
            return True
        return self.al_rebasar_limite and rebasa

    @property
    def gravedad(self):
        return (self.dias_minimos or 0, self.importe_minimo or 0, self.pk or 0)

    @property
    def acciones(self):
        return [a for a in self.ACCIONES if getattr(self, a)]
