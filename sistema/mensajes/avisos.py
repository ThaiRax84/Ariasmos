from collections import Counter, defaultdict, namedtuple
from datetime import time, timedelta
from functools import cached_property, partial, reduce
from operator import or_

from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.utils import timezone

from auditoria.servicios import registrar
from cobros import libro
from cobros.models import Cargo, Recibo
from configuracion.models import PARAMETROS, Negocio, parametro, zona_negocio
from configuracion.moneda import formatear
from rezagos.calculo import ESTADOS, con_efectivo
from titulares import contactos

from . import servicios, variables
from .models import Aviso, Envio, PlantillaMensaje

MAXIMO_POR_CICLO = 50
SEMANA = timedelta(days=7)
VENTANA_DEL_RECIBO = timedelta(hours=24)
DIAS_DE_MARGEN_DE_ATRASO = 7
CALCULABLES = frozenset(variables.EJEMPLOS) - {"folio"}
REINTENTABLES = (Envio.NO_ENVIADO, Envio.INCIERTO)
CIERRAN_EL_CICLO = {
    servicios.MOTIVOS["tope"],
    servicios.MOTIVOS["sin_conexion"],
    servicios.SIN_RESPUESTA,
}
MOMENTOS_DE_AVISO = (Aviso.PAGO, Aviso.ANTES, Aviso.ATRASO)
MOMENTOS_DEL_MAXIMO = (Aviso.ANTES, Aviso.ATRASO)
MAXIMOS_POR_SEMANA = (1, 14)
CAMBIO = "El aviso cambió antes de salir"
Trabajo = namedtuple("Trabajo", ["previo", "mandar"])
EN_PAUSA = "En pausa: "
SIN_APROBAR = EN_PAUSA + "el mensaje no está aprobado"
NO_SIRVE = EN_PAUSA + "este mensaje no sirve para este aviso"
SIN_DATO = EN_PAUSA + "el mensaje usa un dato que este aviso no tiene"


def sirve_el_documento(aviso):
    return aviso.plantilla.con_documento == (aviso.momento == Aviso.PAGO)


def _calculables(plantilla):
    return CALCULABLES.issuperset(variables.usadas(plantilla.texto))


def pausa(aviso):
    if aviso.plantilla.estado != PlantillaMensaje.APROBADA:
        return SIN_APROBAR
    if not sirve_el_documento(aviso):
        return NO_SIRVE
    if aviso.momento != Aviso.PAGO and not _calculables(aviso.plantilla):
        return SIN_DATO
    return ""


def horario():
    de_fabrica = tuple(
        time.fromisoformat(PARAMETROS[clave][0])
        for clave in ("avisos_hora_inicio", "avisos_hora_fin")
    )
    try:
        inicio = time.fromisoformat(str(parametro("avisos_hora_inicio")))
        fin = time.fromisoformat(str(parametro("avisos_hora_fin")))
    except ValueError:
        return de_fabrica
    return (inicio, fin) if inicio < fin else de_fabrica


def maximo_por_semana():
    minimo, maximo = MAXIMOS_POR_SEMANA
    return min(max(parametro("avisos_maximo_semana"), minimo), maximo)


def dias_sin_envio():
    texto = str(parametro("avisos_dias_sin_envio"))
    return {int(d) for d in texto.split(",") if d.strip().isdigit() and int(d) <= 6}


def _de_la_semana(ahora, contactos=None):
    envios = Envio.objects.filter(
        momento__in=MOMENTOS_DEL_MAXIMO, creado__gte=ahora - SEMANA
    ).exclude(estado=Envio.NO_ENVIADO)
    if contactos is not None:
        envios = envios.filter(contacto_id__in=contactos)
    filas = envios.order_by().values("contacto_id").annotate(total=Count("id"))
    return defaultdict(int, {f["contacto_id"]: f["total"] for f in filas})


class _Ciclo:
    def __init__(self, ahora):
        self.ahora = ahora
        self.hoy = libro.fecha_local(ahora)
        self.cupo = MAXIMO_POR_CICLO
        self.detenido = False
        self.enviados = Counter()
        self.sin_enviar = 0

    @property
    def sigue(self):
        return self.cupo > 0 and not self.detenido

    @cached_property
    def en_horario(self):
        local = timezone.localtime(self.ahora, zona_negocio())
        inicio, fin = horario()
        return inicio <= local.time() < fin and local.weekday() not in dias_sin_envio()

    @cached_property
    def maximo_semanal(self):
        return maximo_por_semana()

    @cached_property
    def semanales(self):
        return _de_la_semana(self.ahora)

    @cached_property
    def telefono_de(self):
        return servicios.lector_de_telefonos()

    @cached_property
    def negocio(self):
        return Negocio.actual().nombre

    def anotar(self, aviso, envio):
        self.cupo -= 1
        if envio.estado == Envio.ACEPTADO:
            self.enviados[aviso.momento] += 1
        else:
            self.sin_enviar += 1
        self.detenido = (
            envio.estado == Envio.INCIERTO or envio.motivo in CIERRAN_EL_CICLO
        )


