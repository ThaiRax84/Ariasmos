from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from cuentas.decoradores import requiere_permiso

from .models import Evento
from .servicios import registrar, verificar_cadena


@requiere_permiso("ver_auditoria")
def lista(request):
    eventos = Evento.objects.select_related("usuario").order_by("-id")
    accion = request.GET.get("accion", "").strip()
    if accion:
        eventos = eventos.filter(accion=accion)
    return render(request, "auditoria/lista.html", {"eventos": eventos[:300], "accion": accion})


@requiere_permiso("ver_auditoria")
@require_POST
def verificar(request):
    valida, evento_id, total = verificar_cadena()
    if valida:
        messages.success(request, f"La cadena está íntegra: {total} eventos verificados.")
    else:
        messages.error(request, f"La cadena está alterada a partir del evento {evento_id}.")
    registrar("auditoria_verificada", request=request, datos={"valida": valida, "evento": evento_id})
    return redirect("auditoria:lista")
