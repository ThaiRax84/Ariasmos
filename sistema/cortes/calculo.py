from collections import defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Count, Sum
from django.utils import timezone

from banco.ficha import datos_de_pago
from banco.models import Importacion, MovimientoBancario
from caja.models import Arqueo, RetiroCaja, ReversionRetiro, Traslado, Turno
from caja.servicios import custodia
from cobros import libro
from cobros.models import Aplicacion, Beca, CancelacionCargo, Cargo, ConceptoCobro, Pago, Prorroga, ReversionPago
from configuracion import moneda
from configuracion.models import Negocio, hoy_negocio
from cuentas.models import Usuario
from nucleo import telefono
from titulares import contactos
from titulares.models import CampoContacto, Titular

TRAMOS = (("1_30", 1, 30), ("31_60", 31, 60), ("61_90", 61, 90), ("mas_90", 91, None))


def zona():
    negocio = Negocio.actual()
    try:
        return ZoneInfo(negocio.zona_horaria) if negocio else timezone.get_default_timezone()
    except Exception:
        return timezone.get_default_timezone()


def limites(inicio, fin):
    lugar = zona()
    return datetime.combine(inicio, time.min, tzinfo=lugar), datetime.combine(fin + timedelta(days=1), time.min, tzinfo=lugar)


def local(momento):
    return timezone.localtime(momento, zona())


def persona(usuario):
    return usuario.nombre if usuario is not None else ""


def titular(objeto):
    return {"nombre": objeto.nombre_completo, "matricula": objeto.matricula, "familia": objeto.familia.nombre if objeto.familia_id else ""}


def base(tipo, titulo, inicio, fin):
    return {
        "tipo": tipo,
        "titulo": titulo,
        "moneda": moneda.codigo_actual(),
        "unidad_importes": "centavos",
        "periodo": [inicio.isoformat(), fin.isoformat()],
        "generado": timezone.now().isoformat(),
        "encabezado": {},
        "totales": {},
        "secciones": [],
    }


def seccion(clave, titulo, filas):
    return {"clave": clave, "titulo": titulo, "filas": filas}


def _conceptos(pago):
    return sorted({a.cargo.concepto.nombre for a in pago.aplicaciones.all()})