def _recibos_por_mandar(ciclo, aviso):
    sin_reintento = Envio.objects.filter(recibo=OuterRef("pk")).exclude(
        Q(aviso__isnull=False) & Q(estado__in=REINTENTABLES)
    )
    return (
        Recibo.objects.filter(
            pago__fecha__gt=aviso.activado,
            pago__fecha__gte=ciclo.ahora - VENTANA_DEL_RECIBO,
            pago__reversion__isnull=True,
            pago__titular__interno=False,
        )
        .exclude(Exists(sin_reintento))
        .select_related("pago__titular")
        .order_by("pago__fecha")
    )


def _mandar_recibo(ciclo, aviso, recibo):
    try:
        envio = servicios.mandar_recibo(recibo, None, aviso.plantilla, aviso=aviso)
    except servicios.NoSePuedeEnviar:
        return
    ciclo.anotar(aviso, envio)


def _trabajos_de_recibos(ciclo, aviso):
    recibos = list(_recibos_por_mandar(ciclo, aviso))
    principales = contactos.principales([r.pago.titular for r in recibos])
    previos = {e.recibo_id: e for e in Envio.objects.filter(recibo__in=recibos)}
    trabajos = []
    for recibo in recibos:
        contacto = principales[recibo.pago.titular_id]
        if contacto and not servicios.falta_de(contacto, ciclo.telefono_de(contacto)):
            trabajos.append(
                Trabajo(previos.get(recibo.pk), partial(_mandar_recibo, ciclo, aviso, recibo))
            )
    return trabajos


def _fechas_del_aviso(aviso, hoy):
    if aviso.momento == Aviso.ANTES:
        return hoy + timedelta(days=1), hoy + timedelta(days=aviso.dias)
    lejos = hoy - timedelta(days=aviso.dias + DIAS_DE_MARGEN_DE_ATRASO)
    return lejos, hoy - timedelta(days=aviso.dias)


def _cargos_por_avisar(aviso, hoy):
    cargos = Cargo.objects.filter(
        titular__estado__in=ESTADOS, titular__interno=False
    ).exclude(origen=Cargo.RECARGO)
    agrupaciones = [a.pk for a in aviso.agrupaciones.all()]
    if agrupaciones:
        cargos = cargos.filter(titular__agrupacion__in=agrupaciones)
    desde, hasta = _fechas_del_aviso(aviso, hoy)
    ya_avisado = Envio.objects.filter(aviso=aviso, cargo=OuterRef("pk")).exclude(
        estado__in=REINTENTABLES
    )
    return (
        con_efectivo(libro.con_saldo(cargos))
        .filter(saldo__gt=0, efectivo__gte=desde, efectivo__lte=hasta)
        .exclude(Exists(ya_avisado))
        .select_related("concepto", "titular")
        .order_by("titular_id", "efectivo", "id")
    )


def _el_mas_antiguo_de_cada_titular(cargos):
    primeros = {}
    for cargo in cargos:
        primeros.setdefault(cargo.titular_id, cargo)
    return list(primeros.values())


def _adeudos(titulares):
    filas = (
        libro.con_saldo(Cargo.objects.filter(titular__in=titulares))
        .filter(saldo__gt=0)
        .order_by()
        .values("titular_id")
        .annotate(total=Sum("saldo"))
    )
    return {f["titular_id"]: f["total"] for f in filas}


def _valores(ciclo, plantilla, cargo, contacto, adeudo):
    dias = (cargo.efectivo - ciclo.hoy).days
    datos = {
        "nombre": lambda: contacto.nombre,
        "alumno": lambda: cargo.titular.nombre_completo,
        "concepto": lambda: cargo.concepto.nombre,
        "importe": lambda: formatear(cargo.saldo),
        "adeudo": lambda: formatear(adeudo),
        "fecha": lambda: cargo.efectivo.strftime("%d/%m/%Y"),
        "dias": lambda: str(abs(dias)),
        "negocio": lambda: ciclo.negocio,
    }
    return {
        nombre: variables.limpiar_valor(datos[nombre]())
        for nombre in variables.usadas(plantilla.texto)
    }


