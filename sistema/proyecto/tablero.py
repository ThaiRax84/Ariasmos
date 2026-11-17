from datetime import datetime, time, timedelta

from django.db.models import Count, F, Q, Sum
from django.urls import reverse
from django.utils import dateformat, timezone

from auditoria.servicios import MOTIVOS, ultima_verificacion
from banco import conciliacion
from banco.models import CuentaBancaria, Importacion, MovimientoBancario
from caja import retiros
from caja.models import Denominacion, RetiroCaja, ReversionRetiro, Traslado
from caja.servicios import alertas as alertas_caja
from caja.servicios import devoluciones_articulos, turno_abierto
from cobros.libro import con_saldo
from cobros.models import Cargo, Pago, ReversionPago
from configuracion.models import Negocio, hoy_negocio, parametro, vocabulario
from configuracion.moneda import formatear
from cortes import calendario
from cortes import servicios as cortes
from cortes.calculo import local, zona
from cortes.models import MAYOR, Corte
from cuentas import conectar
from cuentas.models import Dispositivo
from cuentas.servicios import avisos_pendientes, por_revisar
from inventario import servicios as inventario
from respaldos import servicios as respaldos
from respaldos.models import Respaldo

DIRECCION = "direccion"
COORDINACION = "coordinacion"
RECEPCION = "recepcion"
OCULTO = "Se muestra al cerrar tu turno"
MAXIMO_RENGLONES = 50

ESTADOS = {
    "bien": ("Bien", "bien"),
    "revisar": ("Revisar", "aviso"),
    "por_hacer": ("Por hacer", "aviso"),
    "por_revisar": ("Por revisar", "aviso"),
    "por_confirmar": ("Por confirmar", "aviso"),
    "sin_comprobante": ("Sin comprobante", "aviso"),
    "retenidos": ("Retenidos", "aviso"),
    "en_espera": ("En espera", "calma"),
}


def perfil(usuario):
    if usuario.tiene_permiso("ver_auditoria") or usuario.tiene_permiso("administrar_configuracion"):
        return DIRECCION
    if usuario.tiene_permiso("aprobar_solicitudes") or usuario.tiene_permiso("recibir_efectivo"):
        return COORDINACION
    return RECEPCION


def _plural(numero, singular, plural=None):
    return f"{numero} {singular if numero == 1 else (plural or singular + 's')}"


def _fecha(valor, formato="d/m/Y"):
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        valor = local(valor)
    return dateformat.format(valor, formato)


def renglon(clave, titulo, detalle, estado, enlaces=()):
    texto, tono = ESTADOS[estado]
    return {"clave": clave, "titulo": titulo, "detalle": detalle, "estado": estado, "pastilla": texto, "tono": tono, "enlaces": [{"texto": t, "url": u} for t, u in enlaces]}


def mes_en_curso(ahora=None):
    hoy = local(ahora or timezone.now()).date()
    inicio = hoy.replace(day=1)
    siguiente = (inicio + timedelta(days=32)).replace(day=1)
    lugar = zona()
    return datetime.combine(inicio, time.min, tzinfo=lugar), datetime.combine(siguiente, time.min, tzinfo=lugar)


def dia_en_curso(ahora=None):
    hoy = local(ahora or timezone.now()).date()
    desde = datetime.combine(hoy, time.min, tzinfo=zona())
    return desde, datetime.combine(hoy + timedelta(days=1), time.min, tzinfo=zona())


def cobrado(desde, hasta):
    datos = Pago.objects.filter(fecha__gte=desde, fecha__lt=hasta, reversion__isnull=True, medio__in=(Pago.EFECTIVO, Pago.BANCO)).aggregate(
        efectivo=Sum("importe", filter=Q(medio=Pago.EFECTIVO)),
        banco=Sum("importe", filter=Q(medio=Pago.BANCO)),
        cobros=Count("id"),
        cajas=Count("turno__caja", distinct=True),
    )
    efectivo, banco = datos["efectivo"] or 0, datos["banco"] or 0
    total = efectivo + banco
    porcentaje = round(efectivo * 100 / total) if total else 0
    return {"total": total, "efectivo": efectivo, "banco": banco, "cobros": datos["cobros"], "cajas": datos["cajas"], "porcentaje_efectivo": porcentaje, "porcentaje_banco": 100 - porcentaje if total else 0}


