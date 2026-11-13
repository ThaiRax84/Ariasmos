from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.servicios import registrar
from cuentas.decoradores import requiere_permiso

from . import servicios
from .formularios import FormularioAbrir, FormularioArqueo, FormularioConfirmar, FormularioDeposito, FormularioEntrega, FormularioRechazar
from .models import Traslado, Turno

CAJEROS = ("turno_caja", "recibir_efectivo")


@requiere_permiso("turno_caja")
def inicio(request):
    turno = servicios.turno_abierto(request.user)
    contexto = {
        "turno": turno,
        "cobros": turno.pagos.count() if turno else 0,
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
            servicios.abrir_turno(request.user, formulario.cleaned_data["caja"], formulario.cleaned_data.get("fondo_inicial") or 0, request)
            messages.success(request, "Turno abierto.")
        except servicios.ErrorCaja as error:
            messages.error(request, str(error))
    else:
        messages.error(request, "Elige una caja libre.")
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
    return render(request, "caja/turno.html", {"turno": objeto, "arqueo": arqueo, "cobros": objeto.pagos.count()})


@requiere_permiso("turno_caja")
def cerrar(request, pk):
    objeto = get_object_or_404(Turno.objects.select_related("caja"), pk=pk)
    if objeto.usuario_id != request.user.pk:
        registrar("acceso_denegado", request=request, objeto=objeto, datos={"accion": "cerrar_turno_ajeno"})
        raise PermissionDenied
    if not objeto.abierto:
        return redirect("caja:turno", pk=pk)
    formulario = FormularioArqueo(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        try:
            servicios.cerrar_turno(objeto, request.user, formulario.conteo(), formulario.cleaned_data.get("nota", ""), request)
            messages.success(request, "Turno cerrado.")
            return redirect("caja:turno", pk=pk)
        except servicios.NotaRequerida as error:
            formulario.add_error("nota", str(error))
        except servicios.ErrorCaja as error:
            messages.error(request, str(error))
            return redirect("caja:inicio")
    return render(request, "caja/cerrar.html", {"turno": objeto, "formulario": formulario})


@requiere_permiso(*CAJEROS)
def traslados(request):
    propios = Traslado.objects.filter(Q(origen=request.user) | Q(destino=request.user)).select_related("origen", "destino", "cuenta_bancaria")[:100]
    return render(request, "caja/traslados.html", {"traslados": propios, "disponible": servicios.disponible_para_trasladar(request.user)})


@requiere_permiso(*CAJEROS)
def entrega(request):
    formulario = FormularioEntrega(request.POST if request.method == "POST" else None, origen=request.user)
    if request.method == "POST" and formulario.is_valid():
        try:
            servicios.entregar(request.user, formulario.cleaned_data["destino"], formulario.cleaned_data["importe"], formulario.cleaned_data.get("nota", ""), request)
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
            servicios.depositar(request.user, datos["importe"], datos["cuenta"], datos["fecha"], datos["referencia"], request=request)
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
    return render(request, "caja/custodia.html", {"personas": servicios.personas_con_efectivo(), "alertas": servicios.alertas()})
