import secrets
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Count, F, Max, Sum
from django.utils import timezone

from auditoria.servicios import registrar
from configuracion.models import parametro
from cortes.calculo import local, zona

from . import comprobantes
from . import piezas as control_piezas
from .models import Caja, ComprobanteRetiro, MotivoRetiro, MovimientoPiezas, RetiroCaja, ReversionRetiro, Turno
from .servicios import ErrorCaja, neto_de, recibe_movimientos, turno_abierto

RECHAZOS_ANTES_DE_AUTORIZAR = 3
AVISO_TOPE = 80
MOTIVOS_TOPE = {
    "importe_individual": "pasa del importe máximo por retiro",
    "importe_periodo": "pasa del importe máximo del periodo",
    "cantidad_periodo": "pasa del número máximo de retiros del periodo",
    "rechazos": "el turno acumuló rechazos por falta de efectivo",
}


@dataclass
class Resultado:
    retiro: RetiroCaja = None
    solicitud: object = None
    rechazado: bool = False
    motivos: list = field(default_factory=list)


def topes():
    return {
        "periodo": "semana" if parametro("periodo_retiros") == "semana" else "dia",
        "importe_individual": int(parametro("tope_retiro_individual")),
        "importe_periodo": int(parametro("tope_retiros_periodo")),
        "cantidad_periodo": int(parametro("maximo_retiros_periodo")),
        "efectivo_maximo": int(parametro("maximo_efectivo_caja")),
    }


def periodo(momento=None, tipo=None):
    tipo = tipo or topes()["periodo"]
    ahora = local(momento or timezone.now())
    inicio = ahora.date() - timedelta(days=ahora.weekday() if tipo == "semana" else 0)
    desde = datetime.combine(inicio, time.min, tzinfo=zona())
    return desde, desde + timedelta(days=7 if tipo == "semana" else 1)


def uso(caja, momento=None, tipo=None):
    desde, hasta = periodo(momento, tipo)
    datos = RetiroCaja.objects.filter(caja=caja, creado__gte=desde, creado__lt=hasta).aggregate(importe=Sum("importe"), cantidad=Count("id"))
    return {"importe": datos["importe"] or 0, "cantidad": datos["cantidad"] or 0}


def excede(turno, importe):
    limites = topes()
    usado = uso(turno.caja)
    motivos = []
    if importe > limites["importe_individual"]:
        motivos.append("importe_individual")
    if usado["importe"] + importe > limites["importe_periodo"]:
        motivos.append("importe_periodo")
    if usado["cantidad"] + 1 > limites["cantidad_periodo"]:
        motivos.append("cantidad_periodo")
    if turno.rechazos_retiro >= RECHAZOS_ANTES_DE_AUTORIZAR:
        motivos.append("rechazos")
    return motivos


def _motivo(motivo):
    pk = motivo.pk if isinstance(motivo, MotivoRetiro) else motivo
    objeto = MotivoRetiro.objects.filter(pk=pk, activo=True).first() if type(pk) is int else None
    if objeto is None:
        raise ErrorCaja("Elige un motivo de retiro válido.")
    return objeto


def validar_piezas(piezas, importe):
    if not control_piezas.activo():
        return {}
    try:
        return control_piezas.exigir_total(piezas or {}, importe, "Las piezas del retiro deben sumar exactamente el importe.")
    except control_piezas.ErrorPiezas as error:
        raise ErrorCaja(str(error))


def _siguiente_folio(serie):
    ultimo = RetiroCaja.objects.filter(serie=serie).aggregate(m=Max("folio"))["m"] or 0
    return ultimo + 1


def crear(turno, usuario, importe, motivo, nota, piezas, request=None, solicitud=None, autorizador=None):
    serie = str(parametro("serie_retiros")).strip().upper() or "R"
    retiro = RetiroCaja.objects.create(
        serie=serie, folio=_siguiente_folio(serie), turno=turno, caja=turno.caja, registrado_por=usuario, importe=importe, motivo=motivo,
        nota=(nota or "").strip()[:300], solicitud=solicitud, autorizado_por=autorizador,
    )
    control_piezas.registrar(turno, usuario, MovimientoPiezas.RETIRO, piezas, -1, retiro=retiro)
    registrar(
        "retiro_registrado",
        usuario=usuario,
        objeto=retiro,
        datos={"folio": str(retiro), "caja": turno.caja.nombre, "turno": turno.pk, "importe": importe, "motivo": motivo.nombre, "nota": retiro.nota, "piezas": piezas, "solicitud": solicitud.pk if solicitud else None, "autorizo": str(autorizador) if autorizador else None},
        request=request,
    )
    return retiro


