from django.contrib import messages
from django.db import transaction
from django.forms.models import model_to_dict
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.servicios import diferencias, registrar
from cuentas.decoradores import requiere_permiso
from banco.models import MedioPago
from caja.models import Caja, Denominacion
from cobros.models import Cargo, Pago
from titulares.models import Agrupacion, CampoContacto, MotivoBaja, RelacionContacto

from . import plantillas
from .formularios import (
    FormularioAgrupacion,
    FormularioAjustesAvanzados,
    FormularioCaja,
    FormularioCampoContacto,
    FormularioDenominacion,
    FormularioMedioPago,
    FormularioMoneda,
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
        registrar("configuracion_cambiada", usuario=request.user, objeto=guardado, datos={"cambios": diferencias(antes, model_to_dict(guardado))}, request=request)
        messages.success(request, "Configuración guardada.")
        return redirect("configuracion:indice")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Datos del negocio", "boton": "Guardar", "volver": "configuracion:indice"})


@requiere_permiso(PERMISO, reingreso=True)
def avanzado(request):
    actual = Negocio.objects.get(pk=1)
    antes = model_to_dict(actual, fields=["longitud_matricula", "sede", "ranuras"])
    formulario = FormularioAjustesAvanzados(request.POST if request.method == "POST" else None, instance=actual)
    if request.method == "POST":
        if actual.matriculas_emitidas:
            registrar("ajustes_avanzados_rechazados", usuario=request.user, objeto=actual, datos={"motivo": "matriculas_emitidas"}, request=request)
            messages.error(request, "Ya se emitieron matrículas: estos ajustes no se pueden cambiar.")
            return redirect("configuracion:avanzado")
        if formulario.is_valid():
            with transaction.atomic():
                bloqueado = Negocio.objects.filter(pk=1, contador_matricula=0).exists()
                if not bloqueado:
                    messages.error(request, "Ya se emitieron matrículas: estos ajustes no se pueden cambiar.")
                    return redirect("configuracion:avanzado")
                guardado = formulario.save()
                registrar("configuracion_cambiada", usuario=request.user, objeto=guardado, datos={"cambios": diferencias(antes, model_to_dict(guardado, fields=list(antes)))}, request=request)
            messages.success(request, "Ajustes guardados.")
            return redirect("configuracion:indice")
    return render(request, "configuracion/avanzado.html", {"formulario": formulario, "bloqueado": actual.matriculas_emitidas, **_contexto_moneda(actual)})


def moneda_bloqueada():
    return Cargo.objects.exists() or Pago.objects.exists()


def _contexto_moneda(actual, formulario=None):
    bloqueada = moneda_bloqueada()
    return {"formulario_moneda": formulario or FormularioMoneda(initial={"moneda": actual.moneda}, bloqueada=bloqueada), "moneda_bloqueada": bloqueada}


@requiere_permiso(PERMISO, reingreso=True)
@require_POST
def cambiar_moneda(request):
    actual = Negocio.objects.get(pk=1)
    if moneda_bloqueada():
        registrar("moneda_rechazada", usuario=request.user, objeto=actual, datos={"motivo": "ya_hay_movimientos", "pedida": str(request.POST.get("moneda", ""))[:3]}, request=request)
        messages.error(request, "Ya hay cargos o pagos registrados: la moneda no se puede cambiar.")
        return redirect("configuracion:avanzado")
    formulario = FormularioMoneda(request.POST)
    if not formulario.is_valid():
        return render(request, "configuracion/avanzado.html", {"formulario": FormularioAjustesAvanzados(instance=actual), "bloqueado": actual.matriculas_emitidas, **_contexto_moneda(actual, formulario)})
    nueva = formulario.cleaned_data["moneda"]
    with transaction.atomic():
        if moneda_bloqueada():
            registrar("moneda_rechazada", usuario=request.user, objeto=actual, datos={"motivo": "ya_hay_movimientos", "pedida": nueva}, request=request)
            messages.error(request, "Ya hay cargos o pagos registrados: la moneda no se puede cambiar.")
            return redirect("configuracion:avanzado")
        if nueva != actual.moneda:
            Negocio.objects.filter(pk=1).update(moneda=nueva)
            quitadas = Denominacion.objects.filter(activa=True).update(activa=False)
            registrar("moneda_cambiada", usuario=request.user, objeto=actual, datos={"cambios": {"moneda": [actual.moneda, nueva]}, "denominaciones_desactivadas": quitadas}, request=request)
            messages.success(request, f"Moneda cambiada a {nueva}. Captura las denominaciones de caja de la nueva moneda.")
    return redirect("configuracion:avanzado")


@requiere_permiso(PERMISO, reingreso=True)
def exportar(request):
    try:
        datos = plantillas.exportar()
    except plantillas.ErrorPlantilla as error:
        messages.error(request, str(error))
        return redirect("configuracion:indice")
    registrar("plantilla_exportada", usuario=request.user, datos={"roles": len(datos["roles"]), "conceptos": len(datos["conceptos"])}, request=request)
    respuesta = HttpResponse(plantillas.a_json(datos), content_type="application/json; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="plantilla.json"'
    return respuesta


@requiere_permiso(PERMISO, reingreso=True)
def textos(request):
    antes = vocabulario()
    formulario = FormularioVocabulario(request.POST if request.method == "POST" else None, textos=antes)
    if request.method == "POST" and formulario.is_valid():
        with transaction.atomic():
            for clave in VOCABULARIO_BASE:
                Vocabulario.objects.update_or_create(clave=clave, defaults={"texto": formulario.cleaned_data[clave]})
            registrar("vocabulario_cambiado", usuario=request.user, datos={"cambios": diferencias(antes, vocabulario())}, request=request)
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
            registrar("parametros_cambiados", usuario=request.user, datos={"cambios": diferencias(antes, {clave: parametro(clave) for clave in PARAMETROS})}, request=request)
        messages.success(request, "Parámetros guardados.")
        return redirect("configuracion:indice")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Parámetros", "boton": "Guardar", "volver": "configuracion:indice"})


CATALOGOS = {
    "agrupaciones": (Agrupacion, FormularioAgrupacion, "agrupacion"),
    "motivos": (MotivoBaja, FormularioMotivo, "motivo_baja"),
    "relaciones": (RelacionContacto, FormularioRelacion, "relacion_contacto"),
    "campos": (CampoContacto, FormularioCampoContacto, "campo_contacto"),
    "medios": (MedioPago, FormularioMedioPago, "medio_pago"),
    "cajas": (Caja, FormularioCaja, "caja"),
    "denominaciones": (Denominacion, FormularioDenominacion, "denominacion"),
}

TITULOS = {
    "agrupaciones": "Agrupaciones",
    "motivos": "Motivos de baja",
    "relaciones": "Relaciones de contacto",
    "campos": "Campos de contacto",
    "medios": "Medios de pago",
    "cajas": "Cajas",
    "denominaciones": "Denominaciones para el arqueo",
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
            registrar(f"{evento}_{'cambiado' if antes else 'creado'}", usuario=request.user, objeto=guardado, datos={"nombre": str(guardado), "cambios": diferencias(antes or {}, model_to_dict(guardado))}, request=request)
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