def cobrado_mes(ahora=None):
    return cobrado(*mes_en_curso(ahora))


def cobrado_hoy(ahora=None):
    return cobrado(*dia_en_curso(ahora))


def por_cobrar_vencido(hoy=None):
    hoy = hoy or hoy_negocio()
    consulta = con_saldo(Cargo.objects.filter(vencimiento__lt=hoy, titular__interno=False)).filter(saldo__gt=0)
    datos = consulta.aggregate(total=Sum("saldo"), titulares=Count("titular", distinct=True))
    return {"total": datos["total"] or 0, "titulares": datos["titulares"] or 0}


def _por_persona(consulta, persona, campo="importe"):
    return {fila["persona"]: fila["total"] or 0 for fila in consulta.order_by().values(persona=F(persona)).annotate(total=Sum(campo)) if fila["persona"] is not None}


def custodias():
    partes = (
        (1, _por_persona(Pago.objects.filter(medio=Pago.EFECTIVO), "turno__usuario")),
        (-1, _por_persona(ReversionPago.objects.all(), "turno__usuario", "pago__importe")),
        (-1, _por_persona(RetiroCaja.objects.all(), "turno__usuario")),
        (1, _por_persona(ReversionRetiro.objects.all(), "turno__usuario", "retiro__importe")),
        (-1, _por_persona(devoluciones_articulos(), "turno__usuario", "importe_dinero")),
        (-1, _por_persona(Traslado.objects.filter(tipo=Traslado.ENTREGA, estado=Traslado.CONFIRMADO), "origen")),
        (-1, _por_persona(Traslado.objects.filter(tipo=Traslado.DEPOSITO), "origen")),
        (1, _por_persona(Traslado.objects.filter(tipo=Traslado.ENTREGA, estado=Traslado.CONFIRMADO), "destino")),
    )
    totales = {}
    for signo, montos in partes:
        for persona, monto in montos.items():
            totales[persona] = totales.get(persona, 0) + signo * monto
    return totales


def efectivo_en_custodia(quien_ve):
    oculto = quien_ve.pk if turno_abierto(quien_ve) is not None else None
    con_efectivo = {persona: monto for persona, monto in custodias().items() if monto > 0 and persona != oculto}
    return {"total": sum(con_efectivo.values()), "personas": len(con_efectivo)}


def retiros_semana(ahora=None):
    desde, hasta = retiros.periodo(ahora, "semana")
    datos = RetiroCaja.objects.filter(creado__gte=desde, creado__lt=hasta, reversion__isnull=True).aggregate(
        total=Sum("importe"), cantidad=Count("id"), sin_comprobante=Count("id", filter=~Q(comprobante=RetiroCaja.ADJUNTO))
    )
    return {"total": datos["total"] or 0, "cantidad": datos["cantidad"] or 0, "sin_comprobante": datos["sin_comprobante"] or 0}


def _cifra(clave, etiqueta, detalle="", importe=None, texto=None, oculta=False, enlace=None, aviso=False):
    return {"clave": clave, "etiqueta": etiqueta, "importe": importe, "texto": texto, "detalle": OCULTO if oculta else detalle, "oculta": oculta, "enlace": enlace, "aviso": aviso}


def _nombre_mes(ahora=None):
    return dateformat.format(local(ahora or timezone.now()), "F").lower()


