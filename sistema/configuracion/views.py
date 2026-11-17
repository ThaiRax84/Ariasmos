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

from . import marca as marca_negocio
from . import plantillas
from .formularios import (
    FormularioAgrupacion,
    FormularioAjustesAvanzados,
    FormularioCaja,
    FormularioCajaCortes,
    FormularioCarpetaBanco,
    FormularioMarca,
    FormularioLogo,
    FormularioCampoContacto,
    FormularioDenominacion,
    FormularioMedioPago,
    FormularioMoneda,
    FormularioMotivo,
    FormularioNegocio,
    FormularioParametros,
    FormularioReglas,
    FormularioRelacion,
    FormularioVocabulario,
    TOPES_CARPETA,
    guardar_caja,
    valores_caja,
    valores_reglas,
)
from .models import PARAMETROS, VOCABULARIO_BASE, Negocio, Parametro, Vocabulario, con_vocabulario, parametro, vocabulario

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
            messages.error(request, f"Ya se emitieron {vocabulario()['matriculas_min']}: estos ajustes no se pueden cambiar.")
            return redirect("configuracion:avanzado")
        if formulario.is_valid():
            with transaction.atomic():
                bloqueado = Negocio.objects.filter(pk=1, contador_matricula=0).exists()
                if not bloqueado:
                    messages.error(request, f"Ya se emitieron {vocabulario()['matriculas_min']}: estos ajustes no se pueden cambiar.")
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
                Vocabulario.objects.update_or_create(clave=clave, defaults={"texto": formulario.cleaned_data[clave].strip() or antes[clave]})
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
            for clave in formulario.fields:
                Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(formulario.cleaned_data[clave])})
            registrar("parametros_cambiados", usuario=request.user, datos={"cambios": diferencias(antes, {clave: parametro(clave) for clave in PARAMETROS})}, request=request)
        messages.success(request, "Parámetros guardados.")
        return redirect("configuracion:indice")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Parámetros", "boton": "Guardar", "volver": "configuracion:indice"})


@requiere_permiso(PERMISO, reingreso=True)
def reglas(request):
    antes = valores_reglas()
    formulario = FormularioReglas(request.POST if request.method == "POST" else None, valores=antes)
    if request.method == "POST" and formulario.is_valid():
        with transaction.atomic():
            for clave, valor in formulario.valores().items():
                Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})
            registrar("reglas_cambiadas", usuario=request.user, datos={"cambios": diferencias(antes, valores_reglas())}, request=request)
        messages.success(request, "Reglas del negocio guardadas.")
        return redirect("configuracion:indice")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Reglas del negocio", "boton": "Guardar", "volver": "configuracion:indice"})


def registrar_caja(request, antes, despues, origen):
    cambios = diferencias(antes, despues)
    if "calendario_corte" in cambios:
        registrar("calendario_corte_cambiado", usuario=request.user, datos={"cambios": {"calendario_corte": cambios["calendario_corte"]}, "origen": origen}, request=request)
    if cambios:
        registrar("caja_configurada", usuario=request.user, datos={"cambios": cambios, "origen": origen}, request=request)


@requiere_permiso(PERMISO, reingreso=True)
def caja(request):
    antes = valores_caja()
    formulario = FormularioCajaCortes(request.POST if request.method == "POST" else None, valores=antes)
    if request.method == "POST" and formulario.is_valid():
        with transaction.atomic():
            guardar_caja(formulario.valores())
            registrar_caja(request, antes, valores_caja(), "configuracion")
        messages.success(request, "Caja: cortes y retiros guardados.")
        return redirect("configuracion:indice")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Caja: cortes y retiros", "boton": "Guardar", "volver": "configuracion:indice"})


@requiere_permiso(PERMISO, reingreso=True)
def carpeta_banco(request):
    actual = Negocio.objects.get(pk=1)
    antes_topes = {clave: int(parametro(clave)) for clave in TOPES_CARPETA}
    formulario = FormularioCarpetaBanco(request.POST if request.method == "POST" else None, initial={"carpeta_banco": actual.carpeta_banco, **antes_topes})
    if request.method == "POST" and formulario.is_valid():
        nueva = formulario.cleaned_data["carpeta_banco"]
        with transaction.atomic():
            Negocio.objects.filter(pk=1).update(carpeta_banco=nueva)
            for clave, valor in formulario.topes().items():
                Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})
            cambios = diferencias({"carpeta_banco": actual.carpeta_banco, **antes_topes}, {"carpeta_banco": nueva, **formulario.topes()})
            registrar("carpeta_banco_cambiada", usuario=request.user, objeto=actual, datos={"cambios": cambios}, request=request)
        messages.success(request, "Carpeta vigilada guardada." if nueva else "Carpeta vigilada desactivada.")
        return redirect("configuracion:indice")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Carpeta vigilada del banco", "boton": "Guardar", "volver": "configuracion:indice"})


CLAVES_INVENTARIO = ("modulo_inventario", "devoluciones_inventario", "dias_devolucion", "dias_conteo_sin_aprobar", "porcentaje_existencia_baja")


def valores_inventario():
    valores = {clave: int(parametro(clave)) for clave in CLAVES_INVENTARIO}
    valores["modulo_inventario"] = bool(valores["modulo_inventario"])
    valores["devoluciones_inventario"] = bool(valores["devoluciones_inventario"])
    return valores


