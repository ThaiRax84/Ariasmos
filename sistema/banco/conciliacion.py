from collections import Counter
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from auditoria.servicios import registrar
from caja.models import Traslado
from cobros import libro
from cobros.models import Pago
from configuracion.models import Negocio, parametro
from nucleo import identificacion, reparto
from configuracion.moneda import formatear
from nucleo.lectores import santander_pyme
from titulares.models import Titular

from . import lectura
from .models import CuentaBancaria, Importacion, MapeoColumnas, MovimientoBancario, ReglaPagador

CLASES_PDF = {
    santander_pyme.SPEI: MovimientoBancario.SPEI,
    santander_pyme.MISMO_BANCO: MovimientoBancario.MISMO_BANCO,
    santander_pyme.EFECTIVO: MovimientoBancario.EFECTIVO,
    santander_pyme.DEVOLUCION: MovimientoBancario.DEVOLUCION,
    santander_pyme.OTRO: MovimientoBancario.OTRO,
}
COBRABLES = (MovimientoBancario.SPEI, MovimientoBancario.MISMO_BANCO, MovimientoBancario.ARCHIVO)
SINONIMOS = {
    "fecha": ["fecha", "fecha operacion", "fecha de operacion", "dia", "date"],
    "descripcion": ["descripcion", "movimiento", "detalle", "descripcion del movimiento"],
    "concepto": ["concepto", "concepto de pago", "leyenda"],
    "referencia": ["referencia", "ref", "referencia numerica"],
    "abono": ["abono", "abonos", "deposito", "depositos", "ingreso", "ingresos", "credito", "entrada"],
    "cargo": ["cargo", "cargos", "retiro", "retiros", "egreso", "egresos", "debito", "salida"],
    "importe": ["importe", "monto", "cantidad"],
    "saldo": ["saldo", "saldo final"],
}
PAPELES = list(SINONIMOS)


class ErrorConciliacion(ValueError):
    pass


def _texto(valor, maximo):
    return " ".join(str(valor or "").split())[:maximo]


def _ordinales(movimientos, llave):
    vistos = Counter()
    for movimiento in movimientos:
        clave = llave(movimiento)
        movimiento["ordinal"] = vistos[clave]
        vistos[clave] += 1


def movimientos_de_pdf(lineas):
    try:
        estado = santander_pyme.leer(lineas)
    except santander_pyme.ErrorEstado as error:
        raise ErrorConciliacion(str(error))
    cuenta = CuentaBancaria.objects.filter(clabe=estado.clabe).first()
    if cuenta is None:
        raise ErrorConciliacion("El estado de cuenta no es de una cuenta bancaria registrada del negocio (la CLABE no coincide).")
    vistos = Counter()
    movimientos = []
    for movimiento in estado.movimientos:
        clave = (movimiento.fecha, movimiento.folio, movimiento.importe, movimiento.sentido, movimiento.rastreo)
        ordinal = vistos[clave]
        vistos[clave] += 1
        movimientos.append(
            {
                "fecha": movimiento.fecha.isoformat(),
                "folio": _texto(movimiento.folio, 40),
                "descripcion": _texto(movimiento.descripcion, 300),
                "importe": movimiento.importe,
                "saldo": movimiento.saldo,
                "sentido": MovimientoBancario.ABONO if movimiento.sentido == "abono" else MovimientoBancario.CARGO,
                "clase": CLASES_PDF.get(movimiento.clase, MovimientoBancario.OTRO),
                "hora": _texto(movimiento.hora, 8),
                "banco_origen": _texto(movimiento.banco_origen, 80),
                "cuenta_pagador": movimiento.cuenta_pagador[:18],
                "nombre_pagador": _texto(movimiento.nombre_pagador, 150),
                "rastreo": _texto(movimiento.rastreo, 40),
                "referencia": _texto(movimiento.referencia, 40),
                "concepto": _texto(movimiento.concepto, 200),
                "huella": santander_pyme.huella(estado.clabe, movimiento, ordinal)[:400],
            }
        )
    resumen = {
        "periodo_inicio": estado.periodo_inicio.isoformat() if estado.periodo_inicio else None,
        "periodo_fin": estado.periodo_fin.isoformat() if estado.periodo_fin else None,
        "saldo_inicial": estado.saldo_inicial,
        "saldo_final": estado.saldo_final,
        "depositos": estado.depositos,
        "retiros": estado.retiros,
    }
    return cuenta, movimientos, resumen


