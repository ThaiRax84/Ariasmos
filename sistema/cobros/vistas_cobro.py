import re
import secrets
from datetime import timedelta
from io import BytesIO

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from reportlab.pdfgen import canvas

from auditoria.models import Evento
from auditoria.servicios import registrar
from caja import cambio as calculo_cambio
from caja import piezas as control_piezas
from caja.formularios import FormularioPiezasCobro
from caja.models import Turno
from caja.servicios import recibe_movimientos, turno_abierto
from configuracion import hoja as tamano_hoja
from configuracion.models import hoy_negocio, parametro, vocabulario
from cuentas.permisos import quienes
from cuentas.decoradores import exigir_ingresos_o_propio, requiere_permiso
from configuracion.moneda import formatear
from rezagos import servicios as rezagos
from solicitudes import motor
from tarifas import servicios as tarifas
from titulares import contactos
from titulares.models import Titular

from . import libro, qr
from .estado import estado_cuenta

from .formularios import (
    FormularioBeca,
    FormularioCancelacion,
    FormularioCargoManual,
    FormularioPago,
    FormularioProrroga,
    FormularioReversion,
    FormularioVerificarRecibo,
)
from .models import Cargo, Pago, Recibo

AJUSTES = ("solicitar_ajustes", "aplicar_ajustes")
FICHA_VALIDA = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def _miembros(titular):
    return list(Titular.objects.filter(pk__in=libro.miembros_de(titular)).order_by("apellidos", "nombre"))


@requiere_permiso("registrar_pago_efectivo")
def buscar(request):
    from titulares import lista

    contexto = lista.preparar(request, "cobrar", [Titular.ACTIVO], con_filtros=True)
    contexto.update({"turno": turno_abierto(request.user), "destino": "cobros:cobrar", "accion": "Cobrar", "titulo_lista": "cobrar", "con_panel": True})
    return render(request, "cobros/buscar.html", contexto)


def _venta(request, titular):
    from inventario import servicios as inventario

    valor = request.POST.get("venta") if request.method == "POST" else request.GET.get("venta")
    return inventario.venta_por_cobrar(titular, valor) if valor else None


def _primero(venta):
    from inventario import servicios as inventario

    return inventario.cargos_de(venta) if venta is not None else None


def es_panel(request):
    return (request.POST if request.method == "POST" else request.GET).get("panel") == "1"


def _cargos_en_orden(titular, estado):
    if estado["adeudo"] <= 0:
        return []
    partes, _ = libro.proponer_reparto(titular, estado["adeudo"])
    por_id = {fila["cargo"].pk: fila for fila in estado["cargos"]}
    filas = []
    for parte in partes:
        fila = por_id.get(parte.cargo)
        if fila is not None:
            filas.append({"cargo": fila["cargo"], "estado": fila["estado"], "saldo": parte.importe})
    return filas


def _contexto_panel(request, titular, contexto):
    from banco.ficha import datos_de_pago

    contexto["cargos_panel"] = _cargos_en_orden(titular, contexto["estado"])
    contexto["pago_banco"] = datos_de_pago()
    contexto["ultimo_banco"] = Pago.objects.filter(titular__in=[m.pk for m in contexto["estado"]["titulares"]], medio=Pago.BANCO).order_by("-pk").values_list("pk", flat=True).first() or 0
    contexto["configura_banco"] = request.user.tiene_permiso("administrar_configuracion")
    if contexto["con_piezas"] and contexto["piezas"] is None:
        contexto["piezas"] = {"formulario": FormularioPiezasCobro()}
    return contexto


def _pantalla_cobro(request, titular, formulario, propuesta=None, importe=None, ficha=None, status=200, piezas=None):
    miembros = _miembros(titular)
    venta = _venta(request, titular)
    if venta is not None and not formulario.is_bound and importe is None:
        from inventario import servicios as inventario

        pendiente = inventario.pendiente_de(venta)
        if pendiente > 0:
            formulario = FormularioPago(initial={"importe": pendiente})
    contexto = {
        "venta": venta,
        "titular": titular,
        "formulario": formulario,
        "estado": estado_cuenta(miembros),
        "propuesta": propuesta,
        "importe": importe,
        "ficha": ficha,
        "turno": turno_abierto(request.user),
        "sobre_tope": importe is not None and importe > parametro("tope_pago_individual"),
        "con_piezas": control_piezas.activo(),
        "piezas": piezas,
    }
    if es_panel(request):
        return render(request, "cobros/panel.html", _contexto_panel(request, titular, contexto), status=status)
    return render(request, "cobros/cobrar.html", contexto, status=status)


