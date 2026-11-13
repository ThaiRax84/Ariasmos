from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Max, Min, Sum
from django.utils import timezone

from auditoria.servicios import registrar
from cobros.models import Pago, Recibo, ReversionPago
from configuracion.models import parametro
from cuentas.models import Usuario
from configuracion.moneda import formatear

from . import piezas as control_piezas
from .models import Arqueo, ConteoArqueo, Denominacion, MovimientoPiezas, RetiroCaja, ReversionRetiro, Traslado, Turno


class ErrorCaja(ValueError):
    pass


class NotaRequerida(ErrorCaja):
    pass


def _suma(consulta, campo="importe"):
    return consulta.aggregate(total=Sum(campo))["total"] or 0


def turno_abierto(usuario):
    return Turno.objects.filter(usuario=usuario, estado=Turno.ABIERTO).select_related("caja").first()


def abrir_turno(usuario, caja, fondo_inicial, request=None, piezas=None):
    if piezas is not None:
        try:
            piezas = control_piezas.validar(piezas)
        except control_piezas.ErrorPiezas as error:
            raise ErrorCaja(str(error))
        fondo_inicial = control_piezas.total(piezas)
    if fondo_inicial < 0:
        raise ErrorCaja("El fondo inicial no puede ser negativo.")
    if not caja.activa:
        raise ErrorCaja("La caja no está activa.")
    try:
        with transaction.atomic():
            turno = Turno.objects.create(usuario=usuario, caja=caja, fondo_inicial=fondo_inicial)
            if piezas:
                control_piezas.registrar(turno, usuario, MovimientoPiezas.APERTURA, piezas, 1)
    except IntegrityError:
        raise ErrorCaja("Ya tienes un turno abierto o la caja está ocupada por otra persona.")
    registrar("turno_abierto", usuario=usuario, objeto=turno, datos={"caja": str(caja), "fondo_inicial": fondo_inicial, "piezas": piezas or {}}, request=request)
    return turno


def recibe_movimientos(turno):
    return turno is not None and Turno.objects.filter(pk=turno.pk, estado=Turno.ABIERTO).exists() and not ConteoArqueo.objects.filter(turno_id=turno.pk).exists()


def devoluciones_articulos():
    from inventario.models import Devolucion

    return Devolucion.objects.filter(medio=Devolucion.EFECTIVO)


def neto_de(turno):
    cobrado = _suma(Pago.objects.filter(turno=turno, medio=Pago.EFECTIVO))
    devuelto = _suma(ReversionPago.objects.filter(turno=turno), "pago__importe")
    retirado = _suma(RetiroCaja.objects.filter(turno=turno))
    regresado = _suma(ReversionRetiro.objects.filter(turno=turno), "retiro__importe")
    articulos = _suma(devoluciones_articulos().filter(turno=turno), "importe_dinero")
    return cobrado - devuelto - retirado + regresado - articulos


def esperado_de(turno):
    return turno.fondo_inicial + neto_de(turno)


def contar(conteo):
    validas = {d.valor for d in Denominacion.objects.filter(activa=True)}
    total = 0
    limpio = {}
    for valor, cantidad in conteo.items():
        valor = int(valor)
        if valor not in validas:
            raise ErrorCaja("Denominación no válida.")
        if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad < 0 or cantidad > 100000:
            raise ErrorCaja("Cantidad no válida.")
        if cantidad:
            limpio[str(valor)] = cantidad
            total += valor * cantidad
    return total, limpio


def conteo_pendiente(turno):
    return ConteoArqueo.objects.filter(turno=turno, numero=1).first()


def comprobantes_pendientes(turno):
    return RetiroCaja.objects.filter(turno=turno, comprobante=RetiroCaja.PENDIENTE, reversion__isnull=True)


def _cerrable(turno, usuario):
    if turno.usuario_id != usuario.pk:
        raise ErrorCaja("Solo quien abrió el turno puede cerrarlo.")
    fresco = Turno.objects.filter(pk=turno.pk, usuario=usuario, estado=Turno.ABIERTO).first()
    if fresco is None:
        raise ErrorCaja("El turno ya estaba cerrado.")
    return fresco


