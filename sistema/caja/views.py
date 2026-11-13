from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.forms.models import model_to_dict
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.servicios import diferencias, registrar
from cuentas.decoradores import requiere_permiso
from solicitudes import motor

from . import comprobantes, retiros, servicios
from . import piezas as control_piezas
from .formularios import (
    FormularioAbrir,
    FormularioArqueo,
    FormularioCerrarConPrimero,
    FormularioComprobante,
    FormularioConfirmar,
    FormularioDeposito,
    FormularioEntrega,
    FormularioMotivoRetiro,
    FormularioRechazar,
    FormularioReconteo,
    FormularioRetiro,
    FormularioRevertirRetiro,
    FormularioRevision,
    FormularioSinComprobante,
)
from .models import ConteoArqueo, MotivoRetiro, RetiroCaja, Traslado, Turno

CAJEROS = ("turno_caja", "recibir_efectivo")
RETIROS = ("retirar_efectivo", "revisar_retiros")


@requiere_permiso("turno_caja")
def inicio(request):
    turno = servicios.turno_abierto(request.user)
    contexto = {
        "turno": turno,
        "en_arqueo": turno is not None and ConteoArqueo.objects.filter(turno=turno).exists(),
        "cobros": turno.pagos.count() if turno else 0,
        "retiros": turno.retiros.count() if turno else 0,
        "pendientes_comprobante": list(servicios.comprobantes_pendientes(turno)) if turno else [],
        "formulario": FormularioAbrir() if turno is None else None,
        "disponible": servicios.disponible_para_trasladar(request.user),
        "turnos": Turno.objects.filter(usuario=request.user, estado=Turno.CERRADO).select_related("caja", "arqueo")[:10],
    }
    return render(request, "caja/inicio.html", contexto)


@requiere_permiso("turno_caja")
@require_POST
def abrir(request):
    formulario = FormularioAbrir(request.POST)
    if formulario.is_valid():
        try:
            servicios.abrir_turno(request.user, formulario.cleaned_data["caja"], formulario.cleaned_data.get("fondo_inicial") or 0, request, piezas=formulario.piezas())
            messages.success(request, "Turno abierto.")
        except servicios.ErrorCaja as error:
            messages.error(request, str(error))
    else:
        messages.error(request, "Elige una caja libre y revisa el fondo.")
    return redirect("caja:inicio")


def _turno_visible(request, turno):
    if turno.usuario_id == request.user.pk:
        return True
    return request.user.tiene_permiso("recibir_efectivo")


@requiere_permiso(*CAJEROS)
def turno(request, pk):
    objeto = get_object_or_404(Turno.objects.select_related("caja", "usuario"), pk=pk)
    if not _turno_visible(request, objeto):
        registrar("acceso_denegado", request=request, objeto=objeto)
        raise PermissionDenied
    arqueo = getattr(objeto, "arqueo", None) if not objeto.abierto else None
    contexto = {
        "turno": objeto,
        "arqueo": arqueo,
        "cobros": objeto.pagos.count(),
        "retiros": objeto.retiros.select_related("motivo") if arqueo else None,
        "piezas": control_piezas.renglones(arqueo.esperado_piezas, arqueo.conteo) if arqueo and arqueo.esperado_piezas else [],
        "primer_piezas": control_piezas.renglones(arqueo.esperado_piezas, arqueo.primer_conteo) if arqueo and arqueo.esperado_piezas and arqueo.con_reconteo else [],
    }
    return render(request, "caja/turno.html", contexto)


def _turno_propio(request, pk):
    objeto = get_object_or_404(Turno.objects.select_related("caja"), pk=pk)
    if objeto.usuario_id != request.user.pk:
        registrar("acceso_denegado", request=request, objeto=objeto, datos={"accion": "cerrar_turno_ajeno"})
        raise PermissionDenied
    return objeto


@requiere_permiso("turno_caja")
def cerrar(request, pk):
    objeto = _turno_propio(request, pk)
    if not objeto.abierto:
        return redirect("caja:turno", pk=pk)
    if ConteoArqueo.objects.filter(turno=objeto).exists():
        return redirect("caja:reconteo", pk=pk)
    pendientes = list(servicios.comprobantes_pendientes(objeto))
    formulario = FormularioArqueo(request.POST if request.method == "POST" else None)
    if request.method == "POST" and not pendientes and formulario.is_valid():
        try:
            resultado = servicios.primer_conteo(objeto, request.user, formulario.conteo(), formulario.cleaned_data.get("nota", ""), request)
        except servicios.ErrorCaja as error:
            messages.error(request, str(error))
            return redirect("caja:inicio")
        if resultado.cerrado:
            messages.success(request, "El conteo coincide: turno cerrado.")
            return redirect("caja:turno", pk=pk)
        return redirect("caja:reconteo", pk=pk)
    return render(request, "caja/cerrar.html", {"turno": objeto, "formulario": formulario, "pendientes": pendientes})


