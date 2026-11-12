from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from cuentas.decoradores import requiere_permiso
from cuentas.models import Usuario
from nucleo.matricula import normalizar
from titulares.models import Titular

from .models import Evento
from .servicios import MOTIVOS, registrar, ultima_verificacion, verificar_cadena


@requiere_permiso("ver_auditoria")
def lista(request):
    eventos = Evento.objects.order_by("-numero")
    accion = request.GET.get("accion", "").strip()
    usuario = request.GET.get("usuario", "").strip()
    titular = request.GET.get("titular", "").strip()
    if accion:
        eventos = eventos.filter(accion=accion)
    if usuario.isdigit():
        eventos = eventos.filter(usuario_id=int(usuario))
    if titular:
        digitos = normalizar(titular)
        encontrado = Titular.objects.filter(matricula=digitos).values_list("pk", flat=True).first() if digitos else None
        if encontrado is None and titular.isdigit():
            encontrado = int(titular)
        eventos = eventos.filter(titular=encontrado)
    contexto = {
        "eventos": eventos[:300],
        "accion": accion,
        "usuario": usuario,
        "titular": titular,
        "usuarios": Usuario.objects.order_by("nombre"),
        "verificacion": ultima_verificacion(),
        "motivos": MOTIVOS,
    }
    return render(request, "auditoria/lista.html", contexto)


@requiere_permiso("ver_auditoria")
@require_POST
def verificar(request):
    resultado = verificar_cadena(usuario=request.user, guardar=True)
    if resultado.valida:
        messages.success(request, f"La bitácora está íntegra: {resultado.total} eventos verificados.")
    else:
        messages.error(request, f"La bitácora NO está íntegra: {MOTIVOS[resultado.motivo]} (evento {resultado.numero}).")
    registrar("auditoria_verificada", request=request, datos={"valida": resultado.valida, "motivo": resultado.motivo, "numero": resultado.numero})
    return redirect("auditoria:lista")
