import secrets
from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.forms.models import model_to_dict
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from auditoria.servicios import diferencias, registrar
from banco import lectura
from caja import comprobantes
from caja import piezas as control_piezas
from caja.formularios import FormularioPiezasCobro
from caja.servicios import recibe_movimientos, turno_abierto
from cobros import libro
from cobros.formularios import FormularioVerificarRecibo
from cobros.models import Recibo
from cobros.vistas_cobro import _verificaciones_bloqueadas, proponer_cambio
from configuracion.models import parametro
from cuentas.decoradores import requiere_permiso
from nucleo.matricula import normalizar
from titulares.models import Titular

from . import servicios
from .formularios import (
    FormularioArticulo,
    FormularioBuscarVenta,
    FormularioCapturaConteo,
    FormularioComprobante,
    FormularioDevolucion,
    FormularioRegistro,
    FormularioRevision,
    FormularioSubirConteo,
    FormularioVenta,
)
from .models import POR_REVISAR, Articulo, Conteo, Devolucion, RegistroInventario, RenglonVenta, Venta

TODOS = ("vender_articulos", "registrar_movimientos_inventario", "subir_conteo_inventario", "devolver_articulos", "revisar_inventario", "administrar_articulos")
VEN_VENTAS = ("vender_articulos", "devolver_articulos", "revisar_inventario")
VEN_EXISTENCIAS = ("revisar_inventario", "administrar_articulos")
REGISTROS = ("registrar_movimientos_inventario", "revisar_inventario")
CONTEOS = ("subir_conteo_inventario", "revisar_inventario", "aprobar_solicitudes")


def encendido(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not servicios.activo():
            raise Http404
        return vista(request, *args, **kwargs)

    return envoltura


def _ve_existencias(usuario):
    return any(usuario.tiene_permiso(p) for p in VEN_EXISTENCIAS)


@requiere_permiso(*TODOS)
@encendido
def indice(request):
    articulos = list(Articulo.objects.filter(activo=True).select_related("concepto").order_by("nombre"))
    ve = _ve_existencias(request.user)
    actuales = servicios.existencias() if ve else {}
    filas = [{"articulo": a, "existencia": actuales.get(a.pk, 0) if ve else None, "bajo": ve and actuales.get(a.pk, 0) <= a.minimo} for a in articulos]
    return render(request, "inventario/indice.html", {"filas": filas, "ve_existencias": ve, "en_espera": servicios.conteo_en_espera()})


@requiere_permiso("administrar_articulos")
@encendido
def articulos(request):
    return render(request, "inventario/articulos.html", {"articulos": Articulo.objects.select_related("concepto").order_by("-activo", "nombre")})


def _guardar_articulo(request, objeto=None):
    antes = model_to_dict(objeto) if objeto else {}
    formulario = FormularioArticulo(request.POST if request.method == "POST" else None, instance=objeto)
    if request.method == "POST" and formulario.is_valid():
        with transaction.atomic():
            guardado = formulario.save()
            registrar("articulo_cambiado" if objeto else "articulo_creado", usuario=request.user, objeto=guardado, datos={"clave": guardado.clave, "cambios": diferencias(antes, model_to_dict(guardado))}, request=request)
        messages.success(request, "Artículo guardado.")
        return redirect("inventario:articulos")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"Artículo {objeto}" if objeto else "Artículo nuevo", "boton": "Guardar", "volver": "inventario:articulos"})


@requiere_permiso("administrar_articulos")
@encendido
def articulo_nuevo(request):
    return _guardar_articulo(request)


@requiere_permiso("administrar_articulos")
@encendido
def articulo_editar(request, pk):
    return _guardar_articulo(request, get_object_or_404(Articulo, pk=pk))


@requiere_permiso("vender_articulos")
@encendido
def vender(request):
    consulta = request.GET.get("q", "").strip()[:60]
    resultados = []
    if consulta:
        digitos = normalizar(consulta)
        filtro = Q(nombre__icontains=consulta) | Q(apellidos__icontains=consulta)
        if digitos:
            filtro |= Q(matricula__startswith=digitos)
        resultados = Titular.objects.filter(filtro).filter(estado__in=[Titular.ACTIVO, Titular.PENDIENTE]).select_related("familia")[:30]
    return render(request, "inventario/vender.html", {"q": consulta, "resultados": resultados})