def proponer_columnas(filas, cuenta=None):
    encabezado = lectura.detectar_encabezado(filas, SINONIMOS)
    guardado = getattr(cuenta, "mapeo", None) if cuenta is not None else None
    titulos = [lectura.normal(c) for c in filas[encabezado]]
    if guardado is not None and guardado.mapeo.get("titulos") == titulos:
        return encabezado, dict(guardado.mapeo.get("columnas", {}))
    propuesta = lectura.proponer(filas, encabezado, SINONIMOS, (("fecha", lectura.es_fecha), ("importe", lectura.es_importe)))
    return encabezado, propuesta


def _cuadrar(movimientos):
    if any(m["saldo"] is None for m in movimientos):
        return False
    for orden in (movimientos, list(reversed(movimientos))):
        ok = True
        for anterior, actual in zip(orden, orden[1:]):
            signo = 1 if actual["sentido"] == MovimientoBancario.ABONO else -1
            if anterior["saldo"] + signo * actual["importe"] != actual["saldo"]:
                ok = False
                break
        if ok:
            return True
    return None


def movimientos_de_filas(filas, encabezado, columnas, cuenta):
    columnas = {papel: int(indice) for papel, indice in columnas.items() if indice not in (None, "")}
    if "fecha" not in columnas:
        raise ErrorConciliacion("Indica qué columna es la fecha.")
    if not ({"abono", "cargo"} & set(columnas) or "importe" in columnas):
        raise ErrorConciliacion("Indica la columna de abonos y cargos, o la de importe con signo.")
    errores = []
    movimientos = []
    for numero, fila in enumerate(filas[encabezado + 1:], start=encabezado + 2):
        def valor(papel):
            indice = columnas.get(papel)
            return fila[indice] if indice is not None and indice < len(fila) else ""

        abono = lectura.importe(valor("abono")) if "abono" in columnas else None
        cargo = lectura.importe(valor("cargo")) if "cargo" in columnas else None
        con_signo = lectura.importe(valor("importe")) if "importe" in columnas else None
        if abono:
            sentido, monto = MovimientoBancario.ABONO, abs(abono)
        elif cargo:
            sentido, monto = MovimientoBancario.CARGO, abs(cargo)
        elif con_signo:
            sentido, monto = (MovimientoBancario.ABONO, con_signo) if con_signo > 0 else (MovimientoBancario.CARGO, -con_signo)
        else:
            if not any(c.strip() for c in fila):
                continue
            errores.append(f"Renglón {numero}: sin importe.")
            continue
        dia = lectura.fecha(valor("fecha"))
        if dia is None:
            errores.append(f"Renglón {numero}: fecha no reconocida ({_texto(valor('fecha'), 20)}).")
            continue
        saldo = lectura.importe(valor("saldo")) if "saldo" in columnas else None
        if "saldo" in columnas and saldo is None:
            errores.append(f"Renglón {numero}: saldo no reconocido.")
            continue
        movimientos.append(
            {
                "fecha": dia.isoformat(),
                "folio": "",
                "descripcion": _texto(valor("descripcion"), 300),
                "importe": monto,
                "saldo": saldo,
                "sentido": sentido,
                "clase": MovimientoBancario.ARCHIVO if sentido == MovimientoBancario.ABONO else MovimientoBancario.OTRO,
                "hora": "",
                "banco_origen": "",
                "cuenta_pagador": "",
                "nombre_pagador": "",
                "rastreo": "",
                "referencia": _texto(valor("referencia"), 40),
                "concepto": _texto(valor("concepto"), 200),
            }
        )
    if errores:
        raise ErrorConciliacion(" ".join(errores[:10]) + (f" (y {len(errores) - 10} más)" if len(errores) > 10 else ""))
    if not movimientos:
        raise ErrorConciliacion("El archivo no tiene movimientos.")
    if "saldo" in columnas and _cuadrar(movimientos) is None:
        raise ErrorConciliacion("Los saldos del archivo no cuadran con los importes; revisa las columnas o el archivo.")

    def llave(m):
        return (m["fecha"], m["importe"], m["sentido"], m["referencia"], lectura.normal(m["descripcion"]))

    _ordinales(movimientos, llave)
    for m in movimientos:
        m["huella"] = "|".join([cuenta.clabe, m["fecha"], str(m["importe"]), m["sentido"], m["referencia"], lectura.normal(m["descripcion"])[:200], str(m.pop("ordinal"))])
    return movimientos


