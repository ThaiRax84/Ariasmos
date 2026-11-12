from django.db import models
from django.db.models import Q

VOCABULARIO_BASE = {
    "titular": "Titular",
    "titulares": "Titulares",
    "matricula": "Matrícula",
    "agrupacion": "Agrupación",
    "agrupaciones": "Agrupaciones",
}

PARAMETROS = {
    "intentos_antes_de_bloqueo": (5, "Intentos fallidos de inicio de sesión antes de bloquear la cuenta"),
    "minutos_bloqueo_inicial": (1, "Minutos del primer bloqueo; se duplica con cada intento fallido adicional"),
    "minutos_bloqueo_maximo": (1440, "Minutos máximos de bloqueo"),
    "minutos_validez_reingreso": (5, "Minutos que vale el reingreso de contraseña para acciones delicadas"),
    "ventana_codigo_pasos": (1, "Periodos de 30 segundos de tolerancia para los códigos del autenticador"),
    "dias_maximos_delegacion": (30, "Días máximos de una delegación temporal"),
    "intentos_por_equipo_cada_5_minutos": (30, "Intentos de inicio de sesión permitidos por equipo cada 5 minutos"),
    "intentos_codigo_por_solicitud": (5, "Códigos erróneos permitidos por solicitud antes de exigir la bandeja"),
    "intentos_codigo_por_hora": (5, "Códigos por teléfono erróneos por hora, por capturista y por autorizador, antes de bloquear esa vía"),
    "maximo_equipos_pendientes": (50, "Equipos pendientes de aprobación como máximo; los de más de 24 horas se depuran solos"),
    "horas_validez_codigo_activacion": (72, "Horas que vale un código de activación de cuenta"),
    "maximo_altas_pendientes_por_capturista": (30, "Altas pendientes que una persona puede tener al mismo tiempo"),
    "prefijo_pais_telefono": (52, "Prefijo de país que se antepone a los teléfonos"),
    "digitos_telefono_nacional": (10, "Dígitos de un teléfono nacional sin prefijo de país"),
}


class Negocio(models.Model):
    nombre = models.CharField(max_length=150)
    instrucciones_pago = models.TextField(blank=True)
    zona_horaria = models.CharField(max_length=64, default="America/Mexico_City")
    sede = models.PositiveSmallIntegerField(default=0)
    ranuras = models.PositiveSmallIntegerField(default=10)
    longitud_matricula = models.PositiveSmallIntegerField(default=7)
    contador_matricula = models.BigIntegerField(default=0)
    plantilla = models.CharField(max_length=40, blank=True)
    configurado = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="negocio_unico"),
            models.CheckConstraint(condition=Q(longitud_matricula__gte=5, longitud_matricula__lte=12), name="negocio_longitud"),
            models.CheckConstraint(condition=Q(ranuras__gte=1), name="negocio_ranuras"),
            models.CheckConstraint(condition=Q(sede__lt=models.F("ranuras")), name="negocio_sede"),
            models.CheckConstraint(condition=Q(contador_matricula__gte=0), name="negocio_contador"),
        ]

    def __str__(self):
        return self.nombre

    @classmethod
    def actual(cls):
        return cls.objects.filter(pk=1).first()

    @property
    def matriculas_emitidas(self):
        return self.contador_matricula > 0


class Vocabulario(models.Model):
    clave = models.CharField(max_length=30, unique=True, choices=[(k, k) for k in VOCABULARIO_BASE])
    texto = models.CharField(max_length=60)

    def __str__(self):
        return f"{self.clave}: {self.texto}"


class Parametro(models.Model):
    clave = models.CharField(max_length=60, unique=True, choices=[(k, k) for k in PARAMETROS])
    valor = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.clave}={self.valor}"


def vocabulario():
    textos = dict(VOCABULARIO_BASE)
    textos.update(dict(Vocabulario.objects.values_list("clave", "texto")))
    return textos


def parametro(clave):
    base = PARAMETROS[clave][0]
    valor = Parametro.objects.filter(clave=clave).values_list("valor", flat=True).first()
    if valor is None:
        return base
    try:
        return int(valor)
    except ValueError:
        return base