@requiere_permiso(PERMISO, reingreso=True)
def inventario(request):
    from inventario.formularios import FormularioConfiguracion

    antes = valores_inventario()
    formulario = FormularioConfiguracion(request.POST if request.method == "POST" else None, initial=antes)
    if request.method == "POST" and formulario.is_valid():
        with transaction.atomic():
            for clave in CLAVES_INVENTARIO:
                valor = formulario.cleaned_data[clave]
                if valor is None:
                    valor = antes[clave]
                Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(int(valor))})
            cambios = diferencias(antes, valores_inventario())
            if cambios:
                registrar("inventario_configurado", usuario=request.user, datos={"cambios": cambios}, request=request)
        messages.success(request, "Inventario guardado.")
        return redirect("configuracion:indice")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Inventario", "boton": "Guardar", "volver": "configuracion:indice"})


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
    "agrupaciones": "{agrupaciones}",
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
    return render(request, "configuracion/catalogo.html", {"elementos": modelo.objects.all(), "catalogo": catalogo, "titulo": con_vocabulario(TITULOS[catalogo])})


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
    titulo = con_vocabulario(TITULOS[catalogo]) + (": nuevo" if instancia is None else f": {instancia}")
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


def _contrastes(actual):
    if actual is None or not actual.con_colores:
        return None
    valores = marca_negocio.variables(actual.color_principal, actual.color_acento)
    blanco = marca_negocio.contraste(marca_negocio.BLANCO, actual.color_principal)
    return {
        "blanco_sobre_principal": round(blanco, 1),
        "botones_con_tinta": valores["--boton-fondo"] != actual.color_principal,
        "tinta_es_principal": valores["--tinta"] == actual.color_principal,
    }


def propuesta_del_logo(actual):
    from . import colores_logo

    from caja import comprobantes

    try:
        contenido = marca_negocio.leer_logo(actual)
    except (OSError, comprobantes.ComprobanteInvalido):
        raise marca_negocio.MarcaInvalida("No se pudo leer el logo.")
    if not contenido:
        raise marca_negocio.MarcaInvalida("No hay logo del que tomar los colores.")
    return colores_logo.proponer(contenido)


@requiere_permiso(PERMISO, reingreso=True)
def marca(request):
    actual = marca_negocio.actual()
    inicial = {"color_principal": actual.color_principal if actual else "", "color_acento": actual.color_acento if actual else ""}
    propuesta = request.session.pop("propuesta_marca", None)
    if propuesta:
        inicial = {"color_principal": propuesta["principal"], "color_acento": propuesta["acento"]}
    colores = FormularioMarca(initial=inicial)
    logo = FormularioLogo()
    if request.method == "POST":
        accion = request.POST.get("accion", "")
        try:
            if accion == "colores_logo":
                propuesta = propuesta_del_logo(actual)
                colores = FormularioMarca(initial={"color_principal": propuesta["principal"], "color_acento": propuesta["acento"]})
                registrar("marca_colores_propuestos", usuario=request.user, datos={"principal": propuesta["principal"], "acento": propuesta["acento"], "origen": propuesta["origen"]}, request=request)
                messages.info(request, "Estos son los colores tomados del logo. Revísalos en la vista previa y guárdalos si te gustan.")
            elif accion == "colores":
                colores = FormularioMarca(request.POST)
                if colores.is_valid():
                    marca_negocio.guardar_colores(colores.cleaned_data["color_principal"], colores.cleaned_data["color_acento"], request.user, request)
                    messages.success(request, "Colores del negocio guardados.")
                    return redirect("configuracion:marca")
            elif accion == "sin_colores":
                marca_negocio.guardar_colores("", "", request.user, request)
                messages.success(request, "Se usan otra vez los colores de Ariasmos.")
                return redirect("configuracion:marca")
            elif accion == "logo":
                logo = FormularioLogo(request.POST, request.FILES)
                if logo.is_valid():
                    guardada = marca_negocio.guardar_logo(marca_negocio.leer_subida(logo.cleaned_data["archivo"]), request.user, request)
                    request.session["propuesta_marca"] = propuesta_del_logo(guardada)
                    messages.success(request, "Logo del negocio guardado. Te proponemos los colores tomados del logo: revísalos y guárdalos, o elige otros.")
                    return redirect("configuracion:marca")
            elif accion == "quitar_logo":
                marca_negocio.quitar_logo(request.user, request)
                messages.success(request, "Logo quitado: se muestra solo el nombre del negocio.")
                return redirect("configuracion:marca")
            else:
                messages.error(request, "Acción no válida.")
        except marca_negocio.MarcaInvalida as error:
            registrar("marca_rechazada", usuario=request.user, datos={"accion": accion[:20], "motivo": str(error)}, request=request)
            (logo if accion == "logo" else colores).add_error(None, str(error))
    vista = None
    principal, acento = colores["color_principal"].value() or "", colores["color_acento"].value() or ""
    if principal and acento:
        try:
            vista = {"principal": marca_negocio.validar_color(principal), "acento": marca_negocio.validar_color(acento)}
        except marca_negocio.MarcaInvalida:
            vista = None
    return render(request, "configuracion/marca.html", {"colores": colores, "logo": logo, "actual": actual, "contrastes": _contrastes(actual), "vista": vista, "propuesta": bool(propuesta)})