def cifras_diario(turno, arqueo):
    pagos = list(
        Pago.objects.filter(turno=turno, medio=Pago.EFECTIVO).select_related("titular__familia", "recibo").prefetch_related("aplicaciones__cargo__concepto").order_by("fecha", "id")
    )
    devoluciones = list(ReversionPago.objects.filter(turno=turno).select_related("pago__titular__familia", "pago__recibo").order_by("creada", "id"))
    recibos = [
        {"folio": str(p.recibo), "hora": f"{local(p.fecha):%H:%M}", "titular": titular(p.titular), "conceptos": _conceptos(p), "importe": p.importe}
        for p in pagos
    ]
    filas_devoluciones = [
        {"folio": str(d.pago.recibo), "hora": f"{local(d.creada):%H:%M}", "titular": titular(d.pago.titular), "importe": d.pago.importe, "motivo": d.motivo}
        for d in devoluciones
    ]
    hasta = turno.cerrado_en or timezone.now()
    traslados = [
        {
            "tipo": t.get_tipo_display(),
            "hora": f"{local(t.creado):%H:%M}",
            "a": persona(t.destino) if t.tipo == Traslado.ENTREGA else str(t.cuenta_bancaria or ""),
            "importe": t.importe,
            "estado": t.get_estado_display(),
        }
        for t in Traslado.objects.filter(origen=turno.usuario, creado__gte=turno.abierto_en, creado__lte=hasta).select_related("destino", "cuenta_bancaria").order_by("creado", "id")
    ]
    retiros = [
        {"folio": str(r), "hora": f"{local(r.creado):%H:%M}", "motivo": r.motivo.nombre, "nota": r.nota, "importe": r.importe, "comprobante": r.get_comprobante_display(), "autorizo": persona(r.autorizado_por)}
        for r in RetiroCaja.objects.filter(turno=turno).select_related("motivo", "autorizado_por").order_by("creado", "id")
    ]
    regresos = [
        {"folio": str(r.retiro), "hora": f"{local(r.creada):%H:%M}", "importe": r.retiro.importe, "motivo": r.motivo}
        for r in ReversionRetiro.objects.filter(turno=turno).select_related("retiro").order_by("creada", "id")
    ]
    cobrado = sum(p.importe for p in pagos)
    devuelto = sum(d.pago.importe for d in devoluciones)
    retirado = sum(r["importe"] for r in retiros)
    regresado = sum(r["importe"] for r in regresos)
    datos = base("diario", "Corte diario de caja", local(turno.abierto_en).date(), local(hasta).date())
    datos["encabezado"] = {
        "caja": turno.caja.nombre,
        "persona": persona(turno.usuario),
        "abierto": f"{local(turno.abierto_en):%d/%m/%Y %H:%M}",
        "cerrado": f"{local(hasta):%d/%m/%Y %H:%M}",
    }
    datos["totales"] = {
        "fondo_inicial": turno.fondo_inicial,
        "total_cobrado": cobrado,
        "total_devuelto": devuelto,
        "total_retirado": retirado,
        "total_regresado": regresado,
        "recibos": len(recibos),
        "esperado": arqueo.esperado,
        "contado": arqueo.contado,
        "diferencia": arqueo.diferencia,
        "nota": arqueo.nota,
        "con_reconteo": arqueo.con_reconteo,
        "primer_contado": arqueo.primer_contado if arqueo.primer_contado is not None else arqueo.contado,
    }
    datos["secciones"] = [
        seccion("recibos", "Recibos del turno", recibos),
        seccion("devoluciones", "Devoluciones", filas_devoluciones),
        seccion("retiros", "Retiros de caja", retiros),
        seccion("retiros_revertidos", "Retiros revertidos que regresaron a esta caja", regresos),
        seccion("traslados", "Traslados", traslados),
    ]
    if arqueo.esperado_piezas:
        filas_piezas = []
        for valor in sorted({int(v) for v in list(arqueo.esperado_piezas) + list(arqueo.conteo)}, reverse=True):
            esperadas, contadas = int(arqueo.esperado_piezas.get(str(valor), 0)), int(arqueo.conteo.get(str(valor), 0))
            filas_piezas.append({"denominacion": valor, "esperadas": esperadas, "contadas": contadas, "diferencia": contadas - esperadas})
        datos["secciones"].append(seccion("piezas", "Piezas por denominación", filas_piezas))
    return datos


def _vigentes(inicio, fin):
    desde, hasta = limites(inicio, fin)
    return Pago.objects.filter(fecha__gte=desde, fecha__lt=hasta, reversion__isnull=True)


def _estado_concepto(cargos):
    if not cargos:
        return "sin cargo"
    saldo = sum(c.saldo for c in cargos)
    pagado = sum(c.aplicado + c.cancelado for c in cargos)
    if saldo <= 0:
        return "pagado"
    if pagado > 0:
        return "parcial"
    return "adeudo"