def recordar_columnas(cuenta, filas, encabezado, columnas):
    titulos = [lectura.normal(c) for c in filas[encabezado]]
    MapeoColumnas.objects.update_or_create(cuenta=cuenta, defaults={"mapeo": {"titulos": titulos, "columnas": columnas}})


def _titular(matricula):
    return Titular.objects.filter(matricula=matricula).exclude(estado=Titular.RECHAZADO).select_related("familia").first()


def saldos_en_orden(titular):
    miembros = libro.miembros_de(titular)
    pendientes = libro.pendientes_de(miembros)
    total = sum(p.saldo for p in pendientes)
    if total <= 0:
        return []
    partes, _ = reparto.repartir(total, pendientes, titular.pk, miembros, libro.orden_reparto())
    return [p.importe for p in partes]


def _regla(cuenta_pagador):
    return ReglaPagador.objects.filter(cuenta_pagador=cuenta_pagador, activa=True).select_related("titular").first()


def decidir(movimiento):
    negocio = Negocio.actual()

    def existe(matricula):
        return _titular(matricula) is not None

    def saldos_de(matricula):
        titular = _titular(matricula)
        return saldos_en_orden(titular) if titular else []

    def regla_de(cuenta):
        regla = _regla(cuenta)
        return regla.titular.matricula if regla is not None and regla.titular.estado != Titular.RECHAZADO else None

    def pagador_confiable(cuenta):
        regla = _regla(cuenta)
        return bool(parametro("aplicar_solo_por_pagador")) and regla is not None and regla.confirmaciones >= parametro("confirmaciones_pagador_confiable")

    return identificacion.decidir(
        movimiento["referencia"], movimiento["concepto"], movimiento["importe"], existe, saldos_de,
        cuenta_pagador=movimiento.get("cuenta_pagador", ""), regla_de=regla_de, pagador_confiable=pagador_confiable,
        longitud=negocio.longitud_matricula if negocio else 7,
    )


def _dia(valor):
    if valor is None or isinstance(valor, date):
        return valor
    return date.fromisoformat(valor)


def continuidad(cuenta, adaptador, resumen):
    if adaptador != Importacion.ESTADO_PDF:
        return Importacion.NO_VERIFICABLE
    resumen = resumen or {}
    inicio, fin = _dia(resumen.get("periodo_inicio")), _dia(resumen.get("periodo_fin"))
    if inicio is None or fin is None:
        return Importacion.CON_HUECO
    previas = Importacion.objects.filter(cuenta=cuenta, adaptador=Importacion.ESTADO_PDF, periodo_inicio__isnull=False, periodo_fin__isnull=False)
    if not previas.exists():
        return Importacion.PRIMERA
    mismo = previas.filter(periodo_inicio=inicio, periodo_fin=fin).order_by("creada", "id").first()
    if mismo is not None:
        if mismo.saldo_inicial != resumen.get("saldo_inicial") or mismo.saldo_final != resumen.get("saldo_final"):
            raise ErrorConciliacion(
                f"Ya se importó un estado del mismo periodo con otros saldos: aquel abrió en {formatear(mismo.saldo_inicial or 0)} y cerró en {formatear(mismo.saldo_final or 0)}; "
                f"este abre en {formatear(resumen.get('saldo_inicial') or 0)} y cierra en {formatear(resumen.get('saldo_final') or 0)}."
            )
        return mismo.continuidad
    if previas.filter(periodo_inicio__lte=fin, periodo_fin__gte=inicio).exists():
        return Importacion.CON_HUECO
    anterior = previas.filter(periodo_fin=inicio - timedelta(days=1)).order_by("-creada", "-id").first()
    if anterior is not None:
        if anterior.saldo_final != resumen.get("saldo_inicial"):
            raise ErrorConciliacion(
                f"No continúa el estado anterior: cerró el {anterior.periodo_fin:%d/%m/%Y} en {formatear(anterior.saldo_final or 0)} "
                f"y este abre en {formatear(resumen.get('saldo_inicial') or 0)}. No se importó nada."
            )
        return Importacion.VERIFICADA
    return Importacion.CON_HUECO


