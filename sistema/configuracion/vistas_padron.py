import secrets

from django import forms
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.servicios import registrar
from banco import lectura
from banco.models import CargaTemporal, depurar_cargas
from banco.vistas_conciliacion import carga_de
from cobros.models import ConceptoCobro
from cuentas.decoradores import requiere_permiso
from solicitudes import motor
from titulares import fichas_pdf, padron
from titulares.models import LotePadron

from .models import vocabulario

PERMISOS = ("importar_padron", "solicitar_importacion_padron")
ETIQUETAS_CAMBIO = {"nombre": "Nombre", "apellidos": "Apellidos", "agrupacion": "{agrupacion}", "responsable": "Responsable", "telefono": "Teléfono", "correo": "Correo"}


class FormularioArchivo(forms.Form):
    archivo = forms.FileField(label="Hoja en Excel (.xlsx) o CSV, hasta 5 MB")


class FormularioColumnas(forms.Form):
    def __init__(self, *args, filas=None, encabezado=0, propuesta=None, **kwargs):
        super().__init__(*args, **kwargs)
        titulos = filas[encabezado]
        muestra = filas[encabezado + 1] if len(filas) > encabezado + 1 else [""] * len(titulos)
        opciones = [("", "— no usar —")] + [(str(i), f"{t or f'Columna {i + 1}'} (ej. {muestra[i][:20] if i < len(muestra) else ''})") for i, t in enumerate(titulos)]
        voc = vocabulario()
        etiquetas = {
            "matricula": f"{voc['matricula']} (solo para actualizar registros que ya existen)", "nombre": "Nombre", "apellidos": "Apellidos", "nombre_completo": "Nombre completo",
            "agrupacion": voc["agrupacion"], "responsable": "Responsable", "telefono": "Teléfono", "correo": "Correo", "saldo_total": "Saldo total (solo en altas; positivo si debe, negativo si tiene a favor)",
        }
        propuesta = propuesta or {}
        for papel in padron.PAPELES:
            self.fields[papel] = forms.ChoiceField(label=etiquetas[papel], choices=opciones, required=False, initial=str(propuesta[papel]) if papel in propuesta else "")
        self.fields["concepto_saldo_total"] = forms.ModelChoiceField(label="Concepto al que se carga el saldo total", queryset=ConceptoCobro.objects.filter(activo=True), required=False)
        for concepto in ConceptoCobro.objects.filter(activo=True):
            clave = f"saldo_{concepto.pk}"
            self.fields[clave] = forms.ChoiceField(label=f"Saldo de {concepto} (solo en altas)", choices=opciones, required=False, initial=str(propuesta[clave]) if clave in propuesta else "")

    def columnas(self):
        return {papel: int(valor) for papel, valor in self.cleaned_data.items() if papel != "concepto_saldo_total" and valor not in ("", None)}


def detalle_cambios(fila, ve_datos):
    from .models import con_vocabulario

    voc = vocabulario()
    return [(con_vocabulario(ETIQUETAS_CAMBIO.get(campo, campo), voc), antes if ve_datos else "", despues) for campo, (antes, despues) in fila.get("cambios", {}).items()]


def _previa(analisis, ve_datos):
    filas = []
    for fila in analisis["filas"]:
        filas.append(dict(fila, detalle=detalle_cambios(fila, ve_datos) if fila.get("tipo") == "cambio" else [], saldos=fila["saldos"] if ve_datos else []))
    return filas


