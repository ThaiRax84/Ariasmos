import re
import secrets
from datetime import timedelta
from io import BytesIO

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from auditoria.models import Evento
from auditoria.servicios import registrar
from caja import cambio as calculo_cambio
from caja import piezas as control_piezas
from caja.formularios import FormularioPiezasCobro
from caja.models import Turno
from caja.servicios import recibe_movimientos, turno_abierto
from configuracion.models import hoy_negocio, parametro, vocabulario
from cuentas.decoradores import requiere_permiso
from configuracion.moneda import formatear
from nucleo.matricula import normalizar
from solicitudes import motor
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
    consulta = request.GET.get("q", "").strip()
    resultados = []
    if consulta:
        digitos = normalizar(consulta)
        filtro = Q(nombre__icontains=consulta) | Q(apellidos__icontains=consulta)
        if digitos:
            filtro |= Q(matricula__startswith=digitos)
        resultados = Titular.objects.filter(filtro).exclude(estado=Titular.RECHAZADO).select_related("familia")[:30]
    return render(request, "cobros/buscar.html", {"q": consulta, "resultados": resultados, "turno": turno_abierto(request.user)})


def _venta(request, titular):
    from inventario import servicios as inventario

    valor = request.POST.get("venta") if request.method == "POST" else request.GET.get("venta")
    return inventario.venta_por_cobrar(titular, valor) if valor else None


def _primero(venta):
    from inventario import servicios as inventario

    return inventario.cargos_de(venta) if venta is not None else None


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
    return render(request, "cobros/cobrar.html", contexto, status=status)


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
    recibidas = piezas.piezas_recibidas()
    entregado = control_piezas.total(recibidas)
    if entregado < importe:
        piezas.add_error(None, "Las piezas recibidas no alcanzan el importe del pago.")
        return _pantalla_cobro(request, titular, FormularioPago(), _propuesta(titular, importe, _primero(_venta(request, titular))), importe, ficha, piezas={"formulario": piezas})
    vuelto = entregado - importe
    sugerida, aviso = proponer_cambio(request, turno, recibidas, vuelto)
    formulario = FormularioPiezasCobro(initial={nombre: recibidas.get(str(valor), 0) for nombre, valor in piezas.recibidas}, con_cambio=bool(vuelto), propuesta=sugerida)
    return _pantalla_cobro(request, titular, FormularioPago(), _propuesta(titular, importe, _primero(_venta(request, titular))), importe, ficha, piezas={"formulario": formulario, "cambio": vuelto, "aviso": aviso, "listo": True})


@requiere_permiso("registrar_pago_efectivo")
def cobrar(request, pk):
    titular = get_object_or_404(Titular.objects.select_related("familia"), pk=pk)
    if titular.estado == Titular.RECHAZADO:
        raise PermissionDenied
    turno = turno_abierto(request.user)
    if request.method != "POST":
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
    formulario = FormularioPago(request.POST)
    if not formulario.is_valid():
        return _pantalla_cobro(request, titular, formulario)
    importe = formulario.cleaned_data["importe"]
    piezas = {"formulario": FormularioPiezasCobro()} if control_piezas.activo() else None
    return _pantalla_cobro(request, titular, formulario, _propuesta(titular, importe, _primero(_venta(request, titular))), importe, secrets.token_urlsafe(24), piezas=piezas)


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
        return redirect("cobros:recibo", pk=existente.recibo.pk)
    piezas, error_piezas = _piezas_confirmadas(request, titular, importe, ficha)
    if error_piezas is not None:
        return error_piezas
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
        return redirect("cobros:recibo", pk=resultado.objeto.recibo.pk)
    try:
        with transaction.atomic():
            pago = libro.registrar_pago(titular, importe, Pago.EFECTIVO, request.user, turno=turno, ficha=ficha, request=request, piezas=piezas, primero=_primero(venta))
            if venta is not None:
                from inventario import servicios as inventario

                inventario.ligar_pago(venta, pago)
    except libro.PagoDuplicado as duplicado:
        messages.info(request, "Ese pago ya estaba registrado; no se cobró dos veces.")
        return redirect("cobros:recibo", pk=duplicado.pago.recibo.pk)
    except libro.ErrorLibro as error:
        messages.error(request, str(error))
        return redirect("cobros:cobrar", pk=titular.pk)
    messages.success(request, f"Pago registrado: recibo {pago.recibo}.")
    return redirect("cobros:recibo", pk=pago.recibo.pk)


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
    return render(request, "cobros/recibo.html", _datos_recibo(objeto))


