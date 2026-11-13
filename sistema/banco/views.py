from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from cuentas.decoradores import requiere_permiso

from .formularios import FormularioCuenta
from .models import CuentaBancaria
from .servicios import guardar_cuenta

PERMISO = "administrar_configuracion"


def avisar(request, formulario, cuenta):
    if formulario.banco_propuesto is not None:
        messages.info(request, f"Banco elegido según la CLABE: {formulario.banco_propuesto}.")
    if formulario.banco_nuevo is not None:
        messages.warning(request, f"El prefijo {formulario.banco_nuevo['clave']} no está en el catálogo; se registró «{cuenta.banco}» como banco capturado a mano. Revisa que sea correcto.")


@requiere_permiso(PERMISO)
def lista(request):
    return render(request, "banco/lista.html", {"cuentas": CuentaBancaria.objects.select_related("banco").prefetch_related("medios")})


def _guardar(request, cuenta=None):
    formulario = FormularioCuenta(request.POST if request.method == "POST" else None, cuenta=cuenta)
    if request.method == "POST" and formulario.is_valid():
        guardada = guardar_cuenta(formulario, request.user, cuenta=cuenta, request=request)
        avisar(request, formulario, guardada)
        messages.success(request, "Cuenta guardada.")
        return redirect("banco:lista")
    titulo = "Nueva cuenta bancaria" if cuenta is None else f"Editar cuenta {cuenta}"
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": titulo, "boton": "Guardar", "volver": "banco:lista"})


@requiere_permiso(PERMISO, reingreso=True)
def nueva(request):
    return _guardar(request)


@requiere_permiso(PERMISO, reingreso=True)
def editar(request, pk):
    return _guardar(request, get_object_or_404(CuentaBancaria, pk=pk))