@requiere_permiso("vender_articulos")
@encendido
def vender_titular(request, pk):
    titular = get_object_or_404(Titular, pk=pk)
    if titular.estado not in (Titular.ACTIVO, Titular.PENDIENTE):
        raise PermissionDenied
    formulario = FormularioVenta(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        try:
            venta = servicios.vender(titular, formulario.cleaned_data["renglones"], formulario.cleaned_data["modo"], request.user, request)
        except servicios.ErrorInventario as error:
            formulario.add_error(None, str(error))
        else:
            _avisar_sin_existencia(request, venta)
            if venta.modo == Venta.AHORA and request.user.tiene_permiso("registrar_pago_efectivo"):
                messages.success(request, f"Venta {venta} registrada: cobra ahora; el pago se aplica primero a estos artículos.")
                return redirect(reverse("cobros:cobrar", args=[titular.pk]) + f"?venta={venta.pk}")
            messages.success(request, f"Venta {venta} registrada{' y cargada a su adeudo' if venta.modo == Venta.ADEUDO else ''}.")
            return redirect("inventario:venta", pk=venta.pk)
    return render(request, "inventario/venta_nueva.html", {"formulario": formulario, "titular": titular, "catalogo": servicios.para_vender()})


def _avisar_sin_existencia(request, venta):
    faltan = [r.articulo.nombre for r in venta.renglones.filter(sin_existencia=True).select_related("articulo")]
    if faltan:
        messages.warning(request, f"La existencia del sistema no alcanzaba para: {', '.join(faltan)}. La venta quedó registrada y Supervisión la revisará.")


def _renglones_ocultos(formulario):
    return [(campo, formulario.data.get(campo, "")) for par in formulario.lineas for campo in par if formulario.data.get(campo)]


def _pantalla_publico(request, formulario, turno, **extra):
    contexto = {"formulario": formulario, "turno": turno, "publico": True, "con_piezas": control_piezas.activo(), "catalogo": servicios.para_vender(), **extra}
    if formulario.is_bound and formulario.is_valid():
        contexto["ocultos"] = _renglones_ocultos(formulario)
    return render(request, "inventario/venta_nueva.html", contexto)


@requiere_permiso("vender_articulos")
@encendido
def vender_publico(request):
    turno = turno_abierto(request.user)
    formulario = FormularioVenta(request.POST if request.method == "POST" else None, con_modo=False)
    if request.method != "POST":
        return _pantalla_publico(request, formulario, turno)
    if turno is None or not recibe_movimientos(turno):
        messages.error(request, "Abre tu turno de caja (fuera de arqueo) para vender sin matrícula.")
        return redirect("caja:inicio")
    if not formulario.is_valid():
        return _pantalla_publico(request, formulario, turno)
    renglones = formulario.cleaned_data["renglones"]
    try:
        total = servicios.total_de(renglones)
    except servicios.ErrorInventario as error:
        formulario.add_error(None, str(error))
        return _pantalla_publico(request, formulario, turno)
    paso = request.POST.get("paso", "")
    ficha = request.POST.get("ficha", "")
    if paso == "":
        ficha = secrets.token_urlsafe(24)
        piezas = {"formulario": FormularioPiezasCobro()} if control_piezas.activo() else None
        return _pantalla_publico(request, formulario, turno, total=total, ficha=ficha, piezas=piezas)
    if not ficha or len(ficha) > 64 or not ficha.replace("-", "").replace("_", "").isalnum():
        messages.error(request, "Los datos de la venta no son válidos. Vuelve a capturarla.")
        return redirect("inventario:vender_publico")
    if paso == "cambio" and control_piezas.activo():
        captura = FormularioPiezasCobro(request.POST)
        if not captura.is_valid():
            return _pantalla_publico(request, formulario, turno, total=total, ficha=ficha, piezas={"formulario": captura})
        recibidas = captura.piezas_recibidas()
        entregado = control_piezas.total(recibidas)
        if entregado < total:
            captura.add_error(None, "Las piezas recibidas no alcanzan el total de la venta.")
            return _pantalla_publico(request, formulario, turno, total=total, ficha=ficha, piezas={"formulario": captura})
        vuelto = entregado - total
        sugerida, aviso = proponer_cambio(request, turno, recibidas, vuelto)
        siguiente = FormularioPiezasCobro(initial={nombre: recibidas.get(str(valor), 0) for nombre, valor in captura.recibidas}, con_cambio=bool(vuelto), propuesta=sugerida)
        return _pantalla_publico(request, formulario, turno, total=total, ficha=ficha, piezas={"formulario": siguiente, "cambio": vuelto, "aviso": aviso, "listo": True})
    if paso != "confirmar":
        return redirect("inventario:vender_publico")
    piezas = None
    if control_piezas.activo():
        captura = FormularioPiezasCobro(request.POST, con_cambio=True)
        if not captura.is_valid():
            return _pantalla_publico(request, formulario, turno, total=total, ficha=ficha, piezas={"formulario": captura, "listo": True})
        piezas = {"recibidas": captura.piezas_recibidas(), "cambio": captura.piezas_cambio()}
    try:
        venta = servicios.vender_publico(renglones, request.user, turno, ficha, piezas=piezas, request=request)
    except libro.PagoDuplicado as duplicado:
        messages.info(request, "Esa venta ya estaba registrada; no se cobró dos veces.")
        return redirect("cobros:recibo", pk=duplicado.pago.recibo.pk)
    except (servicios.ErrorInventario, libro.ErrorLibro) as error:
        formulario.add_error(None, str(error))
        return _pantalla_publico(request, formulario, turno, total=total, ficha=secrets.token_urlsafe(24), piezas={"formulario": FormularioPiezasCobro()} if control_piezas.activo() else None)
    _avisar_sin_existencia(request, venta)
    messages.success(request, f"Venta {venta} cobrada: recibo {venta.pago.recibo}.")
    return redirect("cobros:recibo", pk=venta.pago.recibo.pk)


@requiere_permiso(*VEN_VENTAS)
@encendido
def ventas(request):
    return render(request, "inventario/ventas.html", {"ventas": servicios.ventas_recientes()})


@requiere_permiso(*VEN_VENTAS)
@encendido
def venta(request, pk):
    objeto = get_object_or_404(Venta.objects.select_related("titular", "usuario", "pago__recibo"), pk=pk)
    libres = servicios.disponibles(objeto, incluir_pendientes=True)
    renglones = [{"renglon": r, "disponible": libres.get(r.pk, 0), "saldo": libro.saldo_de(r.cargo)} for r in objeto.renglones.select_related("articulo", "cargo")]
    contexto = {
        "venta": objeto,
        "renglones": renglones,
        "devoluciones": objeto.devoluciones.select_related("usuario", "autorizada_por", "pago_credito__recibo"),
        "puede_devolver": request.user.tiene_permiso("devolver_articulos") and bool(parametro("devoluciones_inventario")) and servicios.en_plazo(objeto) and any(f["disponible"] for f in renglones),
        "puede_cobrar": objeto.modo == Venta.AHORA and objeto.pago_id is None and not objeto.titular.interno and request.user.tiene_permiso("registrar_pago_efectivo"),
    }
    return render(request, "inventario/venta.html", contexto)


@requiere_permiso("devolver_articulos")
@encendido
def devolver(request):
    formulario = FormularioBuscarVenta(request.GET or None)
    if request.GET and formulario.is_valid():
        datos = formulario.cleaned_data
        if datos.get("venta"):
            encontrada = servicios.buscar_venta(datos["venta"])
            if encontrada is None:
                formulario.add_error("venta", "No hay una venta con ese número.")
            else:
                return redirect("inventario:devolver_venta", pk=encontrada.pk)
        elif datos.get("codigo"):
            encontrada = _venta_por_recibo(request, formulario)
            if encontrada is not None:
                return redirect("inventario:devolver_venta", pk=encontrada.pk)
        else:
            formulario.add_error(None, "Escribe el número de venta o el código del recibo.")
    return render(request, "inventario/devolver.html", {"formulario": formulario, "devoluciones_activas": bool(parametro("devoluciones_inventario"))})


def _venta_por_recibo(request, formulario):
    verificacion = FormularioVerificarRecibo({"codigo": formulario.cleaned_data.get("codigo", ""), "folio": formulario.cleaned_data.get("folio", "")})
    if not verificacion.is_valid():
        formulario.add_error(None, "; ".join(e for errores in verificacion.errors.values() for e in errores))
        return None
    bloqueo = _verificaciones_bloqueadas(request)
    if bloqueo is not None:
        registrar("verificacion_bloqueada", request=request, datos={"por": bloqueo, "desde": "devolucion"})
        formulario.add_error(None, "Hubo demasiadas verificaciones fallidas en la última hora. Busca por número de venta o pide ayuda a Supervisión.")
        return None
    datos = verificacion.cleaned_data
    recibo = Recibo.objects.filter(serie=datos["serie"], folio=datos["numero"]).select_related("pago").first()
    valido = recibo is not None and secrets.compare_digest(recibo.codigo, datos["codigo_limpio"]) and libro.recibo_valido(recibo)
    registrar("recibo_verificado" if valido else "recibo_no_reconocido", request=request, datos={"folio": f"{datos['serie']}-{datos['numero']}", "valido": valido, "desde": "devolucion"})
    if not valido:
        formulario.add_error(None, "El recibo no se reconoce.")
        return None
    encontrada = servicios.venta_de_recibo(recibo)
    if encontrada is None:
        formulario.add_error(None, "Ese recibo no corresponde a una venta de artículos.")
    return encontrada


@requiere_permiso("devolver_articulos")
@encendido
def devolver_venta(request, pk):
    objeto = get_object_or_404(Venta.objects.select_related("titular", "pago"), pk=pk)
    if not parametro("devoluciones_inventario"):
        messages.error(request, "El negocio no acepta devoluciones de artículos.")
        return redirect("inventario:venta", pk=pk)
    if not servicios.en_plazo(objeto):
        messages.error(request, "La venta está fuera del plazo de devolución.")
        return redirect("inventario:venta", pk=pk)
    renglones = list(objeto.renglones.select_related("articulo", "cargo"))
    formulario = FormularioDevolucion(request.POST if request.method == "POST" else None, renglones=renglones, disponibles=servicios.disponibles(objeto, incluir_pendientes=True), publico=objeto.titular.interno)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            if datos["medio"] == Devolucion.EFECTIVO:
                servicios.validar_devolucion(objeto, datos["cantidades"], incluir_pendientes=True)
                resultado = servicios.solicitar_efectivo(objeto, datos["cantidades"], request.user, datos["motivo"], formulario.piezas(), request)
                messages.info(request, "La devolución en efectivo quedó como solicitud: la autoriza otra persona y el efectivo sale de tu turno al aprobarse.")
                return redirect("solicitudes:detalle", pk=resultado.solicitud.pk)
            devolucion = servicios.devolver(objeto, datos["cantidades"], Devolucion.SALDO, request.user, datos["motivo"], request)
        except servicios.ErrorInventario as error:
            formulario.add_error(None, str(error))
        else:
            if devolucion.medio == Devolucion.SIN_DINERO:
                messages.success(request, "Devolución registrada: se canceló lo pendiente de esos artículos.")
            else:
                messages.success(request, f"Devolución registrada: quedó un saldo a favor (recibo {devolucion.pago_credito.recibo}).")
            return redirect("inventario:venta", pk=pk)
    return render(request, "inventario/devolucion.html", {"formulario": formulario, "venta": objeto})


@requiere_permiso("registrar_movimientos_inventario")
@encendido
def registro_nuevo(request):
    formulario = FormularioRegistro(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            contenido = comprobantes.leer_subida(datos["comprobante"]) if datos.get("comprobante") else None
            registro = servicios.registrar_movimiento(datos["tipo"], datos["articulo"], datos["cantidad"], datos["motivo"], datos.get("nota", ""), request.user, contenido, request)
        except comprobantes.ComprobanteInvalido as error:
            registrar("comprobante_rechazado", request=request, datos={"motivo": str(error)[:200], "desde": "inventario"})
            formulario.add_error("comprobante", str(error))
        except servicios.ErrorInventario as error:
            formulario.add_error(None, str(error))
        else:
            messages.success(request, f"{registro.get_tipo_display()} registrada.")
            return redirect("inventario:registro", pk=registro.pk)
    return render(request, "inventario/registro_nuevo.html", {"formulario": formulario})


def _registro_visible(request, pk):
    objeto = get_object_or_404(RegistroInventario.objects.select_related("articulo", "usuario", "revisado_por"), pk=pk)
    if objeto.usuario_id != request.user.pk and not request.user.tiene_permiso("revisar_inventario"):
        registrar("acceso_denegado", request=request, objeto=objeto, datos={"accion": "registro_inventario_ajeno"})
        raise PermissionDenied
    return objeto


@requiere_permiso(*REGISTROS)
@encendido
def registro(request, pk):
    objeto = _registro_visible(request, pk)
    propio = objeto.usuario_id == request.user.pk
    contexto = {
        "registro": objeto,
        "archivo": getattr(objeto, "archivo_comprobante", None),
        "puede_adjuntar": propio and objeto.comprobante == RegistroInventario.SIN,
        "puede_revisar": not propio and objeto.revision == POR_REVISAR and request.user.tiene_permiso("revisar_inventario"),
        "formulario_comprobante": FormularioComprobante(),
        "formulario_revision": FormularioRevision(),
    }
    return render(request, "inventario/registro.html", contexto)


@requiere_permiso("registrar_movimientos_inventario")
@encendido
@require_POST
def registro_comprobante(request, pk):
    objeto = _registro_visible(request, pk)
    formulario = FormularioComprobante(request.POST, request.FILES)
    if not formulario.is_valid():
        messages.error(request, "Elige el archivo del comprobante.")
        return redirect("inventario:registro", pk=pk)
    try:
        servicios.adjuntar(objeto, request.user, comprobantes.leer_subida(formulario.cleaned_data["archivo"]), request)
        messages.success(request, "Comprobante adjuntado.")
    except comprobantes.ComprobanteInvalido as error:
        registrar("comprobante_rechazado", request=request, objeto=objeto, datos={"motivo": str(error)[:200]})
        messages.error(request, str(error))
    except servicios.ErrorInventario as error:
        messages.error(request, str(error))
    return redirect("inventario:registro", pk=pk)


@requiere_permiso(*REGISTROS)
@encendido
def registro_descargar(request, pk):
    objeto = _registro_visible(request, pk)
    archivo = getattr(objeto, "archivo_comprobante", None)
    if archivo is None:
        messages.error(request, "El registro no tiene comprobante.")
        return redirect("inventario:registro", pk=pk)
    try:
        contenido = comprobantes.leer(archivo)
    except (OSError, comprobantes.ComprobanteInvalido):
        registrar("comprobante_alterado", request=request, objeto=objeto, datos={"archivo": archivo.archivo})
        messages.error(request, "El archivo del comprobante no está o fue alterado; quedó registrado en la bitácora.")
        return redirect("inventario:registro", pk=pk)
    registrar("comprobante_descargado", request=request, objeto=objeto, datos={"registro": objeto.pk, "sha256": archivo.sha256})
    respuesta = HttpResponse(contenido, content_type=comprobantes.TIPOS_MIME[archivo.tipo])
    respuesta["Content-Disposition"] = f'attachment; filename="comprobante-inventario-{objeto.pk}.{comprobantes.EXTENSIONES[archivo.tipo]}"'
    respuesta["X-Content-Type-Options"] = "nosniff"
    respuesta["Content-Security-Policy"] = "sandbox"
    respuesta["Cache-Control"] = "no-store"
    return respuesta


def _revision_post(request, accion, regreso):
    formulario = FormularioRevision(request.POST)
    if not formulario.is_valid():
        messages.error(request, "Elige el resultado de la revisión.")
        return redirect(regreso)
    try:
        accion(formulario.cleaned_data["resultado"], formulario.cleaned_data.get("nota", ""))
    except servicios.RevisionPropia:
        raise PermissionDenied
    except servicios.ErrorInventario as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Revisión guardada.")
    return redirect(regreso)


@requiere_permiso("revisar_inventario")
@encendido
@require_POST
def registro_revisar(request, pk):
    objeto = get_object_or_404(RegistroInventario, pk=pk)
    return _revision_post(request, lambda r, n: servicios.revisar_registro(objeto, request.user, r, n, request), reverse("inventario:registro", args=[pk]))


@requiere_permiso("revisar_inventario")
@encendido
@require_POST
def devolucion_revisar(request, pk):
    objeto = get_object_or_404(Devolucion, pk=pk)
    return _revision_post(request, lambda r, n: servicios.revisar_devolucion(objeto, request.user, r, n, request), reverse("inventario:revision"))


@requiere_permiso("revisar_inventario")
@encendido
@require_POST
def renglon_revisar(request, pk):
    objeto = get_object_or_404(RenglonVenta.objects.select_related("venta", "articulo"), pk=pk, sin_existencia=True)
    try:
        servicios.revisar_sin_existencia(objeto, request.user, request)
    except servicios.RevisionPropia:
        raise PermissionDenied
    except servicios.ErrorInventario as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Revisión guardada.")
    return redirect("inventario:revision")


@requiere_permiso("revisar_inventario")
@encendido
def revision(request):
    contexto = {
        "registros": RegistroInventario.objects.filter(revision=POR_REVISAR).select_related("articulo", "usuario")[:200],
        "devoluciones": Devolucion.objects.filter(revision=POR_REVISAR).select_related("venta__titular", "usuario", "pago_credito__recibo")[:200],
        "sin_existencia": RenglonVenta.objects.filter(sin_existencia=True, revisado_por__isnull=True).select_related("venta__titular", "venta__usuario", "articulo")[:200],
        "bajo_minimo": servicios.bajo_minimo(),
        "formulario_revision": FormularioRevision(),
        "registros_recientes": RegistroInventario.objects.exclude(revision=POR_REVISAR).select_related("articulo", "usuario", "revisado_por")[:30],
    }
    return render(request, "inventario/revision.html", contexto)


@requiere_permiso(*VEN_EXISTENCIAS)
@encendido
def existencias_csv(request):
    registrar("exportacion_existencias", request=request, datos={"articulos": Articulo.objects.count()})
    respuesta = HttpResponse(servicios.exportar_existencias(), content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="existencias.csv"'
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


@requiere_permiso("subir_conteo_inventario")
@encendido
def conteo_lista(request):
    registrar("lista_para_contar", request=request)
    respuesta = HttpResponse(servicios.lista_para_contar(), content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="lista-para-contar.csv"'
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


@requiere_permiso("subir_conteo_inventario")
@encendido
def conteo(request):
    subida = FormularioSubirConteo(request.POST or None, request.FILES or None) if request.POST.get("forma") == "archivo" else FormularioSubirConteo()
    captura = FormularioCapturaConteo(request.POST) if request.POST.get("forma") == "pantalla" else FormularioCapturaConteo()
    if request.method == "POST":
        try:
            if request.POST.get("forma") == "archivo" and subida.is_valid():
                archivo = subida.cleaned_data["archivo"]
                contenido = lectura.leer_subida(archivo, servicios.LIMITE_CONTEO)
                cantidades = servicios.leer_conteo(archivo.name, contenido)
                hecho = servicios.subir_conteo(cantidades, request.user, Conteo.ARCHIVO, lectura.nombre_saneado(archivo.name), lectura.huella_archivo(contenido), request)
            elif request.POST.get("forma") == "pantalla" and captura.is_valid():
                hecho = servicios.subir_conteo(captura.cleaned_data["cantidades"], request.user, Conteo.PANTALLA, request=request)
            else:
                hecho = None
        except (servicios.ErrorInventario, lectura.ErrorLectura) as error:
            registrar("conteo_inventario_rechazado", request=request, datos={"motivo": str(error)[:300]})
            (subida if request.POST.get("forma") == "archivo" else captura).add_error(None, str(error))
            hecho = None
        if hecho is not None:
            messages.success(request, "Conteo guardado: ya no se puede cambiar. Otra persona debe aprobarlo.")
            return redirect("inventario:conteo_detalle", pk=hecho.pk)
    return render(request, "inventario/conteo.html", {"subida": subida, "captura": captura, "en_espera": servicios.conteo_en_espera(), "conteos": Conteo.objects.select_related("usuario", "solicitud", "aplicado_por")[:20]})


@requiere_permiso(*CONTEOS)
@encendido
def conteo_detalle(request, pk):
    objeto = get_object_or_404(Conteo.objects.select_related("usuario", "solicitud", "aplicado_por"), pk=pk)
    if objeto.usuario_id != request.user.pk and not (request.user.tiene_permiso("revisar_inventario") or request.user.tiene_permiso("aprobar_solicitudes")):
        registrar("acceso_denegado", request=request, objeto=objeto, datos={"accion": "conteo_ajeno"})
        raise PermissionDenied
    return render(request, "inventario/conteo_detalle.html", {"conteo": objeto, "renglones": objeto.renglones.select_related("articulo")})
