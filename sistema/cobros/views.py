from django.contrib import messages
from django.forms.models import model_to_dict
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.servicios import diferencias, registrar
from cuentas.decoradores import requiere_permiso

from .formularios import FormularioConcepto, FormularioPlan, FormularioRegla
from .models import ConceptoCobro, PlanCobro, ReglaRecargo

PERMISO = "administrar_conceptos"


def _guardar(request, clase_formulario, instancia, evento, destino, titulo, inicial=None):
    antes = model_to_dict(instancia) if instancia is not None and instancia.pk else None
    formulario = clase_formulario(request.POST if request.method == "POST" else None, instance=instancia, initial=inicial)
    if request.method == "POST" and formulario.is_valid():
        guardado = formulario.save()
        registrar(
            f"{evento}_{'cambiado' if antes else 'creado'}",
            usuario=request.user,
            objeto=guardado,
            datos={"nombre": str(guardado), "cambios": diferencias(antes or {}, model_to_dict(guardado))},
            request=request,
        )
        messages.success(request, "Guardado.")
        return redirect(destino)
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": titulo, "boton": "Guardar", "volver": destino})


@requiere_permiso(PERMISO)
def conceptos(request):
    return render(request, "cobros/conceptos.html", {"conceptos": ConceptoCobro.objects.select_related("regla_recargo", "agrupacion")})


@requiere_permiso(PERMISO)
def concepto_nuevo(request):
    return _guardar(request, FormularioConcepto, None, "concepto", "cobros:conceptos", "Nuevo concepto de cobro")


@requiere_permiso(PERMISO)
def concepto_editar(request, pk):
    concepto = get_object_or_404(ConceptoCobro, pk=pk)
    return _guardar(request, FormularioConcepto, concepto, "concepto", "cobros:conceptos", f"Editar {concepto}")


@requiere_permiso(PERMISO)
def reglas(request):
    return render(request, "cobros/reglas.html", {"reglas": ReglaRecargo.objects.all()})


@requiere_permiso(PERMISO)
def regla_nueva(request):
    return _guardar(request, FormularioRegla, None, "regla_recargo", "cobros:reglas", "Nueva regla de recargo")


@requiere_permiso(PERMISO)
def regla_editar(request, pk):
    regla = get_object_or_404(ReglaRecargo, pk=pk)
    return _guardar(request, FormularioRegla, regla, "regla_recargo", "cobros:reglas", f"Editar {regla}")


@requiere_permiso(PERMISO)
def planes(request):
    return render(request, "cobros/planes.html", {"planes": PlanCobro.objects.select_related("titular", "concepto")[:300]})


@requiere_permiso(PERMISO)
def plan_nuevo(request):
    inicial = {}
    titular = request.GET.get("titular", "")
    if titular.isdigit():
        inicial["titular"] = int(titular)
    return _guardar(request, FormularioPlan, None, "plan_cobro", "cobros:planes", "Nuevo plan de cobro", inicial)


@requiere_permiso(PERMISO)
def plan_editar(request, pk):
    plan = get_object_or_404(PlanCobro, pk=pk)
    return _guardar(request, FormularioPlan, plan, "plan_cobro", "cobros:planes", f"Editar plan {plan}")