def _miembro_de(titular, pago):
    return pago is not None and pago.titular_id in libro.miembros_de(titular)


def _panel_hecho(request, titular, recibo_pk):
    recibo = Recibo.objects.select_related("pago__titular").filter(pk=recibo_pk).first() if str(recibo_pk).isdigit() else None
    if recibo is None or not _miembro_de(titular, recibo.pago):
        return redirect(f"{reverse('cobros:cobrar', args=[titular.pk])}?panel=1")
    from caja.models import MovimientoPiezas

    cambio = sum(m.denominacion * -m.piezas for m in MovimientoPiezas.objects.filter(pago=recibo.pago, origen=MovimientoPiezas.CAMBIO))
    contexto = {"titular": titular, "hecho": recibo, "cambio_entregado": cambio, "estado": {"titulares": [titular]}}
    return render(request, "cobros/panel.html", contexto)


def _panel_transferencia(request, titular):
    desde = request.GET.get("desde", "")
    desde = int(desde) if desde.isdigit() and len(desde) < 19 else 0
    pago = Pago.objects.filter(titular__in=libro.miembros_de(titular), medio=Pago.BANCO, pk__gt=desde).select_related("recibo").order_by("pk").first()
    if pago is not None and hasattr(pago, "recibo"):
        return _panel_hecho(request, titular, pago.recibo.pk)
    return None


def _hecho(request, titular, recibo):
    if es_panel(request):
        return redirect(f"{reverse('cobros:cobrar', args=[titular.pk])}?panel=1&hecho={recibo.pk}")
    return redirect("cobros:recibo", pk=recibo.pk)


def _propuesta(titular, importe, primero=None):
    partes, resto = libro.proponer_reparto(titular, importe, primero)
    cargos = {c.pk: c for c in Cargo.objects.filter(pk__in=[p.cargo for p in partes]).select_related("titular", "concepto")}
    return {"partes": [(cargos[p.cargo], p.importe) for p in partes], "resto": resto}


def _datos_validos(request):
    ficha = request.POST.get("ficha", "")
    texto = request.POST.get("importe", "")
    if not FICHA_VALIDA.match(ficha) or not texto.isdigit() or not 0 < int(texto) < 10 ** 12:
        return None, None
    return ficha, int(texto)


def proponer_cambio(request, turno, recibidas, vuelto):
    sugerida, aviso = {}, ""
    if not vuelto:
        return sugerida, aviso
    with transaction.atomic():
        fresco = Turno.objects.get(pk=turno.pk)
        permitidas = parametro("propuestas_cambio_sin_cobro")
        if fresco.propuestas_cambio - fresco.pagos.count() >= permitidas:
            registrar("propuesta_cambio_limitada", objeto=fresco, request=request, datos={"propuestas": fresco.propuestas_cambio})
            return {}, "Captura las piezas que entregas de cambio."
        Turno.objects.filter(pk=turno.pk).update(propuestas_cambio=F("propuestas_cambio") + 1)
        try:
            sugerida = calculo_cambio.proponer(vuelto, control_piezas.disponibles(fresco, {int(v): c for v, c in recibidas.items()}))
        except calculo_cambio.DemasiadoComplejo:
            sugerida = None
        if sugerida is None:
            return {}, "La caja no tiene las piezas para ese cambio exacto: captura las piezas que entregas."
    return sugerida, aviso


def _cambio(request, titular, turno):
    ficha, importe = _datos_validos(request)
    if ficha is None:
        messages.error(request, "Los datos del pago no son válidos. Vuelve a capturarlo.")
        return redirect("cobros:cobrar", pk=titular.pk)
    piezas = FormularioPiezasCobro(request.POST)
    if not piezas.is_valid():
        return _pantalla_cobro(request, titular, FormularioPago(), _propuesta(titular, importe, _primero(_venta(request, titular))), importe, ficha, piezas={"formulario": piezas})
    return _con_piezas(request, titular, turno, importe, ficha, piezas)