def registrar_retiro(usuario, importe, motivo, nota="", piezas=None, archivo=None, request=None):
    from solicitudes import motor

    if type(importe) is not int or importe <= 0:
        raise ErrorCaja("El importe debe ser mayor que cero.")
    motivo = _motivo(motivo)
    piezas = validar_piezas(piezas, importe)
    preparado = comprobantes.preparar(archivo) if archivo is not None else None
    with transaction.atomic():
        turno = turno_abierto(usuario)
        if turno is None:
            raise ErrorCaja("Abre tu turno de caja antes de retirar efectivo.")
        if not recibe_movimientos(turno):
            raise ErrorCaja("El turno ya está en arqueo: no admite retiros.")
        turno = Turno.objects.select_related("caja").get(pk=turno.pk)
        motivos = excede(turno, importe)
        if motivos:
            datos = {"turno": turno.pk, "importe": importe, "motivo": motivo.pk, "nota": (nota or "").strip()[:300], "piezas": piezas, "ficha": secrets.token_urlsafe(18), "excede": motivos}
            try:
                resultado = motor.ejecutar("retiro_caja", usuario, None, datos, request=request)
            except motor.ErrorSolicitud as error:
                raise ErrorCaja(str(error))
            return Resultado(solicitud=resultado.solicitud, motivos=motivos)
        if importe > neto_de(turno):
            Turno.objects.filter(pk=turno.pk).update(rechazos_retiro=F("rechazos_retiro") + 1)
            turno.refresh_from_db()
            registrar("retiro_rechazado", usuario=usuario, objeto=turno, datos={"caja": turno.caja.nombre, "importe_pedido": importe, "motivo": "efectivo_insuficiente", "rechazos": turno.rechazos_retiro}, request=request)
            return Resultado(rechazado=True)
        retiro = crear(turno, usuario, importe, motivo, nota, piezas, request)
        if preparado is not None:
            adjuntar_preparado(retiro, usuario, preparado, request)
    return Resultado(retiro=retiro)


def adjuntar_preparado(retiro, usuario, preparado, request=None):
    tipo, contenido = preparado
    nombre, huella = comprobantes.guardar(tipo, contenido)
    with transaction.atomic():
        hechos = RetiroCaja.objects.filter(pk=retiro.pk, comprobante=RetiroCaja.PENDIENTE).update(comprobante=RetiroCaja.ADJUNTO)
        if hechos != 1:
            raise ErrorCaja("El retiro ya tiene comprobante o se declaró sin él.")
        objeto = ComprobanteRetiro.objects.create(retiro=retiro, archivo=nombre, tipo=tipo, tamano=len(contenido), sha256=huella, subido_por=usuario)
        registrar("comprobante_adjuntado", usuario=usuario, objeto=retiro, datos={"folio": str(retiro), "tipo": tipo, "tamano": len(contenido), "sha256": huella}, request=request)
    return objeto


def adjuntar(retiro, usuario, contenido, request=None):
    if retiro.registrado_por_id != usuario.pk:
        raise ErrorCaja("Solo quien registró el retiro adjunta su comprobante.")
    if retiro.comprobante != RetiroCaja.PENDIENTE:
        raise ErrorCaja("El retiro ya tiene comprobante o se declaró sin él.")
    return adjuntar_preparado(retiro, usuario, comprobantes.preparar(contenido), request)


def sin_comprobante(retiro, usuario, motivo, request=None):
    motivo = " ".join(str(motivo or "").split())[:300]
    if not motivo:
        raise ErrorCaja("Escribe por qué no hay comprobante.")
    if retiro.registrado_por_id != usuario.pk:
        raise ErrorCaja("Solo quien registró el retiro lo declara sin comprobante.")
    with transaction.atomic():
        hechos = RetiroCaja.objects.filter(pk=retiro.pk, comprobante=RetiroCaja.PENDIENTE).update(comprobante=RetiroCaja.SIN_COMPROBANTE, motivo_sin_comprobante=motivo)
        if hechos != 1:
            raise ErrorCaja("El retiro ya tiene comprobante o se declaró sin él.")
        registrar("retiro_sin_comprobante", usuario=usuario, objeto=retiro, datos={"folio": str(retiro), "importe": retiro.importe, "motivo": motivo}, request=request)


class RevisionPropia(ErrorCaja):
    pass


