import hashlib
import hmac
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from auditoria.servicios import registrar
from banco.models import MovimientoBancario
from caja import piezas as control_piezas
from caja.models import MovimientoPiezas, Turno
from caja.servicios import neto_de, personas_con_efectivo, recibe_movimientos
from configuracion.models import Negocio, parametro
from nucleo import reparto
from configuracion.moneda import formatear
from titulares.models import Titular

from .models import Aplicacion, CancelacionCargo, Cargo, Pago, Recibo, ReversionPago, SerieRecibo, cerrado_hasta, dia_contable

ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


class ErrorLibro(ValueError):
    pass


class PagoDuplicado(ErrorLibro):
    def __init__(self, pago):
        super().__init__("Ese pago ya se registró.")
        self.pago = pago


def _suma(modelo, filtro):
    return Coalesce(
        Subquery(modelo.objects.filter(**filtro).order_by().values(list(filtro)[0]).annotate(total=Sum("importe")).values("total"), output_field=IntegerField()),
        Value(0),
    )


def con_saldo(consulta):
    aplicado = Coalesce(
        Subquery(
            Aplicacion.objects.filter(cargo=OuterRef("pk"), pago__reversion__isnull=True).order_by().values("cargo").annotate(total=Sum("importe")).values("total"),
            output_field=IntegerField(),
        ),
        Value(0),
    )
    cancelado = _suma(CancelacionCargo, {"cargo": OuterRef("pk")})
    return consulta.annotate(aplicado=aplicado, cancelado=cancelado).annotate(saldo=F("importe_final") - F("aplicado") - F("cancelado"))


def con_remanente(consulta):
    aplicado = Coalesce(
        Subquery(Aplicacion.objects.filter(pago=OuterRef("pk")).order_by().values("pago").annotate(total=Sum("importe")).values("total"), output_field=IntegerField()),
        Value(0),
    )
    return consulta.annotate(aplicado=aplicado).annotate(remanente=F("importe") - F("aplicado"))


def saldo_de(cargo):
    return con_saldo(Cargo.objects.filter(pk=cargo.pk)).values_list("saldo", flat=True).get()


def remanente_de(pago):
    if ReversionPago.objects.filter(pago=pago).exists():
        return 0
    return con_remanente(Pago.objects.filter(pk=pago.pk)).values_list("remanente", flat=True).get()


def estado_de(cargo):
    if cargo.saldo == 0 and cargo.cancelado > 0 and cargo.aplicado == 0:
        return "cancelado"
    if cargo.saldo == 0:
        return "pagado"
    if cargo.aplicado > 0 or cargo.cancelado > 0:
        return "parcial"
    return "pendiente"


def miembros_de(titular):
    if titular.familia_id:
        return list(titular.familia.miembros.values_list("pk", flat=True))
    return [titular.pk]


def orden_reparto():
    texto = parametro("orden_reparto")
    orden = tuple(p.strip() for p in texto.split(",") if p.strip())
    if not orden or any(c not in reparto.CRITERIOS for c in orden) or len(set(orden)) != len(orden):
        return reparto.ORDEN_POR_DEFECTO
    return orden


def validar_orden(texto):
    orden = tuple(p.strip() for p in str(texto).split(",") if p.strip())
    if not orden or any(c not in reparto.CRITERIOS for c in orden) or len(set(orden)) != len(orden):
        raise ErrorLibro(f"El orden debe combinar sin repetir: {', '.join(reparto.CRITERIOS)}.")
    return ",".join(orden)


def _aplicar(pago, cargo, importe):
    if importe <= 0:
        raise ErrorLibro("aplicación sin importe")
    if importe > saldo_de(cargo):
        raise ErrorLibro("la aplicación excede el saldo del cargo")
    if importe > remanente_de(pago):
        raise ErrorLibro("la aplicación excede lo disponible del pago")
    return Aplicacion.objects.create(pago=pago, cargo=cargo, importe=importe)


