import csv
from io import StringIO

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.servicios import registrar
from configuracion.models import vocabulario
from cuentas.decoradores import requiere_permiso, requiere_sesion
from nucleo import dinero
from nucleo.exportar import neutralizar
from titulares.models import Titular

from . import calculo, presentacion, servicios, tras_alta
from .formularios import FormularioExcepcion, FormularioLimites, FormularioOrden, FormularioRecargosAlta, FormularioRegla
from .models import ExcepcionLimite, LimiteAdeudo, ReglaRezago

LIMITES = "configurar_limites_adeudo"
REGLAS = "configurar_rezagos"


def _sin_cache(respuesta):
    respuesta["Cache-Control"] = "no-store"
    return respuesta


@requiere_sesion
def lista(request):
    ver_saldos = presentacion.ve_saldos(request.user)
    orden = FormularioOrden(request.GET or None, ver_saldos=ver_saldos)
    elegido = orden.elegido()
    filas = presentacion.lista_para(request.user, elegido)
    return _sin_cache(render(request, "rezagos/lista.html", {"filas": filas, "orden": orden, "elegido": elegido, "ver_saldos": ver_saldos}))


@requiere_permiso("ver_titulares")
def exportar(request):
    filas = presentacion.lista_para(request.user, FormularioOrden(request.GET or None, ver_saldos=True).elegido())
    voc = vocabulario()
    salida = StringIO()
    escritor = csv.writer(salida)
    escritor.writerow([voc["titular"], voc["matricula"], voc["agrupacion"], "Días de atraso", "Adeudo vencido", "Aviso", "Marcas", "Sin crédito"])
    for fila in filas:
        escritor.writerow([neutralizar(v) for v in (fila["nombre"], fila["matricula"], fila["agrupacion"], fila["dias"], dinero.a_texto(fila["adeudo"]), fila["texto"], "; ".join(fila["marcas"]), "sí" if fila["sin_credito"] else "no")])
    registrar("rezagados_exportados", request=request, datos={"renglones": len(filas)})
    respuesta = HttpResponse(salida.getvalue().encode("utf-8-sig"), content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="rezagados.csv"'
    respuesta["X-Content-Type-Options"] = "nosniff"
    return _sin_cache(respuesta)


@requiere_permiso(LIMITES, reingreso=True)
def limites(request):
    actual = LimiteAdeudo.actual()
    inicial = {"modo_importe": actual.modo_importe, "importe_maximo": actual.importe_maximo, "modo_dias": actual.modo_dias, "dias_maximos": actual.dias_maximos}
    formulario = FormularioLimites(request.POST if request.method == "POST" else None, initial=inicial)
    if request.method == "POST" and formulario.is_valid():
        cambiaron = servicios.guardar_limites(formulario.cleaned_data, request.user, request)
        messages.success(request, "Límites guardados." if cambiaron else "Los límites no cambiaron.")
        return redirect("rezagos:limites")
    excepciones = ExcepcionLimite.objects.select_related("titular", "titular__agrupacion")
    filas = [
        {
            "excepcion": e,
            "importe": presentacion.texto_limite(e.modo_importe, e.importe_maximo, True),
            "dias": presentacion.texto_limite(e.modo_dias, e.dias_maximos, False),
        }
        for e in excepciones
    ]
    situaciones = calculo.evaluar()
    contexto = {
        "formulario": formulario,
        "excepciones": filas,
        "rebasan": sum(1 for s in situaciones.values() if s.rebasa),
        "sin_credito": sum(1 for s in situaciones.values() if s.sin_credito),
    }
    return _sin_cache(render(request, "rezagos/limites.html", contexto))


@requiere_permiso(LIMITES, reingreso=True)
def excepcion(request, pk):
    titular = get_object_or_404(Titular, pk=pk)
    actual = ExcepcionLimite.objects.filter(titular=titular).first()
    inicial = {"modo_importe": "negocio", "modo_dias": "negocio"}
    if actual is not None:
        inicial = {"modo_importe": actual.modo_importe, "importe_maximo": actual.importe_maximo, "modo_dias": actual.modo_dias, "dias_maximos": actual.dias_maximos, "motivo": actual.motivo, "vigente_hasta": actual.vigente_hasta}
    formulario = FormularioExcepcion(request.POST if request.method == "POST" else None, initial=inicial, existente=actual is not None)
    if request.method == "POST" and formulario.is_valid():
        cambio = servicios.guardar_excepcion(titular, formulario.cleaned_data, request.user, request)
        if formulario.cleaned_data.get("quitar"):
            messages.success(request, "Excepción quitada: vale el límite del negocio.")
        else:
            messages.success(request, "Excepción guardada." if cambio else "La excepción no cambió.")
        return redirect("rezagos:limites")
    negocio = LimiteAdeudo.actual()
    contexto = {
        "formulario": formulario,
        "titular": titular,
        "existente": actual,
        "negocio_importe": presentacion.texto_limite(negocio.modo_importe, negocio.importe_maximo, True),
        "negocio_dias": presentacion.texto_limite(negocio.modo_dias, negocio.dias_maximos, False),
    }
    return _sin_cache(render(request, "rezagos/excepcion.html", contexto))


@requiere_permiso(REGLAS)
def reglas(request):
    lista_reglas = ReglaRezago.objects.select_related("agrupacion", "titular")
    return _sin_cache(render(request, "rezagos/reglas.html", {"reglas": lista_reglas}))


def _inicial_regla(regla):
    if regla is None:
        return {"alcance": ReglaRezago.TODOS, "activa": True}
    inicial = {campo: getattr(regla, campo) for campo in ("nombre", "texto", "alcance", "dias_minimos", "importe_minimo", "al_rebasar_limite", "activa") + ReglaRezago.ACCIONES}
    inicial["agrupacion"] = regla.agrupacion_id
    inicial["matricula"] = regla.titular.matricula_formateada if regla.titular_id else ""
    return inicial


def _regla(request, regla):
    formulario = FormularioRegla(request.POST if request.method == "POST" else None, initial=_inicial_regla(regla))
    if request.method == "POST" and formulario.is_valid():
        guardada = servicios.guardar_regla(regla or ReglaRezago(), formulario.cleaned_data, request.user, request)
        messages.success(request, f"Regla «{guardada.nombre}» guardada.")
        return redirect("rezagos:reglas")
    titulo = f"Editar «{regla.nombre}»" if regla else "Nueva regla de rezago"
    return _sin_cache(render(request, "rezagos/regla.html", {"formulario": formulario, "titulo": titulo}))


@requiere_permiso(REGLAS)
def regla_nueva(request):
    return _regla(request, None)


@requiere_permiso(REGLAS)
def regla_editar(request, pk):
    return _regla(request, get_object_or_404(ReglaRezago.objects.select_related("titular"), pk=pk))


@requiere_permiso("administrar_conceptos")
def recargos_alta(request):
    formulario = FormularioRecargosAlta(request.POST if request.method == "POST" else None, initial={"recargos_tras_alta": tras_alta.modo()})
    if request.method == "POST" and formulario.is_valid():
        cambio = servicios.guardar_recargos_tras_alta(formulario.cleaned_data["recargos_tras_alta"], request.user, request)
        messages.success(request, "Guardado." if cambio else "No cambió.")
        return redirect("rezagos:recargos_alta")
    return render(request, "rezagos/recargos_alta.html", {"formulario": formulario})