def _con_piezas(request, titular, turno, importe, ficha, piezas):
    recibidas = piezas.piezas_recibidas()
    entregado = control_piezas.total(recibidas)
    if entregado < importe:
        piezas.add_error(None, "Las piezas recibidas no alcanzan el importe del pago.")
        return _pantalla_cobro(request, titular, FormularioPago(initial={"importe": importe}), _propuesta(titular, importe, _primero(_venta(request, titular))), importe, ficha, piezas={"formulario": piezas})
    vuelto = entregado - importe
    sugerida, aviso = proponer_cambio(request, turno, recibidas, vuelto)
    formulario = FormularioPiezasCobro(initial={nombre: recibidas.get(str(valor), 0) for nombre, valor in piezas.recibidas}, con_cambio=bool(vuelto), propuesta=sugerida)
    return _pantalla_cobro(request, titular, FormularioPago(), _propuesta(titular, importe, _primero(_venta(request, titular))), importe, ficha, piezas={"formulario": formulario, "cambio": vuelto, "aviso": aviso, "listo": True})


@requiere_permiso("registrar_pago_efectivo")
def cobrar(request, pk):
    titular = get_object_or_404(Titular.objects.select_related("familia"), pk=pk)
    if titular.estado == Titular.RECHAZADO:
        raise PermissionDenied
    if control_piezas.faltan_para_contar():
        return control_piezas.pantalla_faltan(request, "cobros:buscar")
    turno = turno_abierto(request.user)
    if request.method != "POST":
        if es_panel(request) and request.GET.get("hecho"):
            return _panel_hecho(request, titular, request.GET["hecho"])
        if es_panel(request) and request.GET.get("metodo") == "transferencia":
            llegada = _panel_transferencia(request, titular)
            if llegada is not None:
                return llegada
        return _pantalla_cobro(request, titular, FormularioPago())
    if turno is None:
        messages.error(request, "Abre tu turno de caja antes de cobrar.")
        return redirect("caja:inicio")
    if not recibe_movimientos(turno):
        messages.error(request, "Tu turno está en arqueo: termina de cerrarlo antes de cobrar.")
        return redirect("caja:inicio")
    if request.POST.get("paso") == "confirmar":
        return _confirmar(request, titular, turno)
    if request.POST.get("paso") == "cambio" and control_piezas.activo():
        return _cambio(request, titular, turno)
    if request.POST.get("paso") == "panel" and es_panel(request):
        return _paso_panel(request, titular, turno)
    formulario = FormularioPago(request.POST)
    if not formulario.is_valid():
        return _pantalla_cobro(request, titular, formulario)
    importe = formulario.cleaned_data["importe"]
    piezas = {"formulario": FormularioPiezasCobro()} if control_piezas.activo() else None
    return _pantalla_cobro(request, titular, formulario, _propuesta(titular, importe, _primero(_venta(request, titular))), importe, secrets.token_urlsafe(24), piezas=piezas)


def _paso_panel(request, titular, turno):
    formulario = FormularioPago(request.POST)
    piezas = FormularioPiezasCobro(request.POST) if control_piezas.activo() else None
    if not formulario.is_valid():
        return _pantalla_cobro(request, titular, formulario, piezas={"formulario": piezas} if piezas is not None else None)
    importe = formulario.cleaned_data["importe"]
    ficha = secrets.token_urlsafe(24)
    if piezas is None:
        return _registrar(request, titular, turno, ficha, importe, None)
    if not piezas.is_valid():
        return _pantalla_cobro(request, titular, formulario, piezas={"formulario": piezas})
    if control_piezas.total(piezas.piezas_recibidas()) == importe:
        return _registrar(request, titular, turno, ficha, importe, {"recibidas": piezas.piezas_recibidas(), "cambio": {}})
    return _con_piezas(request, titular, turno, importe, ficha, piezas)