@requiere_permiso(*PERMISOS, reingreso=True)
def subir(request):
    depurar_cargas()
    formulario = FormularioArchivo(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        archivo = formulario.cleaned_data["archivo"]
        try:
            contenido = lectura.leer_subida(archivo, lectura.LIMITE_HOJA)
            nombre = lectura.nombre_saneado(archivo.name)
            filas = lectura.filas_de_hoja(nombre, contenido)
        except lectura.ErrorLectura as error:
            formulario.add_error("archivo", str(error))
        else:
            encabezado, propuesta = padron.proponer(filas)
            carga = CargaTemporal.objects.create(
                token=secrets.token_urlsafe(32), tipo=CargaTemporal.PADRON, usuario=request.user, nombre_archivo=nombre,
                sha256=lectura.huella_archivo(contenido), datos={"filas": filas, "encabezado": encabezado, "propuesta": propuesta},
            )
            return redirect("configuracion:padron_revisar", token=carga.token)
    return render(request, "configuracion/padron_subir.html", {"formulario": formulario, "directo": request.user.tiene_permiso("importar_padron")})


def _confirmar(request, carga, datos):
    aceptadas = [int(v) for v in request.POST.getlist("familia") if v.isdigit()]
    hoja = None
    try:
        with transaction.atomic():
            if not CargaTemporal.objects.filter(pk=carga.pk).delete()[0]:
                messages.error(request, "Esta importación ya se confirmó.")
                return redirect("titulares:lista")
            hoja, huella = padron.guardar_hoja(datos["analisis"])
            datos_solicitud = {"hoja": hoja, "huella": huella, "nombre_archivo": carga.nombre_archivo, "sha256": carga.sha256, "familias": aceptadas, **padron.resumen(datos["analisis"])}
            resultado = motor.ejecutar("importacion_padron", request.user, None, datos_solicitud, request=request)
    except motor.ErrorSolicitud as error:
        padron.borrar_hoja(hoja or "")
        messages.error(request, str(error))
        return redirect("configuracion:padron_subir")
    except Exception:
        padron.borrar_hoja(hoja or "")
        raise
    if resultado.solicitud is not None:
        messages.info(request, "La hoja quedó como una sola solicitud. Cuando la aprueben se aplicará completa; mientras, nada cambia.")
        return redirect("solicitudes:detalle", pk=resultado.solicitud.pk)
    lote = resultado.objeto
    messages.success(request, f"Se dieron de alta {lote.creados} registros y se actualizaron {lote.actualizados}.")
    return redirect("configuracion:padron_lote", pk=lote.pk)


@requiere_permiso(*PERMISOS, reingreso=True)
def revisar(request, token):
    carga = carga_de(request, token, [CargaTemporal.PADRON])
    datos = carga.datos
    if request.method == "POST" and request.POST.get("paso") == "confirmar" and "analisis" in datos:
        return _confirmar(request, carga, datos)
    formulario = FormularioColumnas(request.POST if request.method == "POST" else None, filas=datos["filas"], encabezado=datos["encabezado"], propuesta=datos.get("columnas") or datos["propuesta"])
    analisis = None
    if request.method == "POST" and formulario.is_valid():
        concepto = formulario.cleaned_data.get("concepto_saldo_total")
        try:
            analisis = padron.analizar(datos["filas"], datos["encabezado"], formulario.columnas(), concepto.pk if concepto else None)
        except padron.ErrorPadron as error:
            formulario.add_error(None, str(error))
        else:
            datos.update({"analisis": analisis, "columnas": formulario.columnas()})
            CargaTemporal.objects.filter(pk=carga.pk).update(datos=datos)
    ve_datos = request.user.tiene_permiso("ver_titulares")
    contexto = {
        "carga": carga,
        "formulario": formulario,
        "analisis": analisis,
        "filas_previa": _previa(analisis, ve_datos) if analisis else [],
        "resumen": padron.resumen(analisis) if analisis else None,
        "validos": sum(1 for f in analisis["filas"] if not f["errores"] and not f["duplicado"]) if analisis else 0,
        "muestra": datos["filas"][datos["encabezado"]: datos["encabezado"] + 6],
        "ve_datos": ve_datos,
        "directo": request.user.tiene_permiso("importar_padron"),
    }
    return render(request, "configuracion/padron_revisar.html", contexto)


@requiere_permiso(*PERMISOS, reingreso=True)
def lote(request, pk):
    objeto = get_object_or_404(LotePadron, pk=pk)
    return render(request, "configuracion/padron_lote.html", {"lote": objeto, "titulares": padron.titulares_de(objeto), "saltados": objeto.resultado.get("saltados", [])})


def _descarga(contenido, tipo, nombre):
    respuesta = HttpResponse(contenido, content_type=tipo)
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


@requiere_permiso(*PERMISOS, reingreso=True)
def matriculas(request, pk, formato):
    objeto = get_object_or_404(LotePadron, pk=pk)
    registrar("padron_exportado", request=request, datos={"lote": objeto.pk, "formato": formato})
    if formato == "xlsx":
        return _descarga(padron.a_xlsx(objeto), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", padron.nombre_archivo_matriculas(objeto, "xlsx"))
    return _descarga(padron.a_csv(objeto), "text/csv; charset=utf-8", padron.nombre_archivo_matriculas(objeto, "csv"))


@requiere_permiso(*PERMISOS, reingreso=True)
def fichas(request, pk):
    objeto = get_object_or_404(LotePadron, pk=pk)
    titulares = padron.titulares_de(objeto)
    for titular in titulares:
        registrar("ficha_pago_consultada", objeto=titular, request=request, datos={"lote": objeto.pk})
    return _descarga(fichas_pdf.generar(titulares, getattr(request, "negocio", None)), "application/pdf", f"fichas-{objeto.pk}.pdf")