def _cerrar(turno, usuario, final, nota, primero, request):
    esperado = esperado_de(turno)
    diferencia = final.contado - esperado
    supera = abs(diferencia) > parametro("umbral_diferencia_arqueo")
    esperadas = control_piezas.existencias(turno) if MovimientoPiezas.objects.filter(turno=turno).exists() else {}
    cerrados = Turno.objects.filter(pk=turno.pk, usuario=usuario, estado=Turno.ABIERTO).update(estado=Turno.CERRADO, cerrado_en=timezone.now())
    if cerrados != 1:
        raise ErrorCaja("El turno ya estaba cerrado.")
    arqueo = Arqueo.objects.create(
        turno=turno, conteo=final.conteo, contado=final.contado, esperado=esperado, diferencia=diferencia, nota=nota.strip()[:500], supera_umbral=supera,
        primer_conteo=primero.conteo, primer_contado=primero.contado, con_reconteo=final.numero == 2, esperado_piezas=esperadas,
    )
    registrar(
        "turno_cerrado",
        usuario=usuario,
        objeto=turno,
        datos={
            "caja": str(turno.caja), "contado": final.contado, "esperado": esperado, "diferencia": diferencia, "supera_umbral": supera, "nota": arqueo.nota,
            "primer_conteo": primero.conteo, "primer_contado": primero.contado, "reconteo": final.conteo if final.numero == 2 else None, "esperado_piezas": esperadas,
        },
        request=request,
    )
    if supera:
        registrar("diferencia_de_arqueo", usuario=usuario, objeto=turno, datos={"diferencia": diferencia, "diferencia_texto": formatear(diferencia), "nota": arqueo.nota}, request=request)
    from cortes.servicios import crear_diario

    crear_diario(turno, arqueo, request)
    return arqueo


@dataclass
class ResultadoConteo:
    arqueo: Arqueo = None

    @property
    def cerrado(self):
        return self.arqueo is not None


def primer_conteo(turno, usuario, conteo, nota="", request=None):
    contado, limpio = contar(conteo)
    with transaction.atomic():
        turno = _cerrable(turno, usuario)
        if comprobantes_pendientes(turno).exists():
            raise ErrorCaja("Hay retiros con comprobante pendiente: adjúntalos o declara cada uno sin comprobante antes de cerrar el turno.")
        if ConteoArqueo.objects.filter(turno=turno).exists():
            raise ErrorCaja("El primer conteo ya se guardó y no se puede cambiar.")
        primero = ConteoArqueo.objects.create(turno=turno, numero=1, conteo=limpio, contado=contado, nota=nota.strip()[:500])
        coincide = contado == esperado_de(turno)
        registrar("primer_conteo", usuario=usuario, objeto=turno, datos={"caja": str(turno.caja), "conteo": limpio, "contado": contado, "coincide": coincide}, request=request)
        if not coincide:
            return ResultadoConteo()
        return ResultadoConteo(_cerrar(turno, usuario, primero, nota, primero, request))


def reconteo(turno, usuario, conteo, nota, request=None):
    if not (nota or "").strip():
        raise NotaRequerida("Escribe una nota que explique la diferencia antes de recontar.")
    contado, limpio = contar(conteo)
    with transaction.atomic():
        turno = _cerrable(turno, usuario)
        primero = conteo_pendiente(turno)
        if primero is None:
            raise ErrorCaja("Primero captura el conteo del turno.")
        if ConteoArqueo.objects.filter(turno=turno, numero=2).exists():
            raise ErrorCaja("El reconteo ya se hizo.")
        segundo = ConteoArqueo.objects.create(turno=turno, numero=2, conteo=limpio, contado=contado, nota=nota.strip()[:500])
        registrar("reconteo", usuario=usuario, objeto=turno, datos={"caja": str(turno.caja), "conteo": limpio, "contado": contado}, request=request)
        return _cerrar(turno, usuario, segundo, nota, primero, request)


def cerrar_con_primer_conteo(turno, usuario, nota, request=None):
    if not (nota or "").strip():
        raise NotaRequerida("Escribe una nota que explique la diferencia para cerrar con el primer conteo.")
    with transaction.atomic():
        turno = _cerrable(turno, usuario)
        primero = conteo_pendiente(turno)
        if primero is None:
            raise ErrorCaja("Primero captura el conteo del turno.")
        return _cerrar(turno, usuario, primero, nota, primero, request)


def cerrar_turno(turno, usuario, conteo, nota="", request=None):
    contado, limpio = contar(conteo)
    with transaction.atomic():
        turno = _cerrable(turno, usuario)
        if comprobantes_pendientes(turno).exists():
            raise ErrorCaja("Hay retiros con comprobante pendiente: adjúntalos o declara cada uno sin comprobante antes de cerrar el turno.")
        if ConteoArqueo.objects.filter(turno=turno).exists():
            raise ErrorCaja("El primer conteo ya se guardó y no se puede cambiar.")
        primero = ConteoArqueo.objects.create(turno=turno, numero=1, conteo=limpio, contado=contado, nota=nota.strip()[:500])
        return _cerrar(turno, usuario, primero, nota, primero, request)