def aplicar_saldo_a_favor(cargo, request=None):
    titular = Titular.objects.select_related("familia").get(pk=cargo.titular_id)
    pendiente = saldo_de(cargo)
    aplicaciones = []
    if pendiente <= 0:
        return aplicaciones
    pagos = con_remanente(Pago.objects.filter(titular__in=miembros_de(titular), reversion__isnull=True)).filter(remanente__gt=0).order_by("fecha", "id")
    for pago in pagos:
        if pendiente <= 0:
            break
        importe = min(pago.remanente, pendiente)
        aplicaciones.append(_aplicar(pago, cargo, importe))
        pendiente -= importe
    if aplicaciones:
        registrar(
            "saldo_a_favor_aplicado",
            objeto=cargo,
            datos={"cargo": str(cargo), "aplicaciones": [{"pago": a.pago_id, "importe": a.importe} for a in aplicaciones]},
            request=request,
        )
    return aplicaciones


def crear_cargo(titular, concepto, importe_original, vencimiento, origen, periodo="", descripcion="", beca=None, descuento=0, cargo_base=None, fecha_recargo=None, cantidad=1, usuario=None, request=None):
    if importe_original < 0 or descuento < 0 or descuento > importe_original:
        raise ErrorLibro("importe de cargo inválido")
    try:
        with transaction.atomic():
            cargo = Cargo.objects.create(
                titular=titular,
                concepto=concepto,
                periodo=periodo,
                descripcion=descripcion[:200],
                cantidad=cantidad,
                importe_original=importe_original,
                descuento=descuento,
                beca=beca,
                importe_final=importe_original - descuento,
                vencimiento=vencimiento,
                origen=origen,
                cargo_base=cargo_base,
                fecha_recargo=fecha_recargo,
                creado_por=usuario,
            )
    except IntegrityError:
        return None
    registrar(
        "cargo_generado" if origen != Cargo.MANUAL else "cargo_manual",
        usuario=usuario,
        objeto=cargo,
        datos={
            "cargo": str(cargo),
            "origen": origen,
            "importe_original": importe_original,
            "descuento": descuento,
            "importe_final": cargo.importe_final,
            "vencimiento": vencimiento,
            "beca": beca.pk if beca else None,
            "cargo_base": cargo_base.pk if cargo_base else None,
        },
        request=request,
    )
    aplicar_saldo_a_favor(cargo, request=request)
    return cargo


def codigo_recibo(serie, folio, importe, fecha, titular_id):
    mensaje = f"recibo-v1|{serie}|{folio}|{importe}|{fecha.isoformat()}|{titular_id}".encode("utf-8")
    numero = int.from_bytes(hmac.new(settings.CLAVE_AUDITORIA, mensaje, hashlib.sha256).digest()[:10], "big")
    letras = []
    for _ in range(10):
        numero, resto = divmod(numero, len(ALFABETO))
        letras.append(ALFABETO[resto])
    texto = "".join(letras)
    return f"{texto[:5]}-{texto[5:]}"


def fecha_local(momento):
    negocio = Negocio.actual()
    zona = ZoneInfo(negocio.zona_horaria) if negocio else timezone.get_default_timezone()
    return timezone.localtime(momento, zona).date()


def fecha_contable(momento):
    ahora = timezone.now()
    if momento is None:
        return ahora, None
    limite = cerrado_hasta()
    if limite is not None and dia_contable(momento) <= limite:
        return ahora, dia_contable(momento)
    return momento, None


def emitir_recibo(pago, serie):
    SerieRecibo.objects.get_or_create(nombre=serie)
    SerieRecibo.objects.filter(nombre=serie).update(siguiente=F("siguiente") + 1)
    folio = SerieRecibo.objects.filter(nombre=serie).values_list("siguiente", flat=True).get() - 1
    codigo = codigo_recibo(serie, folio, pago.importe, fecha_local(pago.fecha), pago.titular_id)
    return Recibo.objects.create(pago=pago, serie=serie, folio=folio, codigo=codigo)


def recibo_valido(recibo):
    esperado = codigo_recibo(recibo.serie, recibo.folio, recibo.pago.importe, fecha_local(recibo.pago.fecha), recibo.pago.titular_id)
    return hmac.compare_digest(esperado, recibo.codigo)