def _piezas_confirmadas(request, titular, importe, ficha):
    if not control_piezas.activo():
        return None, None
    formulario = FormularioPiezasCobro(request.POST, con_cambio=True)
    if formulario.is_valid():
        piezas = {"recibidas": formulario.piezas_recibidas(), "cambio": formulario.piezas_cambio()}
        try:
            control_piezas.validar_cobro(importe, piezas["recibidas"], piezas["cambio"])
            return piezas, None
        except control_piezas.ErrorPiezas as error:
            formulario.add_error(None, str(error))
    vuelto = max(control_piezas.total(formulario.piezas_recibidas()) - importe, 0)
    respuesta = _pantalla_cobro(request, titular, FormularioPago(), _propuesta(titular, importe, _primero(_venta(request, titular))), importe, ficha, piezas={"formulario": formulario, "cambio": vuelto, "listo": True})
    return None, respuesta


def _confirmar(request, titular, turno):
    ficha, importe = _datos_validos(request)
    if ficha is None:
        messages.error(request, "Los datos del pago no son válidos. Vuelve a capturarlo.")
        return redirect("cobros:cobrar", pk=titular.pk)
    existente = Pago.objects.filter(ficha=ficha).select_related("recibo").first()
    if existente is not None:
        messages.info(request, "Ese pago ya estaba registrado; no se cobró dos veces.")
        return _hecho(request, titular, existente.recibo)
    piezas, error_piezas = _piezas_confirmadas(request, titular, importe, ficha)
    if error_piezas is not None:
        return error_piezas
    return _registrar(request, titular, turno, ficha, importe, piezas)


def _registrar(request, titular, turno, ficha, importe, piezas):
    venta = _venta(request, titular)
    if importe > parametro("tope_pago_individual"):
        datos = {"importe": importe, "ficha": ficha}
        if piezas:
            datos["piezas"] = piezas
        if venta is not None:
            datos["venta"] = venta.pk
        try:
            resultado = motor.ejecutar("pago_sobre_tope", request.user, titular, datos, request=request)
        except motor.ErrorSolicitud as error:
            messages.error(request, str(error))
            return redirect("cobros:cobrar", pk=titular.pk)
        if resultado.solicitud is not None:
            messages.warning(request, f"El pago de {formatear(importe)} pasa del tope: quedó como solicitud. Se registrará al autorizarse.")
            return redirect("solicitudes:detalle", pk=resultado.solicitud.pk)
        return _hecho(request, titular, resultado.objeto.recibo)
    try:
        with transaction.atomic():
            pago = libro.registrar_pago(titular, importe, Pago.EFECTIVO, request.user, turno=turno, ficha=ficha, request=request, piezas=piezas, primero=_primero(venta))
            if venta is not None:
                from inventario import servicios as inventario

                inventario.ligar_pago(venta, pago)
    except libro.PagoDuplicado as duplicado:
        messages.info(request, "Ese pago ya estaba registrado; no se cobró dos veces.")
        return _hecho(request, titular, duplicado.pago.recibo)
    except libro.ErrorLibro as error:
        messages.error(request, str(error))
        return redirect("cobros:cobrar", pk=titular.pk)
    if not es_panel(request):
        messages.success(request, f"Pago registrado: recibo {pago.recibo}.")
    return _hecho(request, titular, pago.recibo)


def _datos_recibo(recibo):
    pago = recibo.pago
    aplicaciones = list(pago.aplicaciones.select_related("cargo__titular", "cargo__concepto"))
    return {
        "recibo": recibo,
        "pago": pago,
        "titular": pago.titular,
        "aplicaciones": aplicaciones,
        "a_favor": pago.importe - sum(a.importe for a in aplicaciones),
        "cancelado": hasattr(pago, "reversion"),
        "contacto": contactos.principal(pago.titular),
        "qr": qr.svg(recibo),
    }


@requiere_permiso("ver_titulares")
def recibo(request, pk):
    objeto = get_object_or_404(Recibo.objects.select_related("pago__titular", "pago__reversion"), pk=pk)
    exigir_ingresos_o_propio(request, objeto.pago.registrado_por_id)
    return render(request, "cobros/recibo.html", _datos_recibo(objeto))


MARGEN_INFERIOR_RECIBO = 40
ALTO_CIERRE_RECIBO = 190
ALTO_CANCELADO_RECIBO = 24


def _colores_recibo():
    from configuracion import marca as marca_negocio

    actual = marca_negocio.actual()
    if actual is not None and actual.con_colores:
        valores = marca_negocio.variables(actual.color_principal, actual.color_acento)
        return actual, valores["--tinta"], valores["--suave"], valores["--acento"], valores["--tinte"], valores["--borde"]
    return actual, "#1F1813", "#5C5047", "#C4662E", "#F6E3D6", "#E2D6C6"


