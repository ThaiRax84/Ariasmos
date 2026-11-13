import re
import secrets
from io import BytesIO

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from auditoria.servicios import registrar
from caja.servicios import turno_abierto
from configuracion.models import hoy_negocio, parametro, vocabulario
from cuentas.decoradores import requiere_permiso
from nucleo.dinero import formatear
from nucleo.matricula import normalizar
from solicitudes import motor
from titulares import contactos
from titulares.models import Titular

from . import libro
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


def _pantalla_cobro(request, titular, formulario, propuesta=None, importe=None, ficha=None, status=200):
    miembros = _miembros(titular)
    contexto = {
        "titular": titular,
        "formulario": formulario,
        "estado": estado_cuenta(miembros),
        "propuesta": propuesta,
        "importe": importe,
        "ficha": ficha,
        "turno": turno_abierto(request.user),
        "sobre_tope": importe is not None and importe > parametro("tope_pago_individual"),
    }
    return render(request, "cobros/cobrar.html", contexto, status=status)


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
    if request.POST.get("paso") == "confirmar":
        return _confirmar(request, titular, turno)
    formulario = FormularioPago(request.POST)
    if not formulario.is_valid():
        return _pantalla_cobro(request, titular, formulario)
    importe = formulario.cleaned_data["importe"]
    partes, resto = libro.proponer_reparto(titular, importe)
    cargos = {c.pk: c for c in Cargo.objects.filter(pk__in=[p.cargo for p in partes]).select_related("titular", "concepto")}
    propuesta = {"partes": [(cargos[p.cargo], p.importe) for p in partes], "resto": resto}
    return _pantalla_cobro(request, titular, formulario, propuesta, importe, secrets.token_urlsafe(24))


def _confirmar(request, titular, turno):
    ficha = request.POST.get("ficha", "")
    texto = request.POST.get("importe", "")
    if not FICHA_VALIDA.match(ficha) or not texto.isdigit() or not 0 < int(texto) < 10 ** 12:
        messages.error(request, "Los datos del pago no son válidos. Vuelve a capturarlo.")
        return redirect("cobros:cobrar", pk=titular.pk)
    importe = int(texto)
    existente = Pago.objects.filter(ficha=ficha).select_related("recibo").first()
    if existente is not None:
        messages.info(request, "Ese pago ya estaba registrado; no se cobró dos veces.")
        return redirect("cobros:recibo", pk=existente.recibo.pk)
    if importe > parametro("tope_pago_individual"):
        try:
            resultado = motor.ejecutar("pago_sobre_tope", request.user, titular, {"importe": importe, "ficha": ficha}, request=request)
        except motor.ErrorSolicitud as error:
            messages.error(request, str(error))
            return redirect("cobros:cobrar", pk=titular.pk)
        if resultado.solicitud is not None:
            messages.warning(request, f"El pago de {formatear(importe)} pasa del tope: quedó como solicitud. Se registrará al autorizarse.")
            return redirect("solicitudes:detalle", pk=resultado.solicitud.pk)
        return redirect("cobros:recibo", pk=resultado.objeto.recibo.pk)
    try:
        pago = libro.registrar_pago(titular, importe, Pago.EFECTIVO, request.user, turno=turno, ficha=ficha, request=request)
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
        (12, f"Importe: {formatear(datos['pago'].importe)}"),
    ]
    for aplicacion in datos["aplicaciones"]:
        lineas.append((10, f"  {aplicacion.cargo} ({aplicacion.cargo.titular.nombre_completo}): {formatear(aplicacion.importe)}"))
    if datos["a_favor"]:
        lineas.append((10, f"  Queda a favor: {formatear(datos['a_favor'])}"))
    lineas.append((10, f"Código de verificación: {objeto.codigo}"))
    if datos["cancelado"]:
        lineas.append((16, "CANCELADO"))
    for tamano, texto in lineas:
        hoja.setFont("Helvetica-Bold" if tamano >= 12 else "Helvetica", tamano)
        hoja.drawString(72, y, texto[:110])
        y -= tamano + 8
    hoja.showPage()
    hoja.save()
    registrar("recibo_pdf", objeto=objeto.pago, titular=objeto.pago.titular_id, request=request, datos={"recibo": str(objeto)})
    respuesta = HttpResponse(memoria.getvalue(), content_type="application/pdf")
    respuesta["Content-Disposition"] = f'inline; filename="recibo-{objeto.serie}-{objeto.folio}.pdf"'
    return respuesta


@requiere_permiso("ver_titulares")
def verificar(request):
    formulario = FormularioVerificarRecibo(request.GET or None)
    resultado = None
    if request.GET and formulario.is_valid():
        serie, folio = formulario.cleaned_data["folio"].upper().split("-")
        codigo = formulario.cleaned_data["codigo"].strip().upper()
        objeto = Recibo.objects.filter(serie=serie, folio=int(folio)).select_related("pago__titular", "pago__reversion").first()
        valido = objeto is not None and secrets.compare_digest(objeto.codigo, codigo) and libro.recibo_valido(objeto)
        resultado = {"valido": valido, "recibo": objeto if valido else None, "cancelado": valido and hasattr(objeto.pago, "reversion")}
        registrar("recibo_verificado", request=request, datos={"folio": formulario.cleaned_data["folio"], "valido": valido})
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
    if request.method == "POST" and formulario.is_valid():
        respuesta = _ejecutar(request, "revertir_pago", pago.titular, {"pago": pago.pk, "motivo": formulario.cleaned_data["motivo"]}, "titulares:detalle")
        if respuesta is not None:
            return respuesta
    titulo = f"Revertir el pago {pago.recibo} de {formatear(pago.importe)} ({pago.titular})"
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": titulo, "boton": "Enviar"})