def pendientes_de(titulares_ids):
    cargos = con_saldo(Cargo.objects.filter(titular__in=titulares_ids).select_related("concepto")).filter(saldo__gt=0)
    return [
        reparto.Pendiente(c.pk, c.titular_id, c.saldo, c.vencimiento, c.origen == Cargo.RECARGO, c.concepto.prioridad)
        for c in cargos
    ]


def proponer_reparto(titular, importe):
    miembros = miembros_de(titular)
    return reparto.repartir(importe, pendientes_de(miembros), titular.pk, miembros, orden_reparto())


def _piezas_de_cobro(importe, medio, piezas):
    if not piezas:
        return None
    if medio != Pago.EFECTIVO:
        raise ErrorLibro("Solo un pago en efectivo lleva piezas.")
    try:
        return control_piezas.validar_cobro(importe, piezas.get("recibidas"), piezas.get("cambio"))
    except control_piezas.ErrorPiezas as error:
        raise ErrorLibro(str(error))


def registrar_pago(titular, importe, medio, usuario, turno=None, ficha=None, request=None, solicitud=None, serie=None, fecha=None, movimiento=None, piezas=None):
    if not isinstance(importe, int) or isinstance(importe, bool) or importe <= 0:
        raise ErrorLibro("El importe debe ser mayor que cero.")
    piezas = _piezas_de_cobro(importe, medio, piezas)
    with transaction.atomic():
        if ficha:
            existente = Pago.objects.filter(ficha=ficha).first()
            if existente is not None:
                raise PagoDuplicado(existente)
        if medio == Pago.EFECTIVO:
            if turno is None or not Turno.objects.filter(pk=turno.pk, estado=Turno.ABIERTO).exists():
                raise ErrorLibro("Se necesita un turno de caja abierto.")
            if not recibe_movimientos(turno):
                raise ErrorLibro("El turno ya está en arqueo: no recibe cobros nuevos.")
        fecha, fecha_banco = fecha_contable(fecha)
        partes, resto = proponer_reparto(titular, importe)
        pago = Pago.objects.create(
            titular=titular, importe=importe, medio=medio, turno=turno, ficha=ficha or None, registrado_por=usuario,
            solicitud=solicitud, fecha=fecha, fecha_banco=fecha_banco, movimiento=movimiento,
        )
        cargos = {c.pk: c for c in Cargo.objects.filter(pk__in=[p.cargo for p in partes])}
        for parte in partes:
            _aplicar(pago, cargos[parte.cargo], parte.importe)
        recibo = emitir_recibo(pago, serie or (turno.caja.serie_recibos if turno is not None else "A"))
        if piezas:
            control_piezas.registrar(turno, usuario, MovimientoPiezas.RECIBIDO, piezas["recibidas"], 1, pago=pago)
            control_piezas.registrar(turno, usuario, MovimientoPiezas.CAMBIO, piezas["cambio"], -1, pago=pago)
        registrar(
            "pago_registrado",
            usuario=usuario,
            objeto=pago,
            titular=titular.pk,
            datos={
                "importe": importe,
                "importe_texto": formatear(importe),
                "medio": medio,
                "recibo": str(recibo),
                "turno": turno.pk if turno else None,
                "movimiento": movimiento.pk if movimiento is not None else None,
                "aplicaciones": [{"cargo": p.cargo, "titular": p.titular, "importe": p.importe} for p in partes],
                "saldo_a_favor": resto,
                "piezas": piezas or {},
            },
            request=request,
        )
        for parte in partes:
            if parte.titular != titular.pk:
                registrar("pago_aplicado_a_familiar", usuario=usuario, objeto=pago, titular=parte.titular, datos={"cargo": parte.cargo, "importe": parte.importe, "pagado_con": titular.matricula}, request=request)
    return pago