def cifras_mayor(inicio, fin, al_dia=None):
    al_dia = al_dia or hoy_negocio()
    desde, hasta = limites(inicio, fin)
    corte_dia = limites(al_dia, al_dia)[1]
    pagos = _vigentes(inicio, fin)
    por_medio = [{"medio": dict(Pago.MEDIOS).get(m["medio"], m["medio"]), "pagos": m["n"], "importe": m["total"]} for m in pagos.values("medio").annotate(total=Sum("importe"), n=Count("id")).order_by("medio")]
    aplicaciones = Aplicacion.objects.filter(pago__in=pagos).values("cargo__concepto__nombre").annotate(total=Sum("importe")).order_by("cargo__concepto__nombre")
    por_concepto = {a["cargo__concepto__nombre"]: a["total"] for a in aplicaciones}
    cargos_mes = list(libro.con_saldo(Cargo.objects.filter(vencimiento__gte=inicio, vencimiento__lte=fin)).select_related("concepto", "titular__familia"))
    esperado = defaultdict(int)
    for cargo in cargos_mes:
        esperado[cargo.concepto.nombre] += cargo.importe_final - cargo.cancelado
    cobrado_esperado = {
        fila["cargo__concepto__nombre"]: fila["total"]
        for fila in Aplicacion.objects.filter(cargo__in=[c.pk for c in cargos_mes], pago__reversion__isnull=True, creada__lt=corte_dia)
        .values("cargo__concepto__nombre")
        .annotate(total=Sum("importe"))
    }
    nombres = sorted(set(esperado) | set(por_concepto))
    filas_concepto = [{"concepto": n, "ingresos": por_concepto.get(n, 0), "esperado": esperado.get(n, 0), "cobrado_de_lo_esperado": cobrado_esperado.get(n, 0)} for n in nombres]
    conceptos = list(ConceptoCobro.objects.filter(activo=True).order_by("prioridad", "nombre").values_list("nombre", flat=True))
    por_titular = defaultdict(lambda: defaultdict(list))
    for cargo in cargos_mes:
        por_titular[cargo.titular_id][cargo.concepto.nombre].append(cargo)
    titulares = Titular.objects.filter(estado__in=[Titular.ACTIVO, Titular.BAJA]).select_related("familia").order_by("apellidos", "nombre")
    becas = defaultdict(list)
    for beca in Beca.objects.filter(vigente_desde__lte=fin).select_related("concepto"):
        if beca.vigente_hasta is None or beca.vigente_hasta >= inicio:
            becas[beca.titular_id].append(f"{beca.concepto.nombre} {beca.puntos_base / 100:g}%")
    prorrogas = defaultdict(list)
    for prorroga in Prorroga.objects.filter(creada__gte=desde, creada__lt=hasta).select_related("cargo__concepto"):
        prorrogas[prorroga.cargo.titular_id].append(f"{prorroga.cargo.concepto.nombre} hasta {prorroga.fecha_limite:%d/%m/%Y}")
    filas_titular = []
    for persona_titular in titulares:
        if persona_titular.estado == Titular.BAJA and persona_titular.pk not in por_titular:
            continue
        fila = {"titular": titular(persona_titular), "estado": persona_titular.get_estado_display()}
        for nombre in conceptos:
            fila[nombre] = _estado_concepto(por_titular[persona_titular.pk].get(nombre, []))
        fila["becas"] = becas.get(persona_titular.pk, [])
        fila["prorrogas"] = prorrogas.get(persona_titular.pk, [])
        filas_titular.append(fila)
    cartera = {clave: 0 for clave, _, _ in TRAMOS}
    for cargo in libro.con_saldo(Cargo.objects.filter(vencimiento__lt=al_dia)).filter(saldo__gt=0):
        dias = (al_dia - cargo.vencimiento).days
        for clave, minimo, maximo in TRAMOS:
            if dias >= minimo and (maximo is None or dias <= maximo):
                cartera[clave] += cargo.saldo
    altas = [{"titular": titular(t), "desde": t.activo_desde.isoformat()} for t in Titular.objects.filter(activo_desde__gte=inicio, activo_desde__lte=fin).select_related("familia")]
    bajas = [{"titular": titular(t), "fecha": f"{local(t.fecha_baja):%d/%m/%Y}"} for t in Titular.objects.filter(fecha_baja__gte=desde, fecha_baja__lt=hasta).select_related("familia")]
    cerrados = Turno.objects.filter(estado=Turno.CERRADO)
    efectivo_total = Pago.objects.filter(medio=Pago.EFECTIVO, turno__in=cerrados).aggregate(t=Sum("importe"))["t"] or 0
    devuelto_total = ReversionPago.objects.filter(turno__in=cerrados).aggregate(t=Sum("pago__importe"))["t"] or 0
    retirado_total = RetiroCaja.objects.filter(turno__in=cerrados).aggregate(t=Sum("importe"))["t"] or 0
    regresado_total = ReversionRetiro.objects.filter(turno__in=cerrados).aggregate(t=Sum("retiro__importe"))["t"] or 0
    depositado_total = Traslado.objects.filter(tipo=Traslado.DEPOSITO).aggregate(t=Sum("importe"))["t"] or 0
    abiertos = Turno.objects.filter(estado=Turno.ABIERTO)
    en_custodia = sum(custodia(u) for u in Usuario.objects.all()) - sum(_neto(t) for t in abiertos)
    retiros_mes = [
        {
            "fecha": f"{local(r.creado):%d/%m/%Y}",
            "folio": str(r),
            "caja": r.caja.nombre,
            "persona": persona(r.registrado_por),
            "motivo": r.motivo.nombre,
            "importe": r.importe,
            "comprobante": r.get_comprobante_display(),
            "revision": r.get_revision_display(),
            "autorizo": persona(r.autorizado_por),
            "revertido": hasattr(r, "reversion"),
        }
        for r in RetiroCaja.objects.filter(creado__gte=desde, creado__lt=hasta, turno__in=cerrados).select_related("caja", "registrado_por", "motivo", "autorizado_por", "reversion")
    ]
    arqueos = [
        {"fecha": f"{local(a.creado):%d/%m/%Y}", "caja": a.turno.caja.nombre, "persona": persona(a.turno.usuario), "diferencia": a.diferencia, "nota": a.nota}
        for a in Arqueo.objects.filter(creado__gte=desde, creado__lt=hasta).exclude(diferencia=0).select_related("turno__caja", "turno__usuario")
    ]
    depositos = [
        {"fecha": t.fecha_deposito.isoformat() if t.fecha_deposito else "", "persona": persona(t.origen), "cuenta": str(t.cuenta_bancaria or ""), "importe": t.importe}
        for t in Traslado.objects.filter(tipo=Traslado.DEPOSITO, estado=Traslado.POR_CONCILIAR).select_related("origen", "cuenta_bancaria")
    ]
    banco = _banco(inicio, fin, desde, hasta)
    reversos = [
        {
            "fecha": f"{local(r.creada):%d/%m/%Y}",
            "folio": str(r.pago.recibo),
            "titular": titular(r.pago.titular),
            "importe": r.pago.importe,
            "ejecuto": persona(r.ejecutada_por),
            "autorizo": persona(r.autorizada_por),
            "motivo": r.motivo,
        }
        for r in ReversionPago.objects.filter(creada__gte=desde, creada__lt=hasta).select_related("pago__recibo", "pago__titular__familia", "ejecutada_por", "autorizada_por")
    ]
    cancelaciones = [
        {
            "fecha": f"{local(c.creada):%d/%m/%Y}",
            "tipo": c.get_tipo_display(),
            "titular": titular(c.cargo.titular),
            "cargo": c.cargo.concepto.nombre + (f" {c.cargo.periodo}" if c.cargo.periodo else ""),
            "importe": c.importe,
            "ejecuto": persona(c.ejecutada_por),
            "autorizo": persona(c.autorizada_por),
            "motivo": c.motivo,
        }
        for c in CancelacionCargo.objects.filter(creada__gte=desde, creada__lt=hasta).select_related("cargo__titular__familia", "cargo__concepto", "ejecutada_por", "autorizada_por")
    ]
    datos = base("mayor", "Corte mayor", inicio, fin)
    datos["encabezado"] = {"periodo": f"{inicio:%d/%m/%Y} a {fin:%d/%m/%Y}", "al_dia": al_dia.isoformat()}
    datos["totales"] = {
        "ingresos": sum(f["importe"] for f in por_medio),
        "esperado": sum(esperado.values()),
        "cobrado_de_lo_esperado": sum(cobrado_esperado.values()),
        "cartera_vencida": cartera,
        "altas": len(altas),
        "bajas": len(bajas),
        "efectivo_cobrado_neto": efectivo_total - devuelto_total,
        "efectivo_retirado_neto": retirado_total - regresado_total,
        "efectivo_en_custodia": en_custodia,
        "efectivo_depositado": depositado_total,
        "efectivo_cuadra": efectivo_total - devuelto_total - retirado_total + regresado_total == en_custodia + depositado_total,
        "nota_efectivo": "Las cifras de efectivo cuentan solo turnos cerrados.",
        "retiros_del_mes": sum(r["importe"] for r in retiros_mes),
        "efectivo_del_mes": pagos.filter(medio=Pago.EFECTIVO).aggregate(t=Sum("importe"))["t"] or 0,
        "banco": banco["totales"],
    }
    datos["secciones"] = [
        seccion("ingresos_por_medio", "Ingresos por medio de pago", por_medio),
        seccion("ingresos_por_concepto", "Ingresos, esperado y cobrado por concepto", filas_concepto),
        seccion("titulares", "Estado por titular y concepto", filas_titular),
        seccion("cartera_vencida", "Cartera vencida por antigüedad", [{"tramo": clave.replace("_", " a ").replace("mas a 90", "más de 90") + " días", "importe": cartera[clave]} for clave, _, _ in TRAMOS]),
        seccion("altas", "Altas", altas),
        seccion("bajas", "Bajas", bajas),
        seccion("diferencias_arqueo", "Diferencias de arqueo", arqueos),
        seccion("retiros", "Retiros de caja", retiros_mes),
        seccion("depositos_sin_conciliar", "Depósitos sin conciliar", depositos),
        seccion("banco_no_confirmados", "Pagos de importaciones no verificables sin confirmar por el estado oficial", banco["no_confirmados"]),
        seccion("importaciones_por_revisar", "Importaciones pendientes de revisión", banco["por_revisar"]),
        seccion("reversos", "Reversos de pago", reversos),
        seccion("cancelaciones", "Cancelaciones y condonaciones", cancelaciones),
    ]
    return datos