def revisar(retiro, usuario, resultado, nota="", request=None):
    if resultado not in (RetiroCaja.REVISADO, RetiroCaja.OBSERVADO):
        raise ErrorCaja("Elige si el retiro queda revisado u observado.")
    nota = " ".join(str(nota or "").split())[:300]
    if resultado == RetiroCaja.OBSERVADO and not nota:
        raise ErrorCaja("Escribe la observación.")
    if retiro.registrado_por_id == usuario.pk:
        registrar("revision_propia_denegada", usuario=usuario, objeto=retiro, datos={"folio": str(retiro)}, request=request)
        raise RevisionPropia("Nadie revisa un retiro propio.")
    if not usuario.tiene_permiso("revisar_retiros"):
        raise ErrorCaja("No tienes permiso para revisar retiros.")
    with transaction.atomic():
        hechos = RetiroCaja.objects.filter(pk=retiro.pk, revision=RetiroCaja.POR_REVISAR).exclude(registrado_por=usuario).update(
            revision=resultado, revisado_por=usuario, revisado_en=timezone.now(), nota_revision=nota
        )
        if hechos != 1:
            raise ErrorCaja("El retiro ya estaba revisado.")
        registrar("retiro_revisado", usuario=usuario, objeto=retiro, datos={"folio": str(retiro), "resultado": resultado, "nota": nota, "registro": str(retiro.registrado_por)}, request=request)


def revertir(retiro, motivo, ejecutor, turno, autorizador=None, solicitud=None, request=None, piezas=None):
    motivo = " ".join(str(motivo or "").split())[:300]
    if not motivo:
        raise ErrorCaja("Escribe el motivo de la reversión.")
    if turno is None or not recibe_movimientos(turno):
        raise ErrorCaja("Para regresar el efectivo se necesita un turno de caja abierto de quien lo recibe.")
    piezas = validar_piezas(piezas, retiro.importe) if piezas or control_piezas.activo() else {}
    with transaction.atomic():
        if ReversionRetiro.objects.filter(retiro=retiro).exists():
            raise ErrorCaja("El retiro ya fue revertido.")
        reversion = ReversionRetiro.objects.create(retiro=retiro, turno=turno, motivo=motivo, ejecutada_por=ejecutor, autorizada_por=autorizador, solicitud=solicitud)
        control_piezas.registrar(turno, turno.usuario, MovimientoPiezas.REVERSION_RETIRO, piezas, 1, retiro=retiro)
        registrar(
            "retiro_revertido",
            usuario=ejecutor,
            objeto=retiro,
            datos={"folio": str(retiro), "importe": retiro.importe, "motivo": motivo, "turno_regreso": turno.pk, "autorizo": str(autorizador) if autorizador else None, "piezas": piezas},
            request=request,
        )
    return reversion


def visibles(usuario):
    consulta = RetiroCaja.objects.select_related("caja", "motivo", "registrado_por", "revisado_por", "turno")
    if usuario.tiene_permiso("revisar_retiros"):
        return consulta
    return consulta.filter(registrado_por=usuario)


def puede_ver(usuario, retiro):
    return retiro.registrado_por_id == usuario.pk or usuario.tiene_permiso("revisar_retiros")


def avisos(quien_ve=None):
    limites = topes()
    ahora = timezone.now()
    cerca = []
    propia = turno_abierto(quien_ve) if quien_ve is not None else None
    for caja in Caja.objects.filter(activa=True):
        usado = uso(caja)
        if limites["importe_periodo"] and usado["importe"] * 100 >= limites["importe_periodo"] * AVISO_TOPE:
            cerca.append({"caja": caja, "tope": "importe", "usado": usado["importe"], "limite": limites["importe_periodo"]})
        if limites["cantidad_periodo"] and usado["cantidad"] * 100 >= limites["cantidad_periodo"] * AVISO_TOPE:
            cerca.append({"caja": caja, "tope": "cantidad", "usado": usado["cantidad"], "limite": limites["cantidad_periodo"]})
    sobre_maximo = []
    if limites["efectivo_maximo"]:
        for turno in Turno.objects.filter(estado=Turno.ABIERTO).select_related("caja", "usuario"):
            if propia is not None and turno.pk == propia.pk:
                continue
            if turno.fondo_inicial + neto_de(turno) > limites["efectivo_maximo"]:
                sobre_maximo.append(turno)
    viejos = ahora - timedelta(days=parametro("dias_retiro_sin_revisar"))
    return {
        "cerca_del_tope": cerca,
        "sin_comprobante": RetiroCaja.objects.filter(comprobante=RetiroCaja.SIN_COMPROBANTE, revision=RetiroCaja.POR_REVISAR).select_related("caja", "registrado_por", "motivo"),
        "por_revisar_viejos": RetiroCaja.objects.filter(revision=RetiroCaja.POR_REVISAR, creado__lt=viejos).select_related("caja", "registrado_por", "motivo"),
        "sobre_maximo": sobre_maximo,
    }