def _logo_recibo(actual):
    from reportlab.lib.utils import ImageReader

    from caja import comprobantes
    from configuracion import marca as marca_negocio

    try:
        contenido = marca_negocio.leer_logo(actual)
    except (OSError, comprobantes.ComprobanteInvalido, marca_negocio.MarcaInvalida):
        return None
    return ImageReader(BytesIO(contenido)) if contenido else None


@requiere_permiso("ver_titulares")
def recibo_pdf(request, pk):
    from reportlab.lib.colors import HexColor

    objeto = get_object_or_404(Recibo.objects.select_related("pago__titular", "pago__reversion"), pk=pk)
    exigir_ingresos_o_propio(request, objeto.pago.registrado_por_id)
    datos = _datos_recibo(objeto)
    voc = vocabulario()
    marca_actual, *colores = _colores_recibo()
    tinta, suave, acento, tinte, borde = (HexColor(c) for c in colores)
    memoria = BytesIO()
    tamano = tamano_hoja.tamano()
    hoja = canvas.Canvas(memoria, pagesize=tamano)
    ancho, alto = tamano
    izquierda, derecha = 90, ancho - 90
    y = alto - 80
    negocio = getattr(request, "negocio", None)
    logo = _logo_recibo(marca_actual)
    texto_x = izquierda
    if logo is not None:
        hoja.drawImage(logo, izquierda, y - 38, width=48, height=48, preserveAspectRatio=True, mask="auto")
        texto_x = izquierda + 60
    hoja.setFillColor(tinta)
    hoja.setFont("Helvetica-Bold", 15)
    hoja.drawString(texto_x, y - 6, (negocio.nombre if negocio else "")[:48])
    hoja.setFont("Helvetica", 9)
    hoja.setFillColor(suave)
    hoja.drawString(texto_x, y - 22, "Recibo de pago")
    hoja.drawRightString(derecha, y + 2, "Recibo")
    hoja.setFillColor(tinta)
    hoja.setFont("Helvetica-Bold", 15)
    hoja.drawRightString(derecha, y - 16, f"{objeto}")
    y -= 52
    hoja.setStrokeColor(acento)
    hoja.setLineWidth(2)
    hoja.line(izquierda, y, derecha, y)
    y -= 26

    def reservar(espacio):
        nonlocal y
        if y - espacio < MARGEN_INFERIOR_RECIBO:
            hoja.showPage()
            y = alto - 80

    def renglon(etiqueta, valor, negritas=True):
        nonlocal y
        reservar(26)
        hoja.setFont("Helvetica", 10)
        hoja.setFillColor(suave)
        hoja.drawString(izquierda, y, etiqueta[:70])
        hoja.setFont("Helvetica-Bold" if negritas else "Helvetica", 10)
        hoja.setFillColor(tinta)
        hoja.drawRightString(derecha, y, valor[:60])
        hoja.setStrokeColor(borde)
        hoja.setLineWidth(0.6)
        hoja.line(izquierda, y - 8, derecha, y - 8)
        y -= 26

    renglon("Fecha", libro.fecha_local(datos["pago"].fecha).strftime("%d/%m/%Y"))
    renglon(voc["titular"], datos["titular"].nombre_completo)
    if not datos["titular"].interno:
        renglon(voc["matricula"], datos["titular"].matricula_formateada)
    renglon("Forma de pago", datos["pago"].get_medio_display().capitalize())
    y -= 6
    reservar(46)
    hoja.setFont("Helvetica-Bold", 9)
    hoja.setFillColor(suave)
    hoja.drawString(izquierda, y, "Aplicado a")
    y -= 20
    for aplicacion in datos["aplicaciones"]:
        etiqueta = f"{aplicacion.cargo}"
        if aplicacion.cargo.titular_id != datos["titular"].pk:
            etiqueta += f" ({aplicacion.cargo.titular.nombre_completo})"
        renglon(etiqueta, formatear(aplicacion.importe, pdf=True), negritas=False)
    if datos["a_favor"]:
        renglon("Queda a favor", formatear(datos["a_favor"], pdf=True), negritas=False)
    y -= 8
    reservar(ALTO_CIERRE_RECIBO + (ALTO_CANCELADO_RECIBO if datos["cancelado"] else 0))
    hoja.setFillColor(tinte)
    hoja.roundRect(izquierda, y - 26, derecha - izquierda, 44, 10, fill=1, stroke=0)
    hoja.setFillColor(tinta)
    hoja.setFont("Helvetica-Bold", 11)
    hoja.drawString(izquierda + 14, y - 8, "Importe recibido")
    hoja.setFont("Helvetica-Bold", 17)
    hoja.drawRightString(derecha - 14, y - 10, formatear(datos["pago"].importe, pdf=True))
    y -= 60
    if datos["cancelado"]:
        hoja.setFillColor(HexColor("#A1281C"))
        hoja.setFont("Helvetica-Bold", 18)
        hoja.drawString(izquierda, y, "CANCELADO")
        y -= 24
    lado = qr.dibujar(hoja, objeto, izquierda, y - 78, modulo=2)
    hoja.setFillColor(suave)
    hoja.setFont("Helvetica", 9)
    hoja.drawString(izquierda + lado + 18, y - 14, "Código de verificación")
    hoja.setFillColor(tinta)
    hoja.setFont("Helvetica-Bold", 15)
    hoja.drawString(izquierda + lado + 18, y - 34, objeto.codigo)
    hoja.setFont("Helvetica", 9)
    hoja.setFillColor(suave)
    hoja.drawString(izquierda + lado + 18, y - 52, f"Recibió: {datos['pago'].registrado_por or 'importación automática del banco'}"[:70])
    y -= max(lado, 60) + 24
    hoja.setStrokeColor(borde)
    hoja.setDash(2, 2)
    hoja.line(izquierda, y, derecha, y)
    hoja.setDash()
    y -= 14
    hoja.setFont("Helvetica", 8)
    hoja.drawString(izquierda, y, "Escanea el QR en «Verificar recibo» o usa su código para comprobarlo.")
    hoja.setFillColor(tinta)
    hoja.setFont("Times-Roman", 10)
    hoja.drawRightString(derecha, y, "A R I A S M O S")
    hoja.setFillColor(suave)
    hoja.setFont("Helvetica", 8)
    hoja.drawRightString(derecha - hoja.stringWidth("A R I A S M O S", "Times-Roman", 10) - 4, y, "Hecho con")
    hoja.showPage()
    hoja.save()
    registrar("recibo_pdf", objeto=objeto.pago, titular=objeto.pago.titular_id, request=request, datos={"recibo": str(objeto)})
    respuesta = HttpResponse(memoria.getvalue(), content_type="application/pdf")
    respuesta["Content-Disposition"] = f'inline; filename="recibo-{objeto.serie}-{objeto.folio}.pdf"'
    return respuesta


