from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone

from auditoria.servicios import registrar
from caja.models import Turno
from cobros.models import Pago
from configuracion.models import Negocio, hoy_negocio, parametro

from . import calculo, entrega, salida
from .models import COBRANZA, DIARIO, MAYOR, Corte, DefinicionCorte, Destino, Entrega, ReglaDestino

ESPERA_MAXIMA_MINUTOS = 6 * 60
INTENTOS_MAXIMOS = 12


class ErrorCorte(ValueError):
    pass


def hora_limite():
    texto = str(parametro("hora_limite_corte_diario"))
    try:
        return time.fromisoformat(texto)
    except ValueError:
        return time(18, 0)


def _fin_de_mes(dia):
    siguiente = (dia.replace(day=28) + timedelta(days=4)).replace(day=1)
    return siguiente - timedelta(days=1)


def _mes_siguiente(dia):
    return (dia.replace(day=28) + timedelta(days=4)).replace(day=1)


def _definicion(tipo):
    return DefinicionCorte.objects.filter(tipo=tipo).first()


def crear_entregas(corte):
    definicion = _definicion(corte.tipo)
    if definicion is not None and not definicion.activa:
        return []
    creadas = []
    for regla in ReglaDestino.objects.filter(tipo=corte.tipo, entregar=True, destino__activo=True).select_related("destino"):
        objeto, nueva = Entrega.objects.get_or_create(corte=corte, destino=regla.destino, defaults={"nivel": regla.nivel, "proximo_intento": timezone.now()})
        if nueva:
            creadas.append(objeto)
    return creadas


def _cerrar(corte, cifras, usuario=None, sin_revisar=False):
    huella = salida.huella(cifras)
    hechos = Corte.objects.filter(pk=corte.pk, estado=Corte.BORRADOR).update(
        estado=Corte.CERRADO, cifras=cifras, hash=huella, cerrado_por=usuario, cerrado_en=timezone.now(), sin_revisar=sin_revisar
    )
    if hechos != 1:
        raise ErrorCorte("El corte ya estaba cerrado.")
    corte.refresh_from_db()
    return corte


def crear_diario(turno, arqueo, request=None):
    tiene = Pago.objects.filter(turno=turno, medio=Pago.EFECTIVO).exists() or turno.devoluciones.exists()
    if not tiene:
        return None
    turno.refresh_from_db()
    abierto = calculo.local(turno.abierto_en)
    cerrado = calculo.local(turno.cerrado_en or timezone.now())
    limite = datetime.combine(abierto.date(), hora_limite(), tzinfo=abierto.tzinfo)
    numero = (Corte.objects.filter(tipo=DIARIO, fecha=abierto.date(), caja=turno.caja).aggregate(n=Max("numero"))["n"] or 0) + 1
    cifras = calculo.cifras_diario(turno, arqueo)
    corte = Corte.objects.create(
        tipo=DIARIO, fecha=abierto.date(), periodo_inicio=abierto.date(), periodo_fin=cerrado.date(), turno=turno, caja=turno.caja,
        usuario=turno.usuario, numero=numero, tardio=cerrado > limite, cifras=cifras,
    )
    _cerrar(corte, cifras, turno.usuario)
    crear_entregas(corte)
    registrar("corte_diario", usuario=turno.usuario, objeto=corte, datos={"caja": turno.caja.nombre, "turno": turno.pk, "tardio": corte.tardio, "hash": corte.hash, "total": cifras["totales"]["total_cobrado"]}, request=request)
    return corte


def diarios_pendientes(ahora=None):
    ahora = calculo.local(ahora or timezone.now())
    hoy = ahora.date()
    pasada = ahora.time() >= hora_limite()
    inicio_hoy = datetime.combine(hoy, time.min, tzinfo=ahora.tzinfo)
    pendientes = []
    for turno in Turno.objects.filter(estado=Turno.ABIERTO).select_related("caja", "usuario"):
        anterior = turno.abierto_en < inicio_hoy
        con_cobros = turno.pagos.filter(fecha__gte=inicio_hoy).exists() or turno.devoluciones.exists()
        if anterior or (pasada and con_cobros):
            pendientes.append({"turno": turno, "persona": turno.usuario, "caja": turno.caja, "desde": calculo.local(turno.abierto_en), "dia_anterior": anterior})
    return pendientes


