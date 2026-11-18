from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from cobros.models import ConceptoCobro
from configuracion.models import vocabulario
from cuentas.decoradores import requiere_permiso

from . import servicios
from .formularios import FormularioOpciones, FormularioTarifa
from .models import OpcionConcepto, TarifaAgrupacion

PERMISO = "administrar_conceptos"


@requiere_permiso(PERMISO)
def indice(request):
    conceptos = ConceptoCobro.objects.filter(activo=True).annotate(tarifas_activas=Count("tarifas", filter=Q(tarifas__activa=True)))
    opciones = {o.concepto_id: o for o in OpcionConcepto.objects.all()}
    filas = [{"concepto": c, "opcion": opciones.get(c.pk), "tarifas": c.tarifas_activas} for c in conceptos]
    return render(request, "tarifas/indice.html", {"filas": filas})


@requiere_permiso(PERMISO)
def concepto(request, pk):
    elegido = get_object_or_404(ConceptoCobro, pk=pk)
    opcion = servicios.opciones_de(elegido)
    inicial = {"por_cantidad": opcion.por_cantidad, "cantidad_maxima": opcion.cantidad_maxima if opcion.por_cantidad else 20, "solo_con_tarifa": opcion.solo_con_tarifa}
    formulario = FormularioOpciones(request.POST if request.method == "POST" else None, concepto=elegido, initial=inicial)
    if request.method == "POST" and formulario.is_valid():
        servicios.guardar_opciones(elegido, formulario.cleaned_data, request.user, request)
        messages.success(request, "Opciones guardadas.")
        return redirect("tarifas:concepto", pk=elegido.pk)
    tarifas = TarifaAgrupacion.objects.filter(concepto=elegido).select_related("agrupacion").order_by("agrupacion__nombre")
    return render(request, "tarifas/concepto.html", {"concepto": elegido, "formulario": formulario, "tarifas": tarifas, "opcion": opcion})


def _tarifa(request, elegido, tarifa):
    formulario = FormularioTarifa(request.POST if request.method == "POST" else None, concepto=elegido, tarifa=tarifa)
    if request.method == "POST" and formulario.is_valid():
        try:
            guardada = servicios.guardar_tarifa(tarifa or TarifaAgrupacion(concepto=elegido), dict(formulario.cleaned_data), request.user, request)
        except IntegrityError:
            formulario.add_error(None, "Esa tarifa ya existe: edítala en lugar de crear otra.")
        else:
            messages.success(request, f"Tarifa de {guardada.agrupacion} guardada.")
            return redirect("tarifas:concepto", pk=elegido.pk)
    voc = vocabulario()
    titulo = f"Tarifa de {elegido} para {tarifa.agrupacion}" if tarifa else f"Nueva tarifa de {elegido} por {voc['agrupacion_min']}"
    vacio = tarifa is None and not formulario.fields["agrupacion"].queryset.exists()
    return render(request, "tarifas/tarifa.html", {"formulario": formulario, "titulo": titulo, "concepto": elegido, "vacio": vacio})


@requiere_permiso(PERMISO)
def nueva(request, pk):
    return _tarifa(request, get_object_or_404(ConceptoCobro, pk=pk), None)


@requiere_permiso(PERMISO)
def editar(request, pk):
    tarifa = get_object_or_404(TarifaAgrupacion.objects.select_related("concepto", "agrupacion"), pk=pk)
    return _tarifa(request, tarifa.concepto, tarifa)