def _verificaciones_bloqueadas(request):
    desde = timezone.now() - timedelta(hours=1)
    limite = parametro("intentos_verificar_recibo_por_hora")
    fallidas = Evento.objects.filter(accion="recibo_no_reconocido", momento__gte=desde)
    dispositivo = getattr(request, "dispositivo", None)
    if fallidas.filter(usuario=request.user).count() >= limite:
        return "usuario"
    if dispositivo is not None and fallidas.filter(equipo=dispositivo.pk).count() >= limite:
        return "equipo"
    return None


@requiere_permiso("ver_titulares")
def verificar(request):
    formulario = FormularioVerificarRecibo(request.GET or None)
    resultado = None
    if request.GET and formulario.is_valid():
        bloqueo = _verificaciones_bloqueadas(request)
        if bloqueo is not None:
            registrar("verificacion_bloqueada", request=request, datos={"por": bloqueo})
            formulario.add_error(None, f"Hubo demasiadas verificaciones fallidas en la última hora. Espera un rato o pide ayuda a {quienes('recibir_efectivo')}.")
        else:
            datos = formulario.cleaned_data
            objeto = Recibo.objects.filter(serie=datos["serie"], folio=datos["numero"]).select_related("pago__titular", "pago__reversion").first()
            codigo = datos["codigo_limpio"]
            coincide = secrets.compare_digest(objeto.codigo if objeto is not None else "XXXXX-XXXXX", codigo) and objeto is not None
            valido = coincide and libro.recibo_valido(objeto)
            resultado = {"valido": valido, "recibo": objeto if valido else None, "cancelado": valido and hasattr(objeto.pago, "reversion")}
            evento = "recibo_verificado" if valido else "recibo_no_reconocido"
            registrar(evento, request=request, datos={"folio": f"{datos['serie']}-{datos['numero']}", "valido": valido, "por_qr": (request.GET.get("codigo") or "").strip().upper().startswith("AR1|")})
    return render(request, "cobros/verificar.html", {"formulario": formulario, "resultado": resultado})