def custodia(usuario):
    cobrado = _suma(Pago.objects.filter(turno__usuario=usuario, medio=Pago.EFECTIVO))
    devuelto = _suma(ReversionPago.objects.filter(turno__usuario=usuario), "pago__importe")
    retirado = _suma(RetiroCaja.objects.filter(turno__usuario=usuario))
    regresado = _suma(ReversionRetiro.objects.filter(turno__usuario=usuario), "retiro__importe")
    articulos = _suma(devoluciones_articulos().filter(turno__usuario=usuario), "importe_dinero")
    enviado = _suma(Traslado.objects.filter(origen=usuario, tipo=Traslado.ENTREGA, estado=Traslado.CONFIRMADO))
    depositado = _suma(Traslado.objects.filter(origen=usuario, tipo=Traslado.DEPOSITO))
    recibido = _suma(Traslado.objects.filter(destino=usuario, tipo=Traslado.ENTREGA, estado=Traslado.CONFIRMADO))
    return cobrado - devuelto - retirado + regresado - articulos - enviado - depositado + recibido


def disponible(usuario):
    reservado = _suma(Traslado.objects.filter(origen=usuario, tipo=Traslado.ENTREGA, estado=Traslado.PENDIENTE))
    return custodia(usuario) - reservado


def neto_turno_abierto(usuario):
    turno = turno_abierto(usuario)
    if turno is None:
        return 0
    return neto_de(turno)


def disponible_para_trasladar(usuario):
    return disponible(usuario) - neto_turno_abierto(usuario)


def _validar_traslado(usuario, importe):
    if importe is None or importe <= 0:
        raise ErrorCaja("El importe debe ser mayor que cero.")
    libre = disponible_para_trasladar(usuario)
    if importe > libre:
        raise ErrorCaja(f"No puedes trasladar más de lo que tienes de turnos cerrados ({formatear(max(libre, 0))}).")


def _piezas_traslado(piezas, importe):
    if piezas is None:
        return {}
    try:
        return control_piezas.exigir_total(piezas, importe, "Las piezas deben sumar exactamente el importe.")
    except control_piezas.ErrorPiezas as error:
        raise ErrorCaja(str(error))


def entregar(origen, destino, importe, nota="", request=None, piezas=None):
    if destino.pk == origen.pk:
        raise ErrorCaja("No puedes entregarte efectivo a ti mismo.")
    if not destino.activo or not destino.tiene_permiso("recibir_efectivo"):
        raise ErrorCaja("Esa persona no puede recibir efectivo.")
    limpio = _piezas_traslado(piezas, importe)
    with transaction.atomic():
        _validar_traslado(origen, importe)
        traslado = Traslado.objects.create(tipo=Traslado.ENTREGA, origen=origen, destino=destino, importe=importe, estado=Traslado.PENDIENTE, nota=nota[:300])
        control_piezas.registrar(None, origen, MovimientoPiezas.TRASLADO, limpio, -1, traslado=traslado)
        registrar("entrega_enviada", usuario=origen, objeto=traslado, datos={"para": str(destino), "importe": importe, "piezas": limpio}, request=request)
    return traslado


def depositar(origen, importe, cuenta, fecha, referencia, nota="", request=None, piezas=None):
    limpio = _piezas_traslado(piezas, importe)
    with transaction.atomic():
        _validar_traslado(origen, importe)
        traslado = Traslado.objects.create(
            tipo=Traslado.DEPOSITO, origen=origen, importe=importe, estado=Traslado.POR_CONCILIAR,
            cuenta_bancaria=cuenta, fecha_deposito=fecha, referencia=referencia[:60], nota=nota[:300],
        )
        control_piezas.registrar(None, origen, MovimientoPiezas.TRASLADO, limpio, -1, traslado=traslado)
        registrar("deposito_registrado", usuario=origen, objeto=traslado, datos={"importe": importe, "cuenta": str(cuenta), "fecha": fecha, "referencia": referencia, "piezas": limpio}, request=request)
    return traslado