def pendientes_de_revision():
    aplicados = Q(lista__estado=MovimientoBancario.APLICADO)
    return (
        Importacion.objects.filter(continuidad__in=Importacion.A_REVISAR, revisada_por__isnull=True)
        .annotate(pagos=Count("lista", filter=aplicados), monto=Sum("lista__importe", filter=aplicados))
        .filter(pagos__gt=0)
        .select_related("cuenta__banco", "creada_por")
        .order_by("creada", "id")
    )


class RevisionPropia(ErrorConciliacion):
    pass


def marcar_revisada(importacion, usuario, request=None):
    if importacion.creada_por_id == usuario.pk:
        registrar("revision_propia_denegada", usuario=usuario, objeto=importacion, datos={"archivo": importacion.nombre_archivo}, request=request)
        raise RevisionPropia("Quien importó no puede revisar su propia importación.")
    if not importacion.requiere_revision:
        raise ErrorConciliacion("Esta importación no necesita revisión.")
    with transaction.atomic():
        hechos = Importacion.objects.filter(pk=importacion.pk, revisada_por__isnull=True).update(revisada_por=usuario, revisada_en=timezone.now())
        if hechos != 1:
            raise ErrorConciliacion("Esta importación ya estaba revisada.")
        aplicados = importacion.lista.filter(estado=MovimientoBancario.APLICADO).aggregate(n=Count("id"), t=Sum("importe"))
        registrar(
            "importacion_revisada",
            usuario=usuario,
            objeto=importacion,
            datos={"archivo": importacion.nombre_archivo, "continuidad": importacion.continuidad, "importo": str(importacion.creada_por), "pagos": aplicados["n"], "monto": aplicados["t"] or 0},
            request=request,
        )


def candidatos_deposito(cuenta, importe, dia):
    tolerancia = timedelta(days=parametro("dias_tolerancia_deposito"))
    return Traslado.objects.filter(
        tipo=Traslado.DEPOSITO, estado=Traslado.POR_CONCILIAR, cuenta_bancaria=cuenta, importe=importe,
        fecha_deposito__gte=dia - tolerancia, fecha_deposito__lte=dia + tolerancia, movimiento__isnull=True,
    ).select_related("origen")


def destino(movimiento, cuenta):
    if movimiento["sentido"] != MovimientoBancario.ABONO:
        return "informativo", None
    if movimiento["clase"] == MovimientoBancario.EFECTIVO:
        candidatos = list(candidatos_deposito(cuenta, movimiento["importe"], datetime.fromisoformat(movimiento["fecha"]).date()))
        return ("deposito", candidatos[0]) if len(candidatos) == 1 else ("sin_pista", None)
    if movimiento["clase"] in COBRABLES:
        decision = decidir(movimiento)
        return decision.resultado, decision
    return "informativo", None


def vista_previa(cuenta, movimientos):
    cuentas = Counter()
    existentes = set(MovimientoBancario.objects.filter(huella__in=[m["huella"] for m in movimientos]).values_list("huella", flat=True))
    for movimiento in movimientos:
        if movimiento["huella"] in existentes:
            cuentas["duplicado"] += 1
            continue
        resultado, _ = destino(movimiento, cuenta)
        cuentas[resultado] += 1
    return {
        "total": len(movimientos),
        "duplicados": cuentas["duplicado"],
        "automaticos": cuentas[identificacion.AUTOMATICA],
        "sugeridos": cuentas[identificacion.SUGERIDA],
        "sin_pista": cuentas[identificacion.SIN_PISTA],
        "depositos": cuentas["deposito"],
        "informativos": cuentas["informativo"],
        "abonos": sum(m["importe"] for m in movimientos if m["sentido"] == MovimientoBancario.ABONO),
        "cargos": sum(m["importe"] for m in movimientos if m["sentido"] == MovimientoBancario.CARGO),
    }


def momento(dia, hora=""):
    negocio = Negocio.actual()
    zona = ZoneInfo(negocio.zona_horaria) if negocio else timezone.get_default_timezone()
    try:
        reloj = time.fromisoformat(hora) if hora else time(12, 0)
    except ValueError:
        reloj = time(12, 0)
    return datetime.combine(dia, reloj, tzinfo=zona)