@requiere_permiso("cargo_manual")
def cargo_manual(request, pk):
    titular = get_object_or_404(Titular, pk=pk)
    if titular.estado not in (Titular.ACTIVO, Titular.PENDIENTE):
        raise PermissionDenied
    formulario = FormularioCargoManual(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        concepto = datos["concepto"]
        precio = tarifas.precio(concepto, titular)
        unitario = datos.get("importe_unitario") or precio
        error_cantidad = tarifas.error_cargo(concepto, titular, datos["cantidad"])
        if error_cantidad:
            formulario.add_error("cantidad", error_cantidad)
        elif unitario != precio and not request.user.tiene_permiso_de_rol("aplicar_ajustes"):
            registrar("cargo_manual_importe_rechazado", objeto=titular, request=request, datos={"concepto": str(concepto), "importe_pedido": unitario})
            formulario.add_error("importe_unitario", "Cambiar el importe del concepto requiere el permiso de ajustes.")
        elif unitario <= 0:
            formulario.add_error("importe_unitario", "El concepto no tiene importe: escribe uno (requiere el permiso de ajustes).")
        elif rezagos.sin_credito(titular):
            respuesta, error = rezagos.solicitar_cargo(request, titular, concepto, datos["cantidad"], unitario)
            if respuesta is not None:
                return respuesta
            formulario.add_error(None, error)
        else:
            cantidad = datos["cantidad"]
            descripcion = tarifas.descripcion_cargo(concepto, cantidad)
            libro.crear_cargo(titular, concepto, unitario * cantidad, hoy_negocio(), Cargo.MANUAL, descripcion=descripcion, cantidad=cantidad, usuario=request.user, request=request)
            messages.success(request, f"Cargo agregado: {descripcion} por {formatear(unitario * cantidad)}.")
            return redirect("titulares:detalle", pk=pk)
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"Cargo manual a {titular}", "boton": "Agregar cargo"})


def _ejecutar(request, accion, titular, datos, regreso):
    try:
        resultado = motor.ejecutar(accion, request.user, titular, datos, request=request)
    except motor.ErrorSolicitud as error:
        messages.error(request, str(error))
        return None
    if resultado.solicitud is not None:
        messages.info(request, "Quedó como solicitud pendiente de autorización.")
        return redirect("solicitudes:detalle", pk=resultado.solicitud.pk)
    messages.success(request, "Aplicado." if resultado.via == "directa" else "Aplicado con tu delegación temporal.")
    return redirect(regreso, pk=titular.pk)


CAMPOS_PROHIBIDOS_BECA = ("tipo", "importe", "importe_fijo", "valor", "fijo", "puntos_base")


@requiere_permiso(*AJUSTES)
def beca(request, pk):
    titular = get_object_or_404(Titular, pk=pk)
    if titular.estado == Titular.RECHAZADO:
        raise PermissionDenied
    if request.method == "POST" and any(campo in request.POST for campo in CAMPOS_PROHIBIDOS_BECA):
        registrar("beca_rechazada", objeto=titular, request=request, datos={"motivo": "campos_no_permitidos", "campos": sorted(c for c in CAMPOS_PROHIBIDOS_BECA if c in request.POST)})
        return HttpResponse(f"{vocabulario()['descuentos']}: solo se admite porcentaje.", status=400, content_type="text/plain; charset=utf-8")
    formulario = FormularioBeca(request.POST if request.method == "POST" else None, initial={"desde": hoy_negocio()})
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        carga = {
            "concepto": datos["concepto"].pk,
            "puntos_base": datos["porcentaje"],
            "desde": datos["desde"].isoformat(),
            "hasta": datos["hasta"].isoformat() if datos.get("hasta") else None,
            "motivo": datos["motivo"],
        }
        respuesta = _ejecutar(request, "beca", titular, carga, "titulares:detalle")
        if respuesta is not None:
            return respuesta
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"{vocabulario()['descuento']} para {titular}", "boton": "Enviar"})