@requiere_permiso("turno_caja")
def reconteo(request, pk):
    objeto = _turno_propio(request, pk)
    if not objeto.abierto:
        return redirect("caja:turno", pk=pk)
    if not ConteoArqueo.objects.filter(turno=objeto).exists():
        return redirect("caja:cerrar", pk=pk)
    accion = request.POST.get("accion") if request.method == "POST" else None
    recontar = FormularioReconteo(request.POST if accion == "reconteo" else None)
    con_primero = FormularioCerrarConPrimero(request.POST if accion == "primero" else None)
    if accion in ("reconteo", "primero"):
        formulario = recontar if accion == "reconteo" else con_primero
        if formulario.is_valid():
            try:
                if accion == "reconteo":
                    servicios.reconteo(objeto, request.user, formulario.conteo(), formulario.cleaned_data["nota"], request)
                else:
                    servicios.cerrar_con_primer_conteo(objeto, request.user, formulario.cleaned_data["nota"], request)
            except servicios.ErrorCaja as error:
                messages.error(request, str(error))
                return redirect("caja:inicio")
            messages.success(request, "Turno cerrado.")
            return redirect("caja:turno", pk=pk)
    return render(request, "caja/reconteo.html", {"turno": objeto, "recontar": recontar, "con_primero": con_primero})


@requiere_permiso(*CAJEROS)
def traslados(request):
    propios = Traslado.objects.filter(Q(origen=request.user) | Q(destino=request.user)).select_related("origen", "destino", "cuenta_bancaria")[:100]
    return render(request, "caja/traslados.html", {"traslados": propios, "disponible": servicios.disponible_para_trasladar(request.user)})


@requiere_permiso(*CAJEROS)
def entrega(request):
    formulario = FormularioEntrega(request.POST if request.method == "POST" else None, origen=request.user)
    if request.method == "POST" and formulario.is_valid():
        try:
            servicios.entregar(request.user, formulario.cleaned_data["destino"], formulario.cleaned_data["importe"], formulario.cleaned_data.get("nota", ""), request, piezas=formulario.piezas())
            messages.success(request, "Entrega enviada; queda pendiente hasta que la otra persona la confirme.")
            return redirect("caja:traslados")
        except servicios.ErrorCaja as error:
            formulario.add_error(None, str(error))
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Entregar efectivo", "boton": "Enviar", "volver": "caja:traslados"})