def _primer_mes():
    negocio = Negocio.actual()
    if negocio is None:
        return None
    inicio = negocio.cobro_desde or calculo.local(negocio.creado).date()
    return inicio.replace(day=1)


def generar_mayores(hoy=None):
    hoy = hoy or hoy_negocio()
    mes = _primer_mes()
    if mes is None:
        return []
    dia = max(1, min(28, int(parametro("dia_corte_mayor"))))
    creados = []
    while True:
        generar_el = _mes_siguiente(mes).replace(day=dia)
        if generar_el > hoy:
            break
        if not Corte.objects.filter(tipo=MAYOR, fecha=mes).exists():
            fin = _fin_de_mes(mes)
            try:
                with transaction.atomic():
                    corte = Corte.objects.create(tipo=MAYOR, fecha=mes, periodo_inicio=mes, periodo_fin=fin, automatico=True, cifras=calculo.cifras_mayor(mes, fin, hoy))
                    registrar("corte_mayor_generado", objeto=corte, datos={"periodo": f"{mes:%Y-%m}"})
                creados.append(corte)
            except IntegrityError:
                pass
        mes = _mes_siguiente(mes)
    return creados


def recalcular(corte):
    if corte.estado != Corte.BORRADOR or corte.tipo != MAYOR:
        return corte
    cifras = calculo.cifras_mayor(corte.periodo_inicio, corte.periodo_fin, hoy_negocio())
    Corte.objects.filter(pk=corte.pk).update(cifras=cifras)
    corte.refresh_from_db()
    return corte


def cerrar_mayor(corte, usuario=None, sin_revisar=False, request=None, hoy=None):
    hoy = hoy or hoy_negocio()
    if corte.tipo != MAYOR:
        raise ErrorCorte("Solo el corte mayor se cierra así.")
    if corte.periodo_fin >= hoy:
        raise ErrorCorte("El mes todavía no termina.")
    with transaction.atomic():
        fresco = Corte.objects.get(pk=corte.pk)
        if fresco.estado != Corte.BORRADOR:
            raise ErrorCorte("El corte ya estaba cerrado.")
        if Corte.objects.filter(tipo=MAYOR, fecha__lt=fresco.fecha, estado=Corte.BORRADOR).exists():
            raise ErrorCorte("Primero hay que cerrar el corte del mes anterior.")
        cifras = calculo.cifras_mayor(fresco.periodo_inicio, fresco.periodo_fin, hoy)
        cerrado = _cerrar(fresco, cifras, usuario, sin_revisar)
        Negocio.objects.filter(pk=1).filter(Q(periodo_cerrado_hasta__isnull=True) | Q(periodo_cerrado_hasta__lt=cerrado.periodo_fin)).update(periodo_cerrado_hasta=cerrado.periodo_fin)
        crear_entregas(cerrado)
        registrar(
            "corte_mayor_cerrado",
            usuario=usuario,
            objeto=cerrado,
            datos={"periodo": f"{cerrado.fecha:%Y-%m}", "sin_revisar": sin_revisar, "hash": cerrado.hash, "periodo_cerrado_hasta": cerrado.periodo_fin.isoformat()},
            request=request,
        )
    return cerrado


def cerrar_vencidos(hoy=None):
    hoy = hoy or hoy_negocio()
    plazo = int(parametro("dias_plazo_corte_mayor"))
    dia = max(1, min(28, int(parametro("dia_corte_mayor"))))
    cerrados = []
    for corte in Corte.objects.filter(tipo=MAYOR, estado=Corte.BORRADOR).order_by("fecha"):
        vence = _mes_siguiente(corte.fecha).replace(day=dia) + timedelta(days=plazo)
        if hoy <= vence:
            break
        try:
            cerrados.append(cerrar_mayor(corte, None, sin_revisar=True, hoy=hoy))
        except ErrorCorte:
            break
    return cerrados