def _neto(turno):
    from caja.servicios import neto_de

    return neto_de(turno)


def _banco(inicio, fin, desde, hasta):
    from banco import conciliacion

    pagos_banco = Pago.objects.filter(medio=Pago.BANCO, reversion__isnull=True, movimiento__fecha__gte=inicio, movimiento__fecha__lte=fin).select_related("movimiento__importacion", "movimiento__confirmado_por", "titular__familia", "recibo")
    oficiales = Importacion.objects.filter(adaptador=Importacion.ESTADO_PDF, periodo_inicio__lte=inicio, periodo_fin__gte=fin)
    abonos_oficiales = MovimientoBancario.objects.filter(importacion__in=oficiales, sentido=MovimientoBancario.ABONO, fecha__gte=inicio, fecha__lte=fin)
    aplicado_oficial = 0
    no_confirmados = []
    aplicado = 0
    for pago in pagos_banco:
        aplicado += pago.importe
        movimiento = pago.movimiento
        confirmado = movimiento.importacion.adaptador == Importacion.ESTADO_PDF or movimiento.confirmado_por_id is not None
        if confirmado:
            aplicado_oficial += pago.importe
        elif movimiento.importacion.continuidad == Importacion.NO_VERIFICABLE:
            no_confirmados.append(
                {
                    "fecha": movimiento.fecha.isoformat(),
                    "folio": str(pago.recibo),
                    "titular": titular(pago.titular),
                    "importe": pago.importe,
                    "importacion": movimiento.importacion.nombre_archivo,
                }
            )
    por_revisar = [
        {"archivo": i.nombre_archivo, "importo": persona(i.creada_por) or "Carpeta vigilada", "fecha": f"{local(i.creada):%d/%m/%Y}", "pagos": i.pagos, "importe": i.monto or 0, "clasificacion": i.get_continuidad_display()}
        for i in conciliacion.pendientes_de_revision()
    ]
    pendientes = MovimientoBancario.objects.filter(estado=MovimientoBancario.POR_IDENTIFICAR)
    return {
        "totales": {
            "aplicado_por_banco": aplicado,
            "estado_oficial_importado": oficiales.exists(),
            "abonos_del_estado_oficial": abonos_oficiales.aggregate(t=Sum("importe"))["t"] or 0,
            "aplicado_confirmado_por_estado_oficial": aplicado_oficial,
            "aplicado_sin_confirmar": aplicado - aplicado_oficial,
            "movimientos_por_identificar": pendientes.count(),
            "importe_por_identificar": pendientes.aggregate(t=Sum("importe"))["t"] or 0,
        },
        "no_confirmados": no_confirmados,
        "por_revisar": por_revisar,
    }


