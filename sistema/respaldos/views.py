from django import forms
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from auditoria.servicios import diferencias, registrar
from configuracion.models import Negocio
from cortes.entrega import ErrorEntrega, validar_ruta
from cuentas.decoradores import requiere_permiso
from nucleo import sobre

from . import servicios
from .models import Respaldo

PERMISO = "administrar_respaldos"


class FormularioCarpeta(forms.Form):
    carpeta_respaldo = forms.CharField(label="Carpeta de respaldo (ruta absoluta; de preferencia una carpeta sincronizada con la nube o un disco externo)", max_length=400)

    def clean_carpeta_respaldo(self):
        try:
            return validar_ruta(self.cleaned_data["carpeta_respaldo"])
        except ErrorEntrega as error:
            raise forms.ValidationError(str(error))


class FormularioGuardada(forms.Form):
    guardada = forms.BooleanField(label="Ya imprimí la clave de recuperación y la guardé fuera de este equipo", required=True)


def _sin_cache(respuesta):
    respuesta["Cache-Control"] = "no-store"
    return respuesta


@requiere_permiso(PERMISO)
def panel(request):
    negocio = Negocio.objects.get(pk=1)
    contexto = {
        "carpeta": negocio.carpeta_respaldo,
        "pendiente": negocio.clave_recuperacion_pendiente,
        "alertas": servicios.alertas(),
        "registros": Respaldo.objects.all()[:60],
    }
    return render(request, "respaldos/panel.html", contexto)


@requiere_permiso(PERMISO, reingreso=True)
def carpeta(request):
    negocio = Negocio.objects.get(pk=1)
    formulario = FormularioCarpeta(request.POST if request.method == "POST" else None, initial={"carpeta_respaldo": negocio.carpeta_respaldo})
    if request.method == "POST" and formulario.is_valid():
        nueva = formulario.cleaned_data["carpeta_respaldo"]
        Negocio.objects.filter(pk=1).update(carpeta_respaldo=nueva)
        registrar("carpeta_respaldo_cambiada", request=request, objeto=negocio, datos={"cambios": diferencias({"carpeta_respaldo": negocio.carpeta_respaldo}, {"carpeta_respaldo": nueva})})
        messages.success(request, "Carpeta de respaldo guardada: existe y se puede escribir en ella.")
        return redirect("respaldos:panel")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Carpeta de respaldo", "boton": "Guardar", "volver": "respaldos:panel"})


@requiere_permiso(PERMISO)
@require_POST
def respaldar(request):
    registro = servicios.respaldar(usuario=request.user)
    if registro is not None and registro.resultado == Respaldo.CORRECTO:
        messages.success(request, f"Respaldo listo: {registro.archivo}.")
    else:
        messages.error(request, f"El respaldo falló: {registro.mensaje if registro else 'hay otro en curso'}")
    return redirect("respaldos:panel")


@requiere_permiso(PERMISO)
@require_POST
def probar(request):
    registro = servicios.probar(usuario=request.user)
    if registro is not None and registro.resultado == Respaldo.CORRECTO:
        messages.success(request, f"Prueba de restauración correcta: {registro.archivo}.")
    else:
        messages.error(request, f"La prueba falló: {registro.mensaje if registro else 'hay otra en curso'}")
    return redirect("respaldos:panel")


@requiere_permiso(PERMISO, reingreso=True)
def clave(request):
    negocio = Negocio.objects.get(pk=1)
    if not negocio.clave_recuperacion_pendiente:
        return render(request, "respaldos/clave.html", {"vista": False})
    formulario = FormularioGuardada(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        if Negocio.objects.filter(pk=1, clave_recuperacion_pendiente=True).update(clave_recuperacion_pendiente=False):
            registrar("clave_recuperacion_guardada", request=request, objeto=negocio)
        messages.success(request, "Listo. La clave ya no se puede volver a ver en el sistema.")
        return redirect("respaldos:panel")
    return _sin_cache(render(request, "respaldos/clave.html", {"vista": True, "texto": sobre.clave_a_texto(servicios.clave_respaldo()), "formulario": formulario}))


@requiere_permiso(PERMISO, reingreso=True)
@require_POST
def clave_nueva(request):
    servicios.nueva_clave_respaldo(request.user, request)
    messages.warning(request, "Se generó una clave nueva para los respaldos futuros. Los respaldos anteriores solo se abren con la clave anterior: no la tires.")
    return redirect("respaldos:clave")