def aplicar(movimiento, titular, usuario, request=None):
    with transaction.atomic():
        fresco = MovimientoBancario.objects.get(pk=movimiento.pk)
        if fresco.pago_id is not None or fresco.estado not in (MovimientoBancario.POR_IDENTIFICAR,):
            raise ErrorConciliacion("El movimiento ya está resuelto.")
        if titular.estado == Titular.RECHAZADO:
            raise ErrorConciliacion("No se aplica a un registro rechazado.")
        pago = libro.registrar_pago(
            titular, fresco.importe, Pago.BANCO, usuario, request=request, serie=parametro("serie_recibos_banco"),
            fecha=momento(fresco.fecha, fresco.hora), movimiento=fresco,
        )
        hechos = MovimientoBancario.objects.filter(pk=fresco.pk, pago__isnull=True).update(estado=MovimientoBancario.APLICADO, pago=pago, resuelto_por=usuario, resuelto_en=timezone.now())
        if hechos != 1:
            raise ErrorConciliacion("El movimiento ya está resuelto.")
    return pago


def aprender(cuenta_pagador, titular):
    if not cuenta_pagador:
        return None
    regla = ReglaPagador.objects.filter(cuenta_pagador=cuenta_pagador).first()
    ahora = timezone.now()
    if regla is None:
        return ReglaPagador.objects.create(cuenta_pagador=cuenta_pagador, titular=titular, confirmaciones=1, ultima_vez=ahora)
    if regla.titular_id == titular.pk:
        regla.confirmaciones += 1
    else:
        regla.titular = titular
        regla.confirmaciones = 1
    regla.ultima_vez = ahora
    regla.activa = True
    regla.save()
    return regla


def conciliar_deposito(movimiento, traslado, usuario, request=None):
    with transaction.atomic():
        fresco = MovimientoBancario.objects.get(pk=movimiento.pk)
        if fresco.estado != MovimientoBancario.POR_IDENTIFICAR:
            raise ErrorConciliacion("El movimiento ya está resuelto.")
        if fresco.clase != MovimientoBancario.EFECTIVO:
            raise ErrorConciliacion("Solo un depósito en efectivo se empareja con un depósito de caja.")
        if not candidatos_deposito(fresco.cuenta, fresco.importe, fresco.fecha).filter(pk=traslado.pk).exists():
            raise ErrorConciliacion("Ese depósito de caja no corresponde por cuenta, importe o fecha, o ya está conciliado.")
        cambiados = Traslado.objects.filter(pk=traslado.pk, estado=Traslado.POR_CONCILIAR).update(estado=Traslado.CONCILIADO, resuelto_en=timezone.now())
        if cambiados != 1:
            raise ErrorConciliacion("Ese depósito de caja ya está conciliado.")
        MovimientoBancario.objects.filter(pk=fresco.pk).update(estado=MovimientoBancario.CONCILIADO, traslado=traslado, resuelto_por=usuario, resuelto_en=timezone.now())
        registrar("deposito_conciliado", usuario=usuario, objeto=traslado, datos={"movimiento": fresco.pk, "importe": fresco.importe, "registro": str(traslado.origen)}, request=request)