def _cobrado_en_mes(usuario, ciego, ahora):
    if ciego:
        return _cifra("cobrado_mes", f"Cobrado en {_nombre_mes(ahora)}", oculta=True)
    datos = cobrado_mes(ahora)
    detalle = f"efectivo {datos['porcentaje_efectivo']} % · banco {datos['porcentaje_banco']} %" if datos["total"] else "Sin cobros este mes"
    return _cifra("cobrado_mes", f"Cobrado en {_nombre_mes(ahora)}", detalle, importe=datos["total"], enlace=reverse("cortes:lista"))


def _vencido():
    datos = por_cobrar_vencido()
    textos = vocabulario()
    nombre = (textos["titular"] if datos["titulares"] == 1 else textos["titulares"]).lower()
    return _cifra("por_cobrar_vencido", "Por cobrar vencido", f"{datos['titulares']} {nombre} con adeudo vencido", importe=datos["total"], enlace=reverse("titulares:lista"), aviso=bool(datos["total"]))


def _custodia(usuario, ciego, etiqueta, clave):
    if ciego:
        return _cifra(clave, etiqueta, oculta=True)
    datos = efectivo_en_custodia(usuario)
    return _cifra(clave, etiqueta, _plural(datos["personas"], "persona"), importe=datos["total"], enlace=reverse("caja:custodia"))


def _retiros():
    datos = retiros_semana()
    detalle = _plural(datos["cantidad"], "retiro")
    if datos["sin_comprobante"]:
        detalle += f" · {datos['sin_comprobante']} sin comprobante"
    return _cifra("retiros_semana", "Retiros de la semana", detalle, importe=datos["total"], enlace=reverse("caja:retiros"), aviso=bool(datos["sin_comprobante"]))


def _cobrado_del_dia(ciego, ahora):
    if ciego:
        return _cifra("cobrado_hoy", "Cobrado hoy", oculta=True)
    datos = cobrado_hoy(ahora)
    detalle = _plural(datos["cobros"], "cobro")
    if datos["cajas"]:
        detalle += " · " + _plural(datos["cajas"], "caja")
    return _cifra("cobrado_hoy", "Cobrado hoy", detalle, importe=datos["total"], enlace=reverse("cortes:lista"))


def _banco():
    pendientes = MovimientoBancario.objects.filter(estado=MovimientoBancario.POR_IDENTIFICAR).aggregate(total=Count("id"), propuestos=Count("id", filter=Q(propuesta__isnull=False)))
    return _cifra("banco_por_identificar", "Banco por identificar", f"{pendientes['propuestos']} con propuesta", texto=str(pendientes["total"]), enlace=reverse("conciliacion:cola"), aviso=bool(pendientes["total"]))


def _corte_pendiente(pendientes):
    if not pendientes:
        return _cifra("corte_diario", "Corte diario pendiente", "Todas las cajas al día", texto="Ninguno")
    primero = pendientes[0]
    texto = str(primero["caja"]) if len(pendientes) == 1 else _plural(len(pendientes), "caja")
    return _cifra("corte_diario", "Corte diario pendiente", f"límite {_fecha(primero['limite'], 'H:i')} · ya pasó", texto=texto, enlace=reverse("caja:custodia"), aviso=True)


def cifras(usuario, ahora=None, diarios=None):
    ciego = turno_abierto(usuario) is not None
    tiene = usuario.tiene_permiso
    lista = []
    if perfil(usuario) == DIRECCION:
        if tiene("ver_cortes"):
            lista.append(_cobrado_en_mes(usuario, ciego, ahora))
        if tiene("ver_titulares"):
            lista.append(_vencido())
        if tiene("recibir_efectivo"):
            lista.append(_custodia(usuario, ciego, "Efectivo en custodia", "efectivo_custodia"))
        if tiene("revisar_retiros"):
            lista.append(_retiros())
    elif perfil(usuario) == COORDINACION:
        if tiene("ver_cortes"):
            lista.append(_cobrado_del_dia(ciego, ahora))
        if tiene("recibir_efectivo"):
            lista.append(_custodia(usuario, ciego, "Efectivo sin entregar", "efectivo_sin_entregar"))
        if tiene("conciliar_banco"):
            lista.append(_banco())
        if tiene("recibir_efectivo"):
            lista.append(_corte_pendiente(cortes.diarios_pendientes() if diarios is None else diarios))
    return lista


