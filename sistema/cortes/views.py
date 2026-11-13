from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.servicios import diferencias, registrar
from cuentas.decoradores import requiere_permiso

from . import salida, servicios
from .formularios import FormularioDestino
from .models import COMPLETO, MAYOR, Corte, DefinicionCorte, Destino, Entrega

VEN = ("turno_caja", "ver_cortes")
CONFIGURA = "administrar_configuracion"
TIPOS_DESCARGA = {"pdf": "application/pdf", "csv": "text/csv; charset=utf-8", "json": "application/json; charset=utf-8"}


def _corte_visible(request, pk):
    corte = get_object_or_404(Corte.objects.select_related("caja", "usuario", "cerrado_por"), pk=pk)
    if not servicios.puede_ver(request.user, corte):
        registrar("acceso_denegado", request=request, objeto=corte, datos={"accion": "ver_corte"})
        raise PermissionDenied
    return corte


@requiere_permiso(*VEN)
def lista(request):
    cortes = servicios.visibles(request.user).select_related("caja", "usuario")[:300]
    contexto = {"cortes": cortes, "ve_todos": request.user.tiene_permiso("ver_cortes")}
    if contexto["ve_todos"]:
        contexto["pendientes"] = servicios.diarios_pendientes()
    return render(request, "cortes/lista.html", contexto)


@requiere_permiso(*VEN)
def detalle(request, pk):
    corte = _corte_visible(request, pk)
    corte = servicios.recalcular(corte)
    datos = salida.vista(corte.cifras, COMPLETO)
    codigo = datos.get("moneda", "")
    resumen = [(salida.etiqueta(k), salida.texto_celda(k, v, codigo, pdf=True)) for k, v in salida.resumen(datos).items()]
    tablas = [
        {"titulo": t["titulo"], "columnas": [salida.etiqueta(c) for c in t["columnas"]], "filas": [[salida.texto_celda(c, f.get(c), codigo, pdf=True) for c in t["columnas"]] for f in t["filas"]]}
        for t in salida.tablas(datos)
    ]
    contexto = {
        "corte": corte,
        "resumen": resumen,
        "tablas": tablas,
        "puede_cerrar": corte.tipo == MAYOR and not corte.cerrado and request.user.tiene_permiso("cerrar_cortes"),
        "entregas": corte.entregas.select_related("destino") if request.user.tiene_permiso("ver_cortes") else [],
    }
    return render(request, "cortes/detalle.html", contexto)


@requiere_permiso(*VEN)
def descargar(request, pk, formato):
    corte = _corte_visible(request, pk)
    corte = servicios.recalcular(corte)
    datos = salida.vista(corte.cifras, COMPLETO)
    if formato == "pdf":
        contenido = salida.a_pdf(datos, request.negocio.nombre if getattr(request, "negocio", None) else "")
    elif formato == "csv":
        contenido = salida.a_csv(datos)
    else:
        contenido = salida.a_json(datos)
    registrar("corte_descargado", request=request, objeto=corte, datos={"formato": formato})
    respuesta = HttpResponse(contenido, content_type=TIPOS_DESCARGA[formato])
    respuesta["Content-Disposition"] = f'attachment; filename="{salida.nombre_base(corte)}.{formato}"'
    return respuesta


@requiere_permiso("cerrar_cortes", reingreso=True)
@require_POST
def cerrar(request, pk):
    corte = get_object_or_404(Corte, pk=pk, tipo=MAYOR)
    try:
        servicios.cerrar_mayor(corte, request.user, request=request)
    except servicios.ErrorCorte as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Corte cerrado: el periodo quedó bloqueado y las entregas están en camino.")
    return redirect("cortes:detalle", pk=pk)


@requiere_permiso("ver_cortes")
@require_POST
def cobranza(request):
    corte = servicios.generar_cobranza(usuario=request.user, request=request)
    return redirect("cortes:detalle", pk=corte.pk)


@requiere_permiso(CONFIGURA)
def destinos(request):
    contexto = {
        "destinos": Destino.objects.prefetch_related("reglas"),
        "problemas": servicios.entregas_con_problema()[:50],
        "recientes": Entrega.objects.select_related("corte", "destino")[:30],
    }
    return render(request, "cortes/destinos.html", contexto)


def _niveles():
    return {d.tipo: d.nivel for d in DefinicionCorte.objects.all()}


def _reglas(destino):
    return {r.tipo: [r.entregar, r.nivel] for r in destino.reglas.all()} if destino and destino.pk else {}


@requiere_permiso(CONFIGURA, reingreso=True)
def destino_editar(request, pk=None):
    objeto = get_object_or_404(Destino, pk=pk) if pk else None
    antes = {"ruta": objeto.ruta, "activo": objeto.activo, "reglas": _reglas(objeto)} if objeto else {}
    formulario = FormularioDestino(request.POST if request.method == "POST" else None, destino=objeto, niveles=_niveles())
    if request.method == "POST" and formulario.is_valid():
        guardado = formulario.guardar(objeto)
        despues = {"ruta": guardado.ruta, "activo": guardado.activo, "reglas": _reglas(guardado)}
        registrar("destino_guardado", request=request, objeto=guardado, datos={"cambios": diferencias(antes, despues)})
        messages.success(request, "Destino guardado: la carpeta existe y se puede escribir en ella.")
        return redirect("cortes:destinos")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Destino de entrega" if objeto else "Nuevo destino de entrega", "boton": "Guardar", "volver": "cortes:destinos"})


@requiere_permiso(CONFIGURA)
@require_POST
def reintentar(request, pk):
    objeto = get_object_or_404(Entrega, pk=pk)
    Entrega.objects.filter(pk=objeto.pk).exclude(estado=Entrega.ENTREGADA).update(estado=Entrega.PENDIENTE, proximo_intento=None, ocupada_hasta=None)
    registrar("entrega_reintentada", request=request, objeto=objeto.corte, datos={"entrega": objeto.pk})
    messages.info(request, "La entrega se reintentará en el siguiente ciclo del trabajador.")
    return redirect("cortes:destinos")