@requiere_permiso(*CAJEROS)
def deposito(request):
    formulario = FormularioDeposito(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            servicios.depositar(request.user, datos["importe"], datos["cuenta"], datos["fecha"], datos["referencia"], request=request, piezas=formulario.piezas())
            messages.success(request, "Depósito registrado; queda por conciliar con el banco.")
            return redirect("caja:traslados")
        except servicios.ErrorCaja as error:
            formulario.add_error(None, str(error))
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Registrar depósito bancario", "boton": "Registrar", "volver": "caja:traslados"})


def _entrega_propia(request, pk):
    traslado = get_object_or_404(Traslado.objects.select_related("origen"), pk=pk, tipo=Traslado.ENTREGA)
    if traslado.destino_id != request.user.pk:
        registrar("acceso_denegado", request=request, objeto=traslado, datos={"accion": "entrega_ajena"})
        raise PermissionDenied
    return traslado


@requiere_permiso("recibir_efectivo")
@require_POST
def confirmar(request, pk):
    traslado = _entrega_propia(request, pk)
    formulario = FormularioConfirmar(request.POST)
    if formulario.is_valid():
        try:
            servicios.confirmar_entrega(traslado, request.user, formulario.cleaned_data["importe"], request)
            messages.success(request, "Entrega confirmada.")
        except servicios.ErrorCaja as error:
            messages.error(request, str(error))
    else:
        messages.error(request, "Escribe el importe que recibiste.")
    return redirect("caja:traslados")


@requiere_permiso("recibir_efectivo")
@require_POST
def rechazar(request, pk):
    traslado = _entrega_propia(request, pk)
    formulario = FormularioRechazar(request.POST)
    if formulario.is_valid():
        try:
            servicios.rechazar_entrega(traslado, request.user, formulario.cleaned_data["nota"], request)
            messages.success(request, "Entrega rechazada.")
        except servicios.ErrorCaja as error:
            messages.error(request, str(error))
    else:
        messages.error(request, "Escribe el motivo del rechazo.")
    return redirect("caja:traslados")


@requiere_permiso("recibir_efectivo")
def custodia(request):
    return render(request, "caja/custodia.html", {"personas": servicios.personas_con_efectivo(request.user), "alertas": servicios.alertas(request.user)})


@requiere_permiso(*RETIROS)
def lista_retiros(request):
    return render(request, "caja/retiros.html", {"retiros": retiros.visibles(request.user)[:200], "puede_retirar": request.user.tiene_permiso("retirar_efectivo")})


def _leer_archivo(archivo):
    if archivo is None:
        return None
    return comprobantes.leer_subida(archivo)


@requiere_permiso("retirar_efectivo")
def retiro_nuevo(request):
    turno = servicios.turno_abierto(request.user)
    formulario = FormularioRetiro(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None)
    if request.method == "POST" and turno is not None and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            resultado = retiros.registrar_retiro(request.user, datos["importe"], datos["motivo"], datos.get("nota", ""), formulario.piezas(), _leer_archivo(datos.get("comprobante")), request)
        except comprobantes.ComprobanteInvalido as error:
            formulario.add_error("comprobante", str(error))
        except servicios.ErrorCaja as error:
            formulario.add_error(None, str(error))
        else:
            if resultado.rechazado:
                formulario.add_error("importe", "No se registró: el turno no tiene ese efectivo cobrado. Revisa el importe.")
            elif resultado.solicitud is not None:
                messages.warning(request, "El retiro pasa de los topes: quedó como solicitud. Se registrará al autorizarse; después adjunta su comprobante.")
                return redirect("solicitudes:detalle", pk=resultado.solicitud.pk)
            else:
                messages.success(request, f"Retiro {resultado.retiro} registrado.")
                return redirect("caja:retiro", pk=resultado.retiro.pk)
    return render(request, "caja/retiro_nuevo.html", {"formulario": formulario, "turno": turno})


def _retiro_visible(request, pk):
    objeto = get_object_or_404(RetiroCaja.objects.select_related("caja", "motivo", "registrado_por", "revisado_por", "turno", "autorizado_por"), pk=pk)
    if not retiros.puede_ver(request.user, objeto):
        registrar("acceso_denegado", request=request, objeto=objeto, datos={"accion": "retiro_ajeno"})
        raise PermissionDenied
    return objeto


@requiere_permiso(*RETIROS)
def retiro(request, pk):
    objeto = _retiro_visible(request, pk)
    propio = objeto.registrado_por_id == request.user.pk
    contexto = {
        "retiro": objeto,
        "archivo": getattr(objeto, "archivo_comprobante", None),
        "reversion": getattr(objeto, "reversion", None),
        "propio": propio,
        "puede_adjuntar": propio and objeto.comprobante == RetiroCaja.PENDIENTE,
        "puede_revisar": not propio and objeto.revision == RetiroCaja.POR_REVISAR and request.user.tiene_permiso("revisar_retiros"),
        "formulario_comprobante": FormularioComprobante(),
        "formulario_sin": FormularioSinComprobante(),
        "formulario_revision": FormularioRevision(),
        "piezas": objeto.piezas.order_by("-denominacion"),
    }
    return render(request, "caja/retiro.html", contexto)


@requiere_permiso("retirar_efectivo")
@require_POST
def retiro_comprobante(request, pk):
    objeto = _retiro_visible(request, pk)
    formulario = FormularioComprobante(request.POST, request.FILES)
    if not formulario.is_valid():
        messages.error(request, "Elige el archivo del comprobante.")
        return redirect("caja:retiro", pk=pk)
    try:
        retiros.adjuntar(objeto, request.user, comprobantes.leer_subida(formulario.cleaned_data["archivo"]), request)
        messages.success(request, "Comprobante adjuntado.")
    except comprobantes.ComprobanteInvalido as error:
        registrar("comprobante_rechazado", request=request, objeto=objeto, datos={"motivo": str(error)[:200]})
        messages.error(request, str(error))
    except servicios.ErrorCaja as error:
        messages.error(request, str(error))
    return redirect("caja:retiro", pk=pk)


@requiere_permiso("retirar_efectivo")
@require_POST
def retiro_sin_comprobante(request, pk):
    objeto = _retiro_visible(request, pk)
    formulario = FormularioSinComprobante(request.POST)
    if not formulario.is_valid():
        messages.error(request, "Escribe por qué no hay comprobante.")
        return redirect("caja:retiro", pk=pk)
    try:
        retiros.sin_comprobante(objeto, request.user, formulario.cleaned_data["motivo"], request)
        messages.warning(request, "Se declaró sin comprobante; Supervisión recibe el aviso.")
    except servicios.ErrorCaja as error:
        messages.error(request, str(error))
    return redirect("caja:retiro", pk=pk)


@requiere_permiso(*RETIROS)
def retiro_descargar(request, pk):
    objeto = _retiro_visible(request, pk)
    archivo = getattr(objeto, "archivo_comprobante", None)
    if archivo is None:
        messages.error(request, "El retiro no tiene comprobante.")
        return redirect("caja:retiro", pk=pk)
    try:
        contenido = comprobantes.leer(archivo)
    except (OSError, comprobantes.ComprobanteInvalido):
        registrar("comprobante_alterado", request=request, objeto=objeto, datos={"archivo": archivo.archivo})
        messages.error(request, "El archivo del comprobante no está o fue alterado; quedó registrado en la bitácora.")
        return redirect("caja:retiro", pk=pk)
    registrar("comprobante_descargado", request=request, objeto=objeto, datos={"folio": str(objeto), "sha256": archivo.sha256})
    respuesta = HttpResponse(contenido, content_type=comprobantes.TIPOS_MIME[archivo.tipo])
    respuesta["Content-Disposition"] = f'attachment; filename="comprobante-{objeto.serie}-{objeto.folio}.{comprobantes.EXTENSIONES[archivo.tipo]}"'
    respuesta["X-Content-Type-Options"] = "nosniff"
    respuesta["Content-Security-Policy"] = "sandbox"
    respuesta["Cache-Control"] = "no-store"
    return respuesta


@requiere_permiso("revisar_retiros")
@require_POST
def retiro_revisar(request, pk):
    objeto = _retiro_visible(request, pk)
    formulario = FormularioRevision(request.POST)
    if not formulario.is_valid():
        messages.error(request, "Elige el resultado de la revisión.")
        return redirect("caja:retiro", pk=pk)
    try:
        retiros.revisar(objeto, request.user, formulario.cleaned_data["resultado"], formulario.cleaned_data.get("nota", ""), request)
        messages.success(request, "Revisión guardada.")
    except retiros.RevisionPropia:
        raise PermissionDenied
    except servicios.ErrorCaja as error:
        messages.error(request, str(error))
    return redirect("caja:retiro", pk=pk)


@requiere_permiso(*RETIROS)
def retiro_revertir(request, pk):
    objeto = _retiro_visible(request, pk)
    formulario = FormularioRevertirRetiro(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        datos = {"retiro": objeto.pk, "motivo": formulario.cleaned_data["motivo"]}
        if formulario.piezas() is not None:
            datos["piezas"] = formulario.piezas()
        try:
            resultado = motor.ejecutar("revertir_retiro", request.user, None, datos, request=request)
        except motor.ErrorSolicitud as error:
            messages.error(request, str(error))
        else:
            messages.info(request, "La reversión quedó como solicitud: la resuelve otra persona.")
            return redirect("solicitudes:detalle", pk=resultado.solicitud.pk)
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"Revertir el retiro {objeto}", "boton": "Solicitar reversión"})


@requiere_permiso("administrar_motivos_retiro")
def motivos(request):
    return render(request, "caja/motivos.html", {"motivos": MotivoRetiro.objects.all()})


def _guardar_motivo(request, pk=None):
    instancia = get_object_or_404(MotivoRetiro, pk=pk) if pk else None
    antes = model_to_dict(instancia) if instancia else {}
    formulario = FormularioMotivoRetiro(request.POST if request.method == "POST" else None, instance=instancia)
    if request.method == "POST" and formulario.is_valid():
        guardado = formulario.save()
        registrar("motivo_retiro_cambiado" if instancia else "motivo_retiro_creado", usuario=request.user, objeto=guardado, datos={"nombre": guardado.nombre, "cambios": diferencias(antes, model_to_dict(guardado))}, request=request)
        messages.success(request, "Guardado.")
        return redirect("caja:motivos")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Motivo de retiro" + (f": {instancia}" if instancia else ": nuevo"), "boton": "Guardar", "volver": "caja:motivos"})


@requiere_permiso("administrar_motivos_retiro")
def motivo_nuevo(request):
    return _guardar_motivo(request)


@requiere_permiso("administrar_motivos_retiro")
def motivo_editar(request, pk):
    return _guardar_motivo(request, pk)