def corte_propio(turno, ahora=None):
    if turno is None:
        return None
    limite = calendario.limite(local(turno.abierto_en))
    if limite is None:
        return None
    ahora = ahora or timezone.now()
    restante = limite - ahora
    if restante.total_seconds() <= 0:
        return {"vencido": True, "limite": limite, "texto": f"Pasó la hora límite ({_fecha(limite, 'd/m/Y H:i')}). Cierra tu turno en cuanto puedas."}
    if local(limite).date() != local(ahora).date():
        return None
    minutos = int(restante.total_seconds() // 60)
    return {"vencido": False, "limite": limite, "texto": f"Cierra tu turno antes de las {_fecha(limite, 'H:i')}. Faltan {minutos // 60} h {minutos % 60} min."}


def _salud_respaldo():
    if not respaldos.carpeta():
        return renglon("respaldo", "Respaldo", "No hay carpeta de respaldo configurada", "revisar", [("Ir a respaldos", reverse("respaldos:panel"))])
    ultimo = Respaldo.objects.filter(tipo=Respaldo.RESPALDO, resultado=Respaldo.CORRECTO).first()
    if ultimo is None:
        return renglon("respaldo", "Respaldo", "Todavía no hay ningún respaldo correcto", "por_hacer", [("Ir a respaldos", reverse("respaldos:panel"))])
    viejo = (timezone.now() - ultimo.creado).total_seconds() > respaldos.HORAS_ALERTA * 3600
    return renglon("respaldo", "Respaldo", f"{_fecha(ultimo.creado, 'd/m/Y H:i')} · en la carpeta de respaldo", "revisar" if viejo else "bien", [("Ir a respaldos", reverse("respaldos:panel"))])


def _salud_prueba():
    enlace = [("Ir a respaldos", reverse("respaldos:panel"))]
    prueba = Respaldo.objects.filter(tipo=Respaldo.PRUEBA).exclude(resultado=Respaldo.EN_CURSO).first()
    if prueba is None:
        return renglon("prueba_restauracion", "Prueba de restauración", "Todavía no se ha probado restaurar un respaldo", "por_hacer", enlace)
    dias = (timezone.now() - prueba.creado).days
    if prueba.resultado == Respaldo.FALLO:
        return renglon("prueba_restauracion", "Prueba de restauración", f"La última prueba falló ({_fecha(prueba.creado)})", "revisar", enlace)
    hace = "Hoy" if dias == 0 else f"Hace {_plural(dias, 'día')}"
    if dias >= respaldos.DIAS_PRUEBA:
        return renglon("prueba_restauracion", "Prueba de restauración", f"{hace} · ya toca otra", "por_hacer", enlace)
    return renglon("prueba_restauracion", "Prueba de restauración", f"{hace} · toca en {_plural(respaldos.DIAS_PRUEBA - dias, 'día')}", "bien", enlace)


def salud(usuario, certificado=None, dispositivos=0):
    filas = []
    if usuario.tiene_permiso("ver_auditoria"):
        verificacion = ultima_verificacion()
        if verificacion is None:
            filas.append(renglon("bitacora", "Bitácora", "Todavía no se ha verificado", "por_hacer", [("Ver bitácora", reverse("auditoria:lista"))]))
        else:
            detalle = f"Verificada {_fecha(verificacion.momento, 'd/m/Y H:i')}" + (" · íntegra" if verificacion.valida else "")
            filas.append(renglon("bitacora", "Bitácora", detalle, "bien" if verificacion.valida else "revisar", [("Ver bitácora", reverse("auditoria:lista"))]))
    if usuario.tiene_permiso("administrar_respaldos"):
        filas.append(_salud_respaldo())
        filas.append(_salud_prueba())
    if usuario.tiene_permiso("aprobar_dispositivos"):
        if certificado:
            estado = "revisar" if certificado["por_vencer"] else "bien"
            filas.append(renglon("certificado", "Certificado del servidor", f"Vence el {_fecha(certificado['vence'])}", estado, [("Conectar otra computadora", reverse("conectar"))]))
        detalle = f"{_plural(dispositivos, 'equipo')} pidiendo acceso" if dispositivos else "Ninguno pidiendo acceso"
        filas.append(renglon("equipos", "Equipos por aprobar", detalle, "revisar" if dispositivos else "bien", [("Ver equipos", reverse("dispositivos"))] if dispositivos else []))
    return filas


def _avisos_efectivo(usuario):
    filas = []
    datos = alertas_caja(usuario)
    custodia = reverse("caja:custodia")
    for t in datos["depositos_sin_conciliar"]:
        filas.append(renglon("deposito_sin_conciliar", "Depósito sin conciliar", f"Depósito sin conciliar de {formatear(t.importe)} registrado por {t.origen} el {_fecha(t.creado)} en {t.cuenta_bancaria} (referencia {t.referencia}): no ha aparecido en el banco.", "revisar", [("Ver custodia", custodia)]))
    for f in datos["sin_trasladar"]:
        filas.append(renglon("efectivo_sin_trasladar", "Efectivo sin entregar", f"{f['usuario']} tiene {formatear(f['custodia'])} sin entregar ni depositar desde {_fecha(f['desde'])}.", "revisar", [("Ver custodia", custodia)]))
    for t in datos["entregas_pendientes"]:
        filas.append(renglon("entrega_sin_confirmar", "Entrega de efectivo sin confirmar", f"Entrega de {formatear(t.importe)} de {t.origen} a {t.destino} sin confirmar.", "en_espera", [("Ver custodia", custodia)]))
    for a in datos["diferencias"]:
        filas.append(renglon("diferencia_arqueo", f"Diferencia de arqueo · {a.turno.caja}", f"Diferencia de arqueo de {formatear(a.diferencia)} en el turno de {a.turno.usuario} ({a.turno.caja}, {_fecha(a.creado)}): {a.nota}", "revisar", [("Ver custodia", custodia)]))
    for r in datos["recibos_cancelados"]:
        filas.append(renglon("recibo_cancelado", f"Recibo {r} cancelado", f"{r.pago.titular.nombre_completo}, {formatear(r.pago.importe)}: {r.pago.reversion.motivo}", "revisar", [("Ver recibo", reverse("cobros:recibo", args=[r.pk]))]))
    return filas


def _avisos_retiros(usuario):
    filas = []
    datos = retiros.avisos(usuario)
    lista = reverse("caja:retiros")
    for a in datos["cerca_del_tope"]:
        uso = f"{formatear(a['usado'])} de {formatear(a['limite'])}" if a["tope"] == "importe" else f"{a['usado']} de {a['limite']} retiros"
        filas.append(renglon("retiros_cerca_del_tope", f"Retiros de caja · {a['caja']}", f"{a['caja']} ya usó {uso} del periodo.", "revisar", [("Ver retiros", lista)]))
    vistos = set()
    for r in datos["sin_comprobante"]:
        vistos.add(r.pk)
        filas.append(renglon("retiro_sin_comprobante", f"Retiro {r} · {formatear(r.importe)}", f"De {r.registrado_por} ({r.motivo}) declarado sin comprobante: {r.motivo_sin_comprobante}", "sin_comprobante", [("Ver", reverse("caja:retiro", args=[r.pk]))]))
    for r in datos["por_revisar_viejos"]:
        vistos.add(r.pk)
        filas.append(renglon("retiro_sin_revisar", f"Retiro {r} · {formatear(r.importe)}", f"De {r.registrado_por} sin revisar desde {_fecha(r.creado)}.", "por_revisar", [("Ver", reverse("caja:retiro", args=[r.pk]))]))
    for t in datos["sobre_maximo"]:
        filas.append(renglon("efectivo_sobre_maximo", f"Efectivo máximo · {t.caja}", f"{t.caja} ({t.usuario}) pasa del efectivo máximo: conviene entregar o depositar.", "revisar", [("Ver retiros", lista)]))
    recientes = RetiroCaja.objects.filter(revision=RetiroCaja.POR_REVISAR).exclude(registrado_por=usuario).exclude(pk__in=vistos).select_related("motivo")[:10]
    for r in recientes:
        comprobante = "con comprobante" if r.comprobante == RetiroCaja.ADJUNTO else r.get_comprobante_display().lower()
        filas.append(renglon("retiro_por_revisar", f"Retiro {r} · {formatear(r.importe)}", f"{r.motivo} · {comprobante}", "por_revisar", [("Ver", reverse("caja:retiro", args=[r.pk]))]))
    return filas


def _avisos_banco(usuario, permisos):
    filas = []
    if "conciliar_banco" in permisos:
        for i in conciliacion.con_retenidos()[:MAXIMO_RENGLONES]:
            filas.append(renglon("importacion_retenida", f"Importaciones automáticas retenidas · {i.nombre_archivo}", f"{_fecha(i.creada, 'd/m/Y H:i')} · {_plural(i.retenidos, 'movimiento retenido', 'movimientos retenidos')} por {formatear(i.monto_retenido)} · {i.get_continuidad_display()}. No se aplican hasta que alguien con permiso de conciliación los compare con el banco y los libere.", "retenidos", [("Ver", reverse("conciliacion:importacion", args=[i.pk]))]))
    if "conciliar_banco" in permisos or "ver_auditoria" in permisos:
        revertir = "solicitar_ajustes" in permisos or "aplicar_ajustes" in permisos
        for m in conciliacion.sin_respaldo_vigentes()[:MAXIMO_RENGLONES]:
            enlaces = [("Solicitar su reversión", reverse("cobros:revertir", args=[m.pago.pk]))] if revertir else []
            filas.append(renglon("pago_sin_respaldo", "Pagos sin respaldo en el estado", f"{_fecha(m.fecha)} · {formatear(m.importe)} · {m.pago.titular.nombre_completo} · recibo {m.pago.recibo}. No aparece en el estado de cuenta en PDF de su periodo; no se revierte solo.", "revisar", enlaces))
        dias = parametro("dias_sin_respaldo_alerta")
        for m in conciliacion.antiguos_sin_respaldo()[:MAXIMO_RENGLONES]:
            filas.append(renglon("pago_sin_estado", "Pagos sin un estado que los respalde", f"{_fecha(m.fecha)} · {formatear(m.importe)} · {m.pago.titular.nombre_completo} · recibo {m.pago.recibo}. Lleva más de {dias} días sin el estado de cuenta en PDF que lo cubra.", "revisar"))
    if "ver_auditoria" in permisos:
        for i in conciliacion.pendientes_de_revision()[:MAXIMO_RENGLONES]:
            filas.append(renglon("importacion_por_revisar", "Importaciones bancarias por revisar", f"{i.nombre_archivo} · importó {i.importo} el {_fecha(i.creada, 'd/m/Y H:i')} · {_plural(i.pagos, 'pago')} por {formatear(i.monto)} · {i.get_continuidad_display()}", "por_revisar", [("Revisar", reverse("conciliacion:importacion", args=[i.pk]))]))
    if "conciliar_banco" in permisos:
        for i in Importacion.objects.filter(origen=Importacion.CARPETA).select_related("cuenta__banco")[:5]:
            retenida = i.retenida and not i.liberada_en
            filas.append(renglon("carpeta_vigilada", f"Carpeta vigilada · {i.nombre_archivo}", f"{_fecha(i.creada, 'd/m/Y H:i')} · {_plural(i.aplicados, 'aplicado')}" + (" · con retenidos" if retenida else ""), "retenidos" if retenida else "bien", [("Ver", reverse("conciliacion:importacion", args=[i.pk]))]))
        pendientes = MovimientoBancario.objects.filter(estado=MovimientoBancario.POR_IDENTIFICAR).aggregate(total=Count("id"), propuestos=Count("id", filter=Q(propuesta__isnull=False)))
        ultima = Importacion.objects.order_by("-creada").first()
        titulo = f"Banco: {_plural(pendientes['total'], 'movimiento')} por identificar" + (f" ({pendientes['propuestos']} con propuesta)" if pendientes["propuestos"] else "")
        detalle = f"Última importación: {_fecha(ultima.creada, 'd/m/Y H:i')} ({ultima.nombre_archivo})." if ultima else "Todavía no se ha importado ningún estado de cuenta."
        filas.append(renglon("banco", titulo, detalle, "revisar" if pendientes["total"] else "bien", [("Ver cola", reverse("conciliacion:cola")), ("Importar estado de cuenta", reverse("conciliacion:importar"))]))
    return filas


def _avisos_inventario(usuario):
    filas = []
    datos = inventario.avisos(usuario)
    for a, e in datos.get("bajo_minimo", []):
        filas.append(renglon("inventario_bajo_minimo", f"Inventario · {a}", f"{a}: existencia {e}, mínimo {a.minimo}.", "revisar", [("Ver inventario", reverse("inventario:indice"))]))
    for a, e, referencia in datos.get("existencia_baja", []):
        filas.append(renglon("inventario_existencia_baja", f"Inventario · {a}", f"{a}: existencia baja, quedan {e} de {referencia} tras su última entrada o conteo.", "revisar", [("Ver inventario", reverse("inventario:indice"))]))
    if datos.get("por_revisar"):
        cuantos = datos["por_revisar"]
        filas.append(renglon("inventario_por_revisar", "Movimientos de inventario", f"{_plural(cuantos, 'movimiento')} de inventario por revisar.", "por_revisar", [("Revisar", reverse("inventario:revision"))]))
    if datos.get("conteo_viejo"):
        conteo = datos["conteo_viejo"]
        filas.append(renglon("inventario_conteo_viejo", f"Conteo de inventario {conteo.pk}", f"El conteo {conteo.pk} espera aprobación desde el {_fecha(conteo.creado)}.", "revisar", [("Ver conteo", reverse("inventario:conteo_detalle", args=[conteo.pk]))]))
    return filas


def avisos_control(usuario, certificado=None, diarios=None):
    tiene = usuario.tiene_permiso
    permisos = {p for p in ("conciliar_banco", "ver_auditoria", "solicitar_ajustes", "aplicar_ajustes") if tiene(p)}
    filas = []
    if tiene("ver_auditoria"):
        verificacion = ultima_verificacion()
        if verificacion is not None and not verificacion.valida:
            motivo = MOTIVOS.get(verificacion.motivo, verificacion.motivo)
            evento = f" (evento {verificacion.numero})" if verificacion.numero else ""
            filas.append(renglon("bitacora_no_integra", "La bitácora no está íntegra", f"Verificación del {_fecha(verificacion.momento, 'd/m/Y H:i')}: {motivo}{evento}.", "revisar", [("Ver bitácora", reverse("auditoria:lista"))]))
    if tiene("recibir_efectivo"):
        filas.extend(_avisos_efectivo(usuario))
    if tiene("revisar_retiros"):
        filas.extend(_avisos_retiros(usuario))
    filas.extend(_avisos_banco(usuario, permisos))
    filas.extend(_avisos_inventario(usuario))
    if tiene("recibir_efectivo"):
        por_recibir = Traslado.objects.filter(destino=usuario, estado=Traslado.PENDIENTE).count()
        if por_recibir:
            filas.append(renglon("entregas_por_confirmar", f"Tienes {_plural(por_recibir, 'entrega')} de efectivo por confirmar", "Confírmala al recibir el efectivo o recházala si no coincide.", "por_confirmar", [("Revisar", reverse("caja:traslados"))]))
        for p in cortes.diarios_pendientes() if diarios is None else diarios:
            filas.append(renglon("corte_diario_pendiente", f"Corte diario pendiente · {p['caja']}", f"{p['persona']} · turno abierto desde {_fecha(p['desde'], 'd/m/Y H:i')}" + (" (de un día anterior)" if p["dia_anterior"] else ""), "revisar"))
    if tiene("administrar_respaldos"):
        if Negocio.objects.filter(pk=1, clave_recuperacion_pendiente=True).exists():
            filas.append(renglon("clave_recuperacion", "Guarda la clave de recuperación", "Sin ella ningún respaldo se puede abrir. Se muestra una sola vez.", "por_hacer", [("Ver la clave", reverse("respaldos:clave"))]))
        for texto in respaldos.alertas():
            filas.append(renglon("respaldos", "Respaldos", texto, "revisar", [("Ir a respaldos", reverse("respaldos:panel"))]))
    if tiene("administrar_configuracion"):
        problemas = cortes.entregas_con_problema().count()
        if problemas:
            filas.append(renglon("entregas_cortes", f"Hay {_plural(problemas, 'entrega')} de cortes con problemas", "No se pudieron dejar en su destino.", "revisar", [("Revisar", reverse("cortes:destinos"))]))
    if tiene("cerrar_cortes"):
        for c in Corte.objects.filter(tipo=MAYOR, estado=Corte.BORRADOR).order_by("fecha"):
            filas.append(renglon("corte_mayor_borrador", f"Corte mayor de {_fecha(c.fecha, 'm/Y')}", "En borrador: falta cerrarlo y entregarlo.", "por_hacer", [("Ver", reverse("cortes:detalle", args=[c.pk]))]))
    if tiene("administrar_configuracion"):
        if not Denominacion.objects.filter(activa=True).exists():
            filas.append(renglon("faltan_denominaciones", "Faltan las denominaciones de caja", "No hay billetes ni monedas capturados para la moneda del negocio: el arqueo de caja no podrá contar el efectivo.", "por_hacer", [("Capturar denominaciones", reverse("configuracion:catalogo", args=["denominaciones"]))]))
        if CuentaBancaria.principal_activa() is None:
            filas.append(renglon("falta_cuenta", "Faltan los datos de pago", "No hay una cuenta bancaria principal: la ficha de pago no muestra a dónde pagar.", "por_hacer", [("Agregar cuenta", reverse("banco:nueva"))]))
    revisar_codigos = por_revisar(usuario).exists()
    bloqueos = avisos_pendientes(usuario).exists()
    if revisar_codigos or bloqueos:
        partes = []
        if revisar_codigos:
            partes.append("Se usaron códigos de tu autenticador para autorizar solicitudes. Confírmalas o repórtalas.")
        if bloqueos:
            partes.append("Alguien tecleó códigos erróneos a tu nombre y la vía de código quedó bloqueada.")
        filas.append(renglon("codigo_autorizacion", "Avisos sobre tu código de autorización", " ".join(partes), "revisar", [("Revisar", reverse("autorizaciones"))]))
    if certificado and certificado["por_vencer"]:
        filas.append(renglon("certificado_por_vencer", "El certificado del servidor vence pronto", f"Vence el {_fecha(certificado['vence'])} (faltan {certificado['dias']} días). Actualiza el programa en esta computadora para generar uno nuevo y después vuelve a instalarlo en las demás computadoras.", "revisar", [("Conectar otra computadora", reverse("conectar"))]))
    return filas


def ordenar(filas):
    orden = {"aviso": 0, "calma": 1, "bien": 2}
    return sorted(filas, key=lambda fila: orden.get(fila["tono"], 1))


def certificado_para(usuario):
    if not usuario.tiene_permiso("aprobar_dispositivos"):
        return None
    return conectar.datos()


def dispositivos_para(usuario):
    if not usuario.tiene_permiso("aprobar_dispositivos"):
        return 0
    return Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).count()