def generar_cobranza(fecha=None, usuario=None, automatica=False, request=None):
    fecha = fecha or hoy_negocio()
    cifras = calculo.cifras_cobranza(fecha)
    with transaction.atomic():
        if automatica and Corte.objects.filter(tipo=COBRANZA, fecha=fecha, automatico=True).exists():
            return None
        numero = (Corte.objects.filter(tipo=COBRANZA, fecha=fecha).aggregate(n=Max("numero"))["n"] or 0) + 1
        try:
            with transaction.atomic():
                corte = Corte.objects.create(tipo=COBRANZA, fecha=fecha, periodo_inicio=fecha, periodo_fin=fecha, numero=numero, automatico=automatica, cifras=cifras, usuario=usuario)
        except IntegrityError:
            return None
        corte = _cerrar(corte, cifras, usuario)
        crear_entregas(corte)
        registrar("lista_cobranza", usuario=usuario, objeto=corte, datos={"fecha": fecha.isoformat(), "renglones": cifras["totales"]["renglones"], "automatica": automatica}, request=request)
    return corte


def cobranza_programada(hoy=None):
    hoy = hoy or hoy_negocio()
    dia = int(parametro("dia_semana_cobranza"))
    if dia < 1 or dia > 7 or hoy.isoweekday() != dia:
        return None
    return generar_cobranza(hoy, automatica=True)


def _espera(intentos):
    return timedelta(minutes=min(2 ** max(intentos - 1, 0), ESPERA_MAXIMA_MINUTOS))


def ejecutar_entregas(ahora=None):
    ahora = ahora or timezone.now()
    hechas = fallidas = 0
    candidatas = Entrega.objects.filter(estado=Entrega.PENDIENTE).filter(Q(proximo_intento__isnull=True) | Q(proximo_intento__lte=ahora)).values_list("pk", flat=True)
    for pk in list(candidatas):
        tomada = Entrega.objects.filter(pk=pk, estado=Entrega.PENDIENTE).filter(Q(ocupada_hasta__isnull=True) | Q(ocupada_hasta__lt=ahora)).update(ocupada_hasta=ahora + timedelta(minutes=10))
        if tomada != 1:
            continue
        objeto = Entrega.objects.select_related("corte__caja", "destino").get(pk=pk)
        intentos = objeto.intentos + 1
        try:
            archivos = entrega.entregar(objeto)
        except Exception as error:
            fallidas += 1
            estado = Entrega.FALLIDA if intentos >= INTENTOS_MAXIMOS else Entrega.PENDIENTE
            Entrega.objects.filter(pk=pk).update(
                intentos=intentos, ultimo_error=f"{type(error).__name__}: {error}"[:300], proximo_intento=ahora + _espera(intentos), ocupada_hasta=None, estado=estado
            )
            registrar("entrega_fallida", objeto=objeto.corte, datos={"entrega": pk, "intentos": intentos, "error": f"{type(error).__name__}"})
            continue
        Entrega.objects.filter(pk=pk).update(estado=Entrega.ENTREGADA, intentos=intentos, ultimo_error="", entregada_en=timezone.now(), archivos=[a["nombre"] for a in archivos], ocupada_hasta=None)
        registrar("corte_entregado", objeto=objeto.corte, datos={"entrega": pk, "archivos": [{"nombre": a["nombre"], "sha256": a["sha256"]} for a in archivos], "nivel": objeto.nivel})
        hechas += 1
    return hechas, fallidas


def entregas_con_problema():
    return Entrega.objects.exclude(estado=Entrega.ENTREGADA).exclude(ultimo_error="").select_related("corte", "destino")


def puede_ver(usuario, corte):
    if usuario.tiene_permiso("ver_cortes"):
        return True
    return corte.tipo == DIARIO and corte.usuario_id == usuario.pk and usuario.tiene_permiso("turno_caja")


def visibles(usuario):
    if usuario.tiene_permiso("ver_cortes"):
        return Corte.objects.all()
    return Corte.objects.filter(tipo=DIARIO, usuario=usuario)