@requiere_permiso(*AJUSTES)
def prorroga(request, pk):
    cargo = get_object_or_404(Cargo.objects.select_related("titular"), pk=pk)
    formulario = FormularioProrroga(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        carga = {"cargo": cargo.pk, "fecha_limite": formulario.cleaned_data["fecha_limite"].isoformat(), "motivo": formulario.cleaned_data["motivo"]}
        respuesta = _ejecutar(request, "prorroga", cargo.titular, carga, "titulares:detalle")
        if respuesta is not None:
            return respuesta
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"Prórroga de {cargo} ({cargo.titular})", "boton": "Enviar"})


@requiere_permiso(*AJUSTES)
def cancelar(request, pk):
    cargo = get_object_or_404(Cargo.objects.select_related("titular"), pk=pk)
    accion = "condonar_recargo" if cargo.origen == Cargo.RECARGO else "cancelar_cargo"
    formulario = FormularioCancelacion(request.POST if request.method == "POST" else None, initial={"importe": libro.saldo_de(cargo)})
    if request.method == "POST" and formulario.is_valid():
        carga = {"cargo": cargo.pk, "importe": formulario.cleaned_data["importe"], "motivo": formulario.cleaned_data["motivo"]}
        respuesta = _ejecutar(request, accion, cargo.titular, carga, "titulares:detalle")
        if respuesta is not None:
            return respuesta
    titulo = f"{'Condonar' if accion == 'condonar_recargo' else 'Cancelar'} {cargo} ({cargo.titular}) · saldo {formatear(libro.saldo_de(cargo))}"
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": titulo, "boton": "Enviar"})


@requiere_permiso(*AJUSTES)
def revertir(request, pk):
    pago = get_object_or_404(Pago.objects.select_related("titular", "recibo"), pk=pk)
    exigir_ingresos_o_propio(request, pago.registrado_por_id)
    formulario = FormularioReversion(request.POST if request.method == "POST" else None)
    if pago.medio == Pago.EFECTIVO and control_piezas.faltan_para_contar():
        return control_piezas.pantalla_faltan(request)
    nombres = control_piezas.campos(formulario, "p_", "Piezas que devuelves:") if pago.medio == Pago.EFECTIVO and control_piezas.activo() else []
    formulario.titulo_piezas = "Billetes y monedas que devuelves"
    formulario.ayuda_piezas = f"deben sumar {formatear(pago.importe)}"
    renglones = []
    venta = getattr(pago, "venta", None) if hasattr(pago, "venta") else None
    if venta is not None:
        for renglon in venta.renglones.select_related("articulo"):
            nombre = f"regreso_{renglon.pk}"
            formulario.fields[nombre] = forms.BooleanField(label=f"¿Regresó {renglon.articulo.nombre} × {renglon.cantidad}?", required=False)
            renglones.append((nombre, renglon.pk))
    if request.method == "POST" and formulario.is_valid():
        datos = {"pago": pago.pk, "motivo": formulario.cleaned_data["motivo"]}
        if renglones:
            datos["regresan"] = [pk for nombre, pk in renglones if formulario.cleaned_data.get(nombre)]
        if nombres:
            datos["piezas"] = control_piezas.leer(formulario.cleaned_data, nombres)
            if control_piezas.total(datos["piezas"]) != pago.importe:
                formulario.add_error(None, "Las piezas que devuelves deben sumar exactamente el importe del pago.")
        if not formulario.errors:
            respuesta = _ejecutar(request, "revertir_pago", pago.titular, datos, "titulares:detalle")
            if respuesta is not None:
                if pago.titular.interno and respuesta.status_code == 302 and "/solicitudes/" not in respuesta.url:
                    return redirect("cobros:recibo", pk=pago.recibo.pk)
                return respuesta
    titulo = f"Revertir el pago {pago.recibo} de {formatear(pago.importe)} ({pago.titular})"
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": titulo, "boton": "Enviar"})