def confirmar_entrega(traslado, usuario, importe, request=None):
    if traslado.destino_id != usuario.pk or traslado.origen_id == usuario.pk:
        raise ErrorCaja("Solo quien recibe puede confirmar la entrega.")
    if importe != traslado.importe:
        registrar("entrega_importe_distinto", usuario=usuario, objeto=traslado, datos={"declarado": traslado.importe, "recibido": importe}, request=request)
        raise ErrorCaja("El importe no coincide con lo enviado. Si recibiste otra cantidad, rechaza la entrega.")
    with transaction.atomic():
        hechos = Traslado.objects.filter(pk=traslado.pk, estado=Traslado.PENDIENTE, destino=usuario).update(estado=Traslado.CONFIRMADO, resuelto_en=timezone.now())
        if hechos != 1:
            raise ErrorCaja("La entrega ya no está pendiente.")
        registrar("entrega_confirmada", usuario=usuario, objeto=traslado, datos={"de": str(traslado.origen), "importe": traslado.importe}, request=request)


def rechazar_entrega(traslado, usuario, nota, request=None):
    if traslado.destino_id != usuario.pk:
        raise ErrorCaja("Solo quien recibe puede rechazar la entrega.")
    with transaction.atomic():
        hechos = Traslado.objects.filter(pk=traslado.pk, estado=Traslado.PENDIENTE, destino=usuario).update(estado=Traslado.RECHAZADO, resuelto_en=timezone.now())
        if hechos != 1:
            raise ErrorCaja("La entrega ya no está pendiente.")
        registrar("entrega_rechazada", usuario=usuario, objeto=traslado, datos={"de": str(traslado.origen), "importe": traslado.importe, "nota": nota}, request=request)


def personas_con_efectivo(quien_ve=None):
    ids = set(Pago.objects.filter(medio=Pago.EFECTIVO).values_list("turno__usuario", flat=True))
    ids |= set(Traslado.objects.values_list("destino", flat=True))
    ids |= set(Traslado.objects.filter(tipo=Traslado.DEPOSITO).values_list("origen", flat=True))
    ids |= set(RetiroCaja.objects.values_list("registrado_por", flat=True))
    filas = []
    for usuario in Usuario.objects.filter(pk__in=[i for i in ids if i]):
        depositos = Traslado.objects.filter(origen=usuario, tipo=Traslado.DEPOSITO, estado=Traslado.POR_CONCILIAR).select_related("cuenta_bancaria").order_by("creado")
        oculto = quien_ve is not None and usuario.pk == quien_ve.pk and turno_abierto(usuario) is not None
        filas.append(
            {
                "usuario": usuario,
                "custodia": None if oculto else custodia(usuario),
                "disponible": None if oculto else disponible(usuario),
                "desde": None if oculto else efectivo_desde(usuario),
                "depositos": list(depositos),
                "oculto": oculto,
                "turno_abierto": turno_abierto(usuario) is not None,
            }
        )
    return filas


def efectivo_desde(usuario):
    if custodia(usuario) <= 0:
        return None
    ultimo = Traslado.objects.filter(origen=usuario).exclude(estado=Traslado.RECHAZADO).aggregate(m=Max("creado"))["m"]
    pagos = Pago.objects.filter(turno__usuario=usuario, medio=Pago.EFECTIVO)
    if ultimo is not None:
        pagos = pagos.filter(fecha__gt=ultimo)
    primero = pagos.aggregate(m=Min("fecha"))["m"]
    return primero or ultimo


def alertas(quien_ve=None):
    ahora = timezone.now()
    limite = ahora - timedelta(days=parametro("dias_maximos_efectivo_sin_trasladar"))
    sin_trasladar = [f for f in personas_con_efectivo(quien_ve) if not f["oculto"] and f["custodia"] > 0 and f["desde"] is not None and f["desde"] < limite]
    return {
        "depositos_sin_conciliar": Traslado.objects.filter(
            tipo=Traslado.DEPOSITO, estado=Traslado.POR_CONCILIAR, creado__lt=ahora - timedelta(days=parametro("dias_maximos_deposito_sin_conciliar"))
        ).select_related("origen", "cuenta_bancaria").order_by("creado"),
        "sin_trasladar": sin_trasladar,
        "entregas_pendientes": Traslado.objects.filter(tipo=Traslado.ENTREGA, estado=Traslado.PENDIENTE).select_related("origen", "destino"),
        "diferencias": Arqueo.objects.filter(supera_umbral=True, creado__gte=ahora - timedelta(days=parametro("dias_alerta_recibos_cancelados"))).select_related("turno__usuario", "turno__caja"),
        "recibos_cancelados": Recibo.objects.filter(pago__reversion__isnull=False, pago__reversion__creada__gte=ahora - timedelta(days=parametro("dias_alerta_recibos_cancelados"))).select_related("pago__titular", "pago__reversion"),
    }