def importar(cuenta, movimientos, adaptador, nombre, sha256, usuario, resumen=None, request=None):
    resumen = resumen or {}
    with transaction.atomic():
        clasificacion = continuidad(cuenta, adaptador, resumen)
        importacion = Importacion.objects.create(
            continuidad=clasificacion,
            cuenta=cuenta, nombre_archivo=lectura.nombre_saneado(nombre), sha256=sha256, adaptador=adaptador,
            periodo_inicio=resumen.get("periodo_inicio") or min(m["fecha"] for m in movimientos),
            periodo_fin=resumen.get("periodo_fin") or max(m["fecha"] for m in movimientos),
            saldo_inicial=resumen.get("saldo_inicial"), saldo_final=resumen.get("saldo_final"),
            depositos=sum(m["importe"] for m in movimientos if m["sentido"] == MovimientoBancario.ABONO),
            retiros=sum(m["importe"] for m in movimientos if m["sentido"] == MovimientoBancario.CARGO),
            movimientos=len(movimientos), creada_por=usuario,
        )
        cuentas = Counter()
        for datos in movimientos:
            if MovimientoBancario.objects.filter(huella=datos["huella"]).exists():
                cuentas["duplicados"] += 1
                continue
            resultado, extra = destino(datos, cuenta)
            estado = MovimientoBancario.INFORMATIVO if resultado == "informativo" else MovimientoBancario.POR_IDENTIFICAR
            movimiento = MovimientoBancario.objects.create(
                cuenta=cuenta, importacion=importacion, estado=estado,
                **{k: v for k, v in datos.items() if k not in ("fecha",)}, fecha=datetime.fromisoformat(datos["fecha"]).date(),
            )
            cuentas["nuevos"] += 1
            if resultado == "deposito":
                conciliar_deposito(movimiento, extra, usuario, request)
                cuentas["depositos"] += 1
            elif resultado == identificacion.AUTOMATICA:
                aplicar(movimiento, _titular(extra.matricula), usuario, request)
                cuentas["aplicados"] += 1
            elif resultado in (identificacion.SUGERIDA, identificacion.SIN_PISTA):
                if extra is not None:
                    MovimientoBancario.objects.filter(pk=movimiento.pk).update(
                        sugerencia=extra.matricula, alternativas=list(extra.alternativas), motivo=extra.motivo, coincide_importe=extra.coincide_importe
                    )
                cuentas["sugeridos" if resultado == identificacion.SUGERIDA else "sin_pista"] += 1
        Importacion.objects.filter(pk=importacion.pk).update(
            nuevos=cuentas["nuevos"], duplicados=cuentas["duplicados"], aplicados=cuentas["aplicados"],
            sugeridos=cuentas["sugeridos"], sin_pista=cuentas["sin_pista"], depositos_emparejados=cuentas["depositos"],
        )
        importacion.refresh_from_db()
        registrar(
            "importacion_bancaria",
            usuario=usuario,
            objeto=importacion,
            datos={
                "archivo": importacion.nombre_archivo, "sha256": sha256, "cuenta": str(cuenta), "adaptador": adaptador, "continuidad": clasificacion,
                "periodo": [str(importacion.periodo_inicio), str(importacion.periodo_fin)], "saldo_inicial": importacion.saldo_inicial, "saldo_final": importacion.saldo_final,
                "total_abonos": importacion.depositos, "total_cargos": importacion.retiros, "movimientos": len(movimientos),
                "aplicados_monto": importacion.lista.filter(estado=MovimientoBancario.APLICADO).aggregate(t=Sum("importe"))["t"] or 0, **dict(cuentas),
            },
            request=request,
        )
    return importacion


def confirmar(movimiento, titular, usuario, request=None):
    with transaction.atomic():
        pago = aplicar(movimiento, titular, usuario, request)
        regla = aprender(movimiento.cuenta_pagador, titular)
        registrar(
            "movimiento_confirmado",
            usuario=usuario,
            objeto=movimiento,
            titular=titular.pk,
            datos={"importe": movimiento.importe, "importe_texto": formatear(movimiento.importe), "sugerencia": movimiento.sugerencia, "confirmado_a": titular.matricula, "regla": regla.confirmaciones if regla else None},
            request=request,
        )
    return pago


def proponer(movimiento, titular, usuario, request=None):
    with transaction.atomic():
        hechos = MovimientoBancario.objects.filter(pk=movimiento.pk, estado=MovimientoBancario.POR_IDENTIFICAR).update(propuesta=titular, propuesta_por=usuario, propuesta_en=timezone.now())
        if hechos != 1:
            raise ErrorConciliacion("El movimiento ya está resuelto.")
        registrar("movimiento_propuesto", usuario=usuario, objeto=movimiento, titular=titular.pk, datos={"matricula": titular.matricula, "importe": movimiento.importe}, request=request)


def no_es_cobro(movimiento, motivo, usuario, request=None):
    motivo = " ".join(str(motivo or "").split())[:300]
    if not motivo:
        raise ErrorConciliacion("Escribe el motivo.")
    with transaction.atomic():
        hechos = MovimientoBancario.objects.filter(pk=movimiento.pk, estado=MovimientoBancario.POR_IDENTIFICAR).update(estado=MovimientoBancario.NO_COBRO, nota=motivo, resuelto_por=usuario, resuelto_en=timezone.now())
        if hechos != 1:
            raise ErrorConciliacion("El movimiento ya está resuelto.")
        registrar("movimiento_no_cobro", usuario=usuario, objeto=movimiento, datos={"importe": movimiento.importe, "motivo": motivo}, request=request)