def _vencimiento_efectivo(cargo):
    prorroga = cargo.prorrogas.order_by("-fecha_limite").first()
    return max(cargo.vencimiento, prorroga.fecha_limite) if prorroga else cargo.vencimiento


def contacto_principal(objeto):
    contacto = contactos.principal(objeto)
    if contacto is None:
        return {"nombre": "", "relacion": "", "telefono": "", "correo": ""}
    prefijo = contactos.prefijo()
    telefono_texto = correo = ""
    for campo in CampoContacto.objects.filter(activo=True).order_by("-principal", "orden"):
        valor = contacto.valor(campo)
        if campo.tipo == CampoContacto.TELEFONO and valor and not telefono_texto:
            telefono_texto = telefono.formatear(valor, prefijo)
        if campo.tipo == CampoContacto.CORREO and valor and not correo:
            correo = valor
    return {"nombre": contacto.nombre, "relacion": str(contacto.relacion or ""), "telefono": telefono_texto, "correo": correo}


def cifras_cobranza(fecha):
    filas = []
    cargos = libro.con_saldo(Cargo.objects.filter(vencimiento__lt=fecha)).filter(saldo__gt=0).select_related("titular__familia", "concepto").prefetch_related("prorrogas").order_by("titular__apellidos", "titular__nombre", "vencimiento", "id")
    contactos_cache = {}
    for cargo in cargos:
        vence = _vencimiento_efectivo(cargo)
        if vence >= fecha:
            continue
        if cargo.titular_id not in contactos_cache:
            contactos_cache[cargo.titular_id] = contacto_principal(cargo.titular)
        filas.append(
            {
                "titular": titular(cargo.titular),
                "concepto": cargo.concepto.nombre,
                "periodo": cargo.periodo,
                "importe_pendiente": cargo.saldo,
                "vencimiento": vence.isoformat(),
                "dias_atraso": (fecha - vence).days,
                "contacto": contactos_cache[cargo.titular_id],
            }
        )
    datos = base("cobranza", "Lista de cobranza", fecha, fecha)
    pago = datos_de_pago()
    if pago:
        cuenta = pago["cuenta"]
        datos["encabezado"] = {
            "fecha": fecha.isoformat(),
            "banco": str(cuenta.banco or ""),
            "clabe": cuenta.clabe_formateada,
            "beneficiario": cuenta.beneficiario,
            "medios": ", ".join(str(m) for m in pago["medios"]),
            "donde_va_la_matricula": pago["lugar"],
        }
    else:
        datos["encabezado"] = {"fecha": fecha.isoformat()}
    datos["totales"] = {"renglones": len(filas), "importe_pendiente": sum(f["importe_pendiente"] for f in filas)}
    datos["secciones"] = [seccion("adeudos", "Adeudos vencidos", filas)]
    return datos