def _pedir_aviso(envio, numero, valores):
    datos = {
        "clave_envio": envio.clave_envio,
        "plantilla": envio.plantilla.clave,
        "destino": numero,
        "valores": valores,
    }
    servicios._aplicar_resultado(envio, servicios._pedir("mensajes_enviar", datos))


def _crear_envio(ciclo, aviso, cargo, contacto, numero):
    try:
        with transaction.atomic():
            ya_enviados = _de_la_semana(ciclo.ahora, [contacto.pk])[contacto.pk]
            if ya_enviados >= ciclo.maximo_semanal:
                return None
            return Envio.objects.create(
                clave_envio=f"aviso-{aviso.pk}-{cargo.pk}",
                plantilla=aviso.plantilla,
                contacto=contacto,
                titular=cargo.titular,
                aviso=aviso,
                cargo=cargo,
                destino_final=numero[-4:],
            )
    except IntegrityError:
        return None


def _cuenta_en_la_semana(ciclo, envio):
    return (
        envio is not None
        and envio.estado == Envio.INCIERTO
        and envio.creado >= ciclo.ahora - SEMANA
    )


def _mandar_cargo(ciclo, aviso, cargo, contacto, previo, adeudo):
    numero = ciclo.telefono_de(contacto)
    if servicios.falta_de(contacto, numero):
        return
    contado = _cuenta_en_la_semana(ciclo, previo)
    if ciclo.semanales[contacto.pk] - contado >= ciclo.maximo_semanal:
        return
    envio = previo or _crear_envio(ciclo, aviso, cargo, contacto, numero)
    if envio is None:
        return
    valores = _valores(ciclo, envio.plantilla, cargo, contacto, adeudo)
    _pedir_aviso(envio, numero, valores)
    ciclo.anotar(aviso, envio)
    if envio.estado != Envio.NO_ENVIADO and not contado:
        ciclo.semanales[contacto.pk] += 1


def _trabajos_de_cargos(ciclo, aviso):
    elegidos = _el_mas_antiguo_de_cada_titular(_cargos_por_avisar(aviso, ciclo.hoy))
    if not elegidos:
        return []
    titulares = [c.titular for c in elegidos]
    principales = contactos.principales(titulares)
    previos = {
        e.cargo_id: e
        for e in Envio.objects.filter(
            aviso=aviso, cargo__in=[c.pk for c in elegidos], estado__in=REINTENTABLES
        ).select_related("plantilla")
    }
    adeudos = (
        _adeudos(titulares)
        if "adeudo" in variables.usadas(aviso.plantilla.texto)
        else {}
    )
    return [
        Trabajo(
            previos.get(cargo.pk),
            partial(
                _mandar_cargo,
                ciclo,
                aviso,
                cargo,
                principales[cargo.titular_id],
                previos.get(cargo.pk),
                adeudos.get(cargo.titular_id, 0),
            ),
        )
        for cargo in elegidos
        if principales[cargo.titular_id] is not None
    ]


def _activos():
    avisos = Aviso.objects.filter(activo=True).select_related("plantilla")
    return [a for a in avisos.prefetch_related("agrupaciones") if not pausa(a)]


def _bitacora(ciclo):
    if ciclo.cupo < MAXIMO_POR_CICLO:
        registrar(
            "avisos_enviados",
            datos={**ciclo.enviados, "sin_enviar": ciclo.sin_enviar},
        )


def _cerrar_los_que_cambiaron(activos):
    vigentes = [Q(aviso=a, plantilla=a.plantilla_id) for a in activos]
    cambiados = Envio.objects.filter(
        estado__in=REINTENTABLES, momento__in=MOMENTOS_DE_AVISO
    )
    if vigentes:
        cambiados = cambiados.exclude(reduce(or_, vigentes))
    cambiados.update(estado=Envio.FALLIDO, motivo=CAMBIO)


def _trabajos(ciclo, activos):
    trabajos = []
    for aviso in activos:
        if aviso.momento == Aviso.PAGO:
            trabajos += _trabajos_de_recibos(ciclo, aviso)
        elif ciclo.en_horario:
            trabajos += _trabajos_de_cargos(ciclo, aviso)
    return sorted(trabajos, key=lambda trabajo: trabajo.previo is not None)


def ejecutar(ahora=None):
    if not servicios.disponible():
        return 0
    ciclo = _Ciclo(ahora or timezone.now())
    activos = _activos()
    _cerrar_los_que_cambiaron(activos)
    for trabajo in _trabajos(ciclo, activos):
        if not ciclo.sigue:
            break
        trabajo.mandar()
    _bitacora(ciclo)
    return sum(ciclo.enviados.values())
