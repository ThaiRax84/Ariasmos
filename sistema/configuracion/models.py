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
    "calendario_corte": ('{"0":"18:00","1":"18:00","2":"18:00","3":"18:00","4":"18:00","5":"18:00","6":"18:00"}', "Días con corte de caja y hora límite de cada uno"),
    "dia_corte_mayor": (1, "Día del mes en que se genera el corte mayor del mes anterior (1 a 28)"),
    "dias_plazo_corte_mayor": (5, "Días para cerrar el corte mayor antes de que se cierre solo marcado sin revisar"),
    "dia_semana_cobranza": (1, "Día de la semana de la lista de cobranza automática (1 lunes a 7 domingo; 0 para no generarla)"),
    "hora_respaldo": ("02:00", "Hora del respaldo diario (HH:MM, hora del negocio)"),
    "control_denominaciones": (0, "1 para capturar piezas por denominación en apertura, cobros, retiros y devoluciones; 0 para no hacerlo"),
    "periodo_retiros": ("dia", "Periodo en que se cuentan los topes de retiros (dia o semana)"),
    "tope_retiro_individual": (0, "Importe máximo en centavos de un retiro de caja sin autorización"),
    "tope_retiros_periodo": (0, "Importe máximo en centavos de los retiros de una caja en el periodo sin autorización"),
    "maximo_retiros_periodo": (0, "Número máximo de retiros de una caja en el periodo sin autorización"),
    "maximo_efectivo_caja": (0, "Efectivo máximo en centavos en una caja antes de avisar que se entregue (0 sin aviso)"),
    "dias_retiro_sin_revisar": (3, "Días que un retiro puede quedar sin revisar antes de avisar a Supervisión"),
    "serie_retiros": ("R", "Serie de los folios de retiros de caja"),
    "intentos_verificar_recibo_por_hora": (20, "Verificaciones de recibo fallidas por hora, por persona y por equipo, antes de bloquear la verificación"),
    "propuestas_cambio_sin_cobro": (10, "Propuestas de cambio sin cobro registrado que se permiten por turno"),
    "tope_aplicado_sin_respaldo": (0, "Importe máximo en centavos de pagos aplicados desde archivos editables de la carpeta vigilada sin respaldo de un estado en PDF (0 retiene todo archivo editable)"),
    "tope_pago_carpeta": (0, "Importe máximo en centavos de un pago aplicado solo desde un archivo editable de la carpeta vigilada (0 sin tope individual)"),
    "dias_sin_respaldo_alerta": (45, "Días que un pago aplicado desde un archivo editable puede quedar sin un estado en PDF que lo respalde antes de alertar"),
    "modulo_inventario": (0, "1 para usar el inventario; 0 para ocultarlo"),
    "devoluciones_inventario": (0, "1 para aceptar devoluciones de artículos vendidos; 0 para no aceptarlas"),
    "dias_devolucion": (15, "Días después de la venta en que se acepta una devolución de artículos"),
    "dias_conteo_sin_aprobar": (3, "Días que un conteo de inventario puede esperar aprobación antes de avisar a Dirección"),
    "serie_devoluciones": ("D", "Serie de los recibos de saldo a favor por devolución de artículos"),
}

ESPECIALES = (
    "calendario_corte",
    "control_denominaciones",
    "periodo_retiros",
    "tope_retiro_individual",
    "tope_retiros_periodo",
    "maximo_retiros_periodo",
    "maximo_efectivo_caja",
    "dias_retiro_sin_revisar",
    "tope_aplicado_sin_respaldo",
    "tope_pago_carpeta",
    "modulo_inventario",
    "devoluciones_inventario",
    "dias_devolucion",
    "dias_conteo_sin_aprobar",
)


class Negocio(models.Model):
    nombre = models.CharField(max_length=150)
    nota_ficha = models.TextField(blank=True)
    zona_horaria = models.CharField(max_length=64, default="America/Mexico_City")
    moneda = models.CharField(max_length=3, default="MXN")
    sede = models.PositiveSmallIntegerField(default=0)
    ranuras = models.PositiveSmallIntegerField(default=10)
    longitud_matricula = models.PositiveSmallIntegerField(default=7)
    contador_matricula = models.BigIntegerField(default=0)
    cobro_desde = models.DateField(null=True, blank=True)
    periodo_cerrado_hasta = models.DateField(null=True, blank=True)
    carpeta_respaldo = models.CharField(max_length=400, blank=True)
    carpeta_banco = models.CharField(max_length=400, blank=True)
    clave_recuperacion_pendiente = models.BooleanField(default=True)
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


def inventario_activo():
    return bool(parametro("modulo_inventario"))


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
