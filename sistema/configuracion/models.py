from zoneinfo import ZoneInfo

from django.db import models
from django.db.models import Q
from django.utils import timezone

VOCABULARIO_BASE = {
    "titular": "Titular",
    "titulares": "Titulares",
    "matricula": "Matrícula",
    "agrupacion": "Agrupación",
    "agrupaciones": "Agrupaciones",
    "familia": "Familia",
    "familias": "Familias",
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
    "dia_generacion_cargos": (1, "Día del mes en que se generan los cargos recurrentes"),
    "orden_reparto": ("recargos,vencimiento,prioridad", "Orden en que un pago cubre los cargos (recargos, vencimiento, prioridad, separados por comas)"),
    "tope_pago_individual": (5000000, "Importe máximo en centavos de un pago individual sin autorización"),
    "umbral_diferencia_arqueo": (1000, "Diferencia en centavos a partir de la cual el arqueo pide nota y avisa a Supervisión"),
    "dias_maximos_efectivo_sin_trasladar": (2, "Días que el efectivo puede quedarse con una persona sin entregarse ni depositarse"),
    "dias_maximos_deposito_sin_conciliar": (5, "Días que un depósito registrado puede quedar sin aparecer en el banco antes de alertar"),
    "confirmaciones_pagador_confiable": (2, "Confirmaciones de un pagador para considerarlo confiable"),
    "aplicar_solo_por_pagador": (0, "1 para aplicar sin revisión los abonos de un pagador confiable aunque no traigan matrícula; 0 para solo sugerirlos"),
    "dias_tolerancia_deposito": (3, "Días de diferencia aceptados entre un depósito de caja y su abono en el banco"),
    "serie_recibos_banco": ("B", "Serie de los recibos de pagos por banco"),
    "serie_recibos_saldo_inicial": ("S", "Serie de los recibos de saldo inicial a favor"),
    "dias_alerta_recibos_cancelados": (7, "Días que un recibo cancelado aparece en las alertas"),
    "segundos_ciclo_trabajador": (300, "Segundos entre ciclos del trabajador"),
    "horas_validez_codigo_activacion": (72, "Horas que vale un código de activación de cuenta"),
    "maximo_altas_pendientes_por_capturista": (30, "Altas pendientes que una persona puede tener al mismo tiempo"),
    "prefijo_pais_telefono": (52, "Prefijo de país que se antepone a los teléfonos"),
    "digitos_telefono_nacional": (10, "Dígitos de un teléfono nacional sin prefijo de país"),
}


class Negocio(models.Model):
    nombre = models.CharField(max_length=150)
    nota_ficha = models.TextField(blank=True)
    zona_horaria = models.CharField(max_length=64, default="America/Mexico_City")
    sede = models.PositiveSmallIntegerField(default=0)
    ranuras = models.PositiveSmallIntegerField(default=10)
    longitud_matricula = models.PositiveSmallIntegerField(default=7)
    contador_matricula = models.BigIntegerField(default=0)
    cobro_desde = models.DateField(null=True, blank=True)
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
    if isinstance(base, str):
        return valor
    try:
        return int(valor)
    except ValueError:
        return base


def hoy_negocio():
    negocio = Negocio.actual()
    zona = ZoneInfo(negocio.zona_horaria) if negocio else timezone.get_default_timezone()
    return timezone.localtime(timezone.now(), zona).date()


class Tarea(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    ultima_ejecucion = models.DateTimeField(null=True, blank=True)
    ultima_fecha = models.DateField(null=True, blank=True)
    exito = models.BooleanField(default=True)
    resultado = models.CharField(max_length=500, blank=True)
    ejecuciones = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre
