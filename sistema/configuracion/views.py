from django.contrib import messages
from django.db import transaction
from django.forms.models import model_to_dict
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.servicios import registrar
from cuentas.decoradores import requiere_permiso
from titulares.models import Agrupacion, CampoContacto, MotivoBaja, RelacionContacto

from .formularios import (
    FormularioAgrupacion,
    FormularioCampoContacto,
    FormularioMotivo,
    FormularioNegocio,
    FormularioParametros,
    FormularioRelacion,
    FormularioVocabulario,
)
from .models import PARAMETROS, VOCABULARIO_BASE, Negocio, Parametro, Vocabulario, parametro, vocabulario

PERMISO = "administrar_configuracion"


@requiere_permiso(PERMISO)
def indice(request):
    return render(request, "configuracion/indice.html")


@requiere_permiso(PERMISO, reingreso=True)
def negocio(request):
    actual = Negocio.objects.get(pk=1)
    antes = model_to_dict(actual)
    formulario = FormularioNegocio(request.POST if request.method == "POST" else None, instance=actual)
    if request.method == "POST" and formulario.is_valid():
        guardado = formulario.save()
        registrar("configuracion_cambiada", usuario=request.user, objeto=guardado, datos={"antes": antes, "despues": model_to_dict(guardado)}, request=request)
        messages.success(request, "Configuración guardada.")
        return redirect("configuracion:indice")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Datos del negocio", "boton": "Guardar", "volver": "configuracion:indice"})


@requiere_permiso(PERMISO, reingreso=True)
def textos(request):
    antes = vocabulario()
    formulario = FormularioVocabulario(request.POST if request.method == "POST" else None, textos=antes)
    if request.method == "POST" and formulario.is_valid():
        with transaction.atomic():
            for clave in VOCABULARIO_BASE:
                Vocabulario.objects.update_or_create(clave=clave, defaults={"texto": formulario.cleaned_data[clave]})
            registrar("vocabulario_cambiado", usuario=request.user, datos={"antes": antes, "despues": formulario.cleaned_data}, request=request)
        messages.success(request, "Vocabulario guardado.")
        return redirect("configuracion:indice")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Vocabulario", "boton": "Guardar", "volver": "configuracion:indice"})


@requiere_permiso(PERMISO, reingreso=True)
def parametros(request):
    antes = {clave: parametro(clave) for clave in PARAMETROS}
    formulario = FormularioParametros(request.POST if request.method == "POST" else None, valores=antes)
    if request.method == "POST" and formulario.is_valid():
        with transaction.atomic():
            for clave in PARAMETROS:
                Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(formulario.cleaned_data[clave])})
            registrar("parametros_cambiados", usuario=request.user, datos={"antes": antes, "despues": formulario.cleaned_data}, request=request)
        messages.success(request, "Parámetros guardados.")
        return redirect("configuracion:indice")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Parámetros", "boton": "Guardar", "volver": "configuracion:indice"})


CATALOGOS = {
    "agrupaciones": (Agrupacion, FormularioAgrupacion, "agrupacion"),
    "motivos": (MotivoBaja, FormularioMotivo, "motivo_baja"),
    "relaciones": (RelacionContacto, FormularioRelacion, "relacion_contacto"),
    "campos": (CampoContacto, FormularioCampoContacto, "campo_contacto"),
}

TITULOS = {
    "agrupaciones": "Agrupaciones",
    "motivos": "Motivos de baja",
    "relaciones": "Relaciones de contacto",
    "campos": "Campos de contacto",
}


@requiere_permiso(PERMISO)
def catalogo(request, catalogo):
    if catalogo not in CATALOGOS:
        return redirect("configuracion:indice")
    modelo = CATALOGOS[catalogo][0]
    return render(request, "configuracion/catalogo.html", {"elementos": modelo.objects.all(), "catalogo": catalogo, "titulo": TITULOS[catalogo]})


def _guardar_catalogo(request, catalogo, pk=None):
    modelo, clase_formulario, evento = CATALOGOS[catalogo]
    instancia = get_object_or_404(modelo, pk=pk) if pk else None
    antes = model_to_dict(instancia) if instancia else None
    formulario = clase_formulario(request.POST if request.method == "POST" else None, instance=instancia)
    if request.method == "POST" and formulario.is_valid():
        with transaction.atomic():
            if modelo is CampoContacto and formulario.cleaned_data.get("principal"):
                CampoContacto.objects.filter(principal=True).exclude(pk=pk or 0).update(principal=False)
            guardado = formulario.save()
            registrar(f"{evento}_{'cambiado' if antes else 'creado'}", usuario=request.user, objeto=guardado, datos={"antes": antes, "despues": model_to_dict(guardado)}, request=request)
        messages.success(request, "Guardado.")
        return redirect("configuracion:catalogo", catalogo=catalogo)
    titulo = TITULOS[catalogo] + (": nuevo" if instancia is None else f": {instancia}")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": titulo, "boton": "Guardar"})


@requiere_permiso(PERMISO)
def catalogo_nuevo(request, catalogo):
    if catalogo not in CATALOGOS:
        return redirect("configuracion:indice")
    return _guardar_catalogo(request, catalogo)


@requiere_permiso(PERMISO)
def catalogo_editar(request, catalogo, pk):
    if catalogo not in CATALOGOS:
        return redirect("configuracion:indice")
    return _guardar_catalogo(request, catalogo, pk)