@requiere_permiso("ver_titulares")
def recibo_pdf(request, pk):
    objeto = get_object_or_404(Recibo.objects.select_related("pago__titular", "pago__reversion"), pk=pk)
    datos = _datos_recibo(objeto)
    voc = vocabulario()
    memoria = BytesIO()
    hoja = canvas.Canvas(memoria, pagesize=letter)
    ancho, alto = letter
    y = alto - 72
    negocio = getattr(request, "negocio", None)
    lineas = [
        (14, negocio.nombre if negocio else ""),
        (12, f"Recibo {objeto}"),
        (10, f"Fecha: {libro.fecha_local(datos['pago'].fecha).strftime('%d/%m/%Y')}"),
        (10, f"{voc['titular']}: {datos['titular'].nombre_completo} · {voc['matricula']} {datos['titular'].matricula_formateada}"),
        (12, f"Importe: {formatear(datos['pago'].importe, pdf=True)}"),
    ]
    for aplicacion in datos["aplicaciones"]:
        lineas.append((10, f"  {aplicacion.cargo} ({aplicacion.cargo.titular.nombre_completo}): {formatear(aplicacion.importe, pdf=True)}"))
    if datos["a_favor"]:
        lineas.append((10, f"  Queda a favor: {formatear(datos['a_favor'], pdf=True)}"))
    lineas.append((10, f"Código de verificación: {objeto.codigo}"))
    if datos["cancelado"]:
        lineas.append((16, "CANCELADO"))
    for tamano, texto in lineas:
        hoja.setFont("Helvetica-Bold" if tamano >= 12 else "Helvetica", tamano)
        hoja.drawString(72, y, texto[:110])
        y -= tamano + 8
    qr.dibujar(hoja, objeto, 72, y - 110)
    hoja.setFont("Helvetica", 8)
    hoja.drawString(72, y - 122, "Escanea el QR en «Verificar recibo» para comprobarlo.")
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
            formulario.add_error(None, "Hubo demasiadas verificaciones fallidas en la última hora. Espera un rato o pide ayuda a Supervisión.")
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
        unitario = datos.get("importe_unitario") or concepto.importe_centavos
        if unitario != concepto.importe_centavos and not request.user.tiene_permiso_de_rol("aplicar_ajustes"):
            registrar("cargo_manual_importe_rechazado", objeto=titular, request=request, datos={"concepto": str(concepto), "importe_pedido": unitario})
            formulario.add_error("importe_unitario", "Cambiar el importe del concepto requiere el permiso de ajustes.")
        elif unitario <= 0:
            formulario.add_error("importe_unitario", "El concepto no tiene importe: escribe uno (requiere el permiso de ajustes).")
        else:
            cantidad = datos["cantidad"]
            descripcion = f"{concepto} × {cantidad}" if cantidad > 1 else str(concepto)
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
        return HttpResponse("Las becas solo admiten porcentaje.", status=400, content_type="text/plain; charset=utf-8")
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
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"Beca para {titular}", "boton": "Enviar"})


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
    formulario = FormularioReversion(request.POST if request.method == "POST" else None)
    nombres = control_piezas.campos(formulario, "p_", "Piezas que devuelves:") if pago.medio == Pago.EFECTIVO and control_piezas.activo() else []
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