def cancelar_cargo(cargo, importe, tipo, motivo, ejecutor, autorizador=None, solicitud=None, request=None):
    with transaction.atomic():
        saldo = saldo_de(cargo)
        if importe <= 0 or importe > saldo:
            raise ErrorLibro(f"El importe a cancelar debe ser mayor que cero y no pasar del saldo ({formatear(saldo)}).")
        if tipo == CancelacionCargo.CONDONACION and cargo.origen != Cargo.RECARGO:
            raise ErrorLibro("Solo se condonan recargos.")
        asiento = CancelacionCargo.objects.create(cargo=cargo, tipo=tipo, importe=importe, motivo=motivo[:300], ejecutada_por=ejecutor, autorizada_por=autorizador, solicitud=solicitud)
        registrar(
            "cargo_cancelado" if tipo == CancelacionCargo.CANCELACION else "recargo_condonado",
            usuario=ejecutor,
            objeto=cargo,
            datos={"cargo": str(cargo), "importe": importe, "motivo": motivo, "autorizado_por": str(autorizador) if autorizador else None, "cambios": {"saldo": [saldo, saldo - importe]}},
            request=request,
        )
    return asiento


def revertir_pago(pago, motivo, ejecutor, turno=None, autorizador=None, solicitud=None, request=None, piezas=None):
    if piezas:
        try:
            piezas = control_piezas.exigir_total(piezas, pago.importe, "Las piezas devueltas deben sumar exactamente el importe del pago.")
        except control_piezas.ErrorPiezas as error:
            raise ErrorLibro(str(error))
    with transaction.atomic():
        if ReversionPago.objects.filter(pago=pago).exists():
            raise ErrorLibro("El pago ya fue revertido.")
        if pago.medio == Pago.EFECTIVO:
            if turno is None or not Turno.objects.filter(pk=turno.pk, estado=Turno.ABIERTO).exists():
                raise ErrorLibro("Para devolver efectivo se necesita un turno de caja abierto de quien lo devuelve.")
            if not recibe_movimientos(turno):
                raise ErrorLibro("El turno de quien devuelve ya está en arqueo: no admite devoluciones.")
            if efectivo_devolvible(turno) < pago.importe:
                raise ErrorLibro(
                    f"El turno de {turno.usuario} no tiene suficiente efectivo cobrado para devolver {formatear(pago.importe)}. "
                    f"{quien_tiene_efectivo(pago)}"
                )
        aplicaciones = list(pago.aplicaciones.values("cargo", "importe"))
        if pago.movimiento_id:
            MovimientoBancario.objects.filter(pk=pago.movimiento_id, pago=pago).update(estado=MovimientoBancario.POR_IDENTIFICAR, pago=None, resuelto_por=None, resuelto_en=None)
        reversion = ReversionPago.objects.create(pago=pago, motivo=motivo[:300], turno=turno if pago.medio == Pago.EFECTIVO else None, ejecutada_por=ejecutor, autorizada_por=autorizador, solicitud=solicitud)
        if piezas and pago.medio == Pago.EFECTIVO:
            control_piezas.registrar(turno, turno.usuario, MovimientoPiezas.DEVOLUCION, piezas, -1, reversion=reversion)
        recibo = getattr(pago, "recibo", None)
        registrar(
            "pago_revertido",
            usuario=ejecutor,
            objeto=pago,
            titular=pago.titular_id,
            datos={"importe": pago.importe, "recibo": str(recibo) if recibo else None, "motivo": motivo, "aplicaciones_anuladas": aplicaciones, "turno_devolucion": turno.pk if turno else None},
            request=request,
        )
    return reversion


def efectivo_devolvible(turno):
    return neto_de(turno)


def quien_tiene_efectivo(pago):
    tenedores = [str(f["usuario"]) if f["turno_abierto"] else f"{f['usuario']} ({formatear(f['custodia'])})" for f in personas_con_efectivo() if f["turno_abierto"] or f["custodia"] > 0]
    cobro = f"Lo cobró {pago.registrado_por} en {pago.turno.caja}." if pago.turno_id else ""
    hoy = f" Hoy tienen efectivo: {', '.join(tenedores)}." if tenedores else " Hoy nadie tiene efectivo en custodia."
    return (cobro + hoy + " Quien lo tenga debe abrir su turno para devolverlo.").strip()


def validar_importe_pago(importe):
    if importe is None or importe <= 0:
        raise ErrorLibro("El importe debe ser mayor que cero.")
    return importe > parametro("tope_pago_individual")
