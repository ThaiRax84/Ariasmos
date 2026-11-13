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
from titulares import fichas_pdf, padron
from titulares.models import LotePadron

PERMISO = "administrar_configuracion"


class FormularioArchivo(forms.Form):
    archivo = forms.FileField(label="Padrón en Excel (.xlsx) o CSV, hasta 5 MB")


class FormularioColumnas(forms.Form):
    def __init__(self, *args, filas=None, encabezado=0, propuesta=None, **kwargs):
        super().__init__(*args, **kwargs)
        titulos = filas[encabezado]
        muestra = filas[encabezado + 1] if len(filas) > encabezado + 1 else [""] * len(titulos)
        opciones = [("", "— no usar —")] + [(str(i), f"{t or f'Columna {i + 1}'} (ej. {muestra[i][:20] if i < len(muestra) else ''})") for i, t in enumerate(titulos)]
        etiquetas = {"nombre": "Nombre", "apellidos": "Apellidos", "nombre_completo": "Nombre completo", "agrupacion": "Agrupación", "responsable": "Responsable", "telefono": "Teléfono", "correo": "Correo", "saldo_total": "Saldo total (positivo si debe, negativo si tiene a favor)"}
        propuesta = propuesta or {}
        for papel in padron.PAPELES:
            self.fields[papel] = forms.ChoiceField(label=etiquetas[papel], choices=opciones, required=False, initial=str(propuesta[papel]) if papel in propuesta else "")
        self.fields["concepto_saldo_total"] = forms.ModelChoiceField(label="Concepto al que se carga el saldo total", queryset=ConceptoCobro.objects.filter(activo=True), required=False)
        for concepto in ConceptoCobro.objects.filter(activo=True):
            clave = f"saldo_{concepto.pk}"
            self.fields[clave] = forms.ChoiceField(label=f"Saldo de {concepto}", choices=opciones, required=False, initial=str(propuesta[clave]) if clave in propuesta else "")

    def columnas(self):
        return {papel: int(valor) for papel, valor in self.cleaned_data.items() if papel != "concepto_saldo_total" and valor not in ("", None)}


@requiere_permiso(PERMISO, reingreso=True)
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
    return render(request, "configuracion/padron_subir.html", {"formulario": formulario})


@requiere_permiso(PERMISO, reingreso=True)
def revisar(request, token):
    carga = carga_de(request, token, [CargaTemporal.PADRON])
    datos = carga.datos
    if request.method == "POST" and request.POST.get("paso") == "confirmar" and "analisis" in datos:
        aceptadas = [int(v) for v in request.POST.getlist("familia") if v.isdigit()]
        with transaction.atomic():
            if not CargaTemporal.objects.filter(pk=carga.pk).delete()[0]:
                messages.error(request, "Esta importación ya se confirmó.")
                return redirect("configuracion:indice")
            lote = padron.aplicar(datos["analisis"], aceptadas, request.user, carga.nombre_archivo, carga.sha256, request)
        messages.success(request, f"Se dieron de alta {lote.creados} registros.")
        return redirect("configuracion:padron_lote", pk=lote.pk)
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
    contexto = {
        "carga": carga,
        "formulario": formulario,
        "analisis": analisis,
        "validos": sum(1 for f in analisis["filas"] if not f["errores"] and not f["duplicado"]) if analisis else 0,
        "muestra": datos["filas"][datos["encabezado"]: datos["encabezado"] + 6],
    }
    return render(request, "configuracion/padron_revisar.html", contexto)


@requiere_permiso(PERMISO, reingreso=True)
def lote(request, pk):
    objeto = get_object_or_404(LotePadron, pk=pk)
    return render(request, "configuracion/padron_lote.html", {"lote": objeto, "titulares": padron.titulares_de(objeto)})


def _descarga(contenido, tipo, nombre):
    respuesta = HttpResponse(contenido, content_type=tipo)
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


@requiere_permiso(PERMISO, reingreso=True)
def matriculas(request, pk, formato):
    objeto = get_object_or_404(LotePadron, pk=pk)
    registrar("padron_exportado", request=request, datos={"lote": objeto.pk, "formato": formato})
    if formato == "xlsx":
        return _descarga(padron.a_xlsx(objeto), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"matriculas-{objeto.pk}.xlsx")
    return _descarga(padron.a_csv(objeto), "text/csv; charset=utf-8", f"matriculas-{objeto.pk}.csv")


@requiere_permiso(PERMISO, reingreso=True)
def fichas(request, pk):
    objeto = get_object_or_404(LotePadron, pk=pk)
    titulares = padron.titulares_de(objeto)
    for titular in titulares:
        registrar("ficha_pago_consultada", objeto=titular, request=request, datos={"lote": objeto.pk})
    return _descarga(fichas_pdf.generar(titulares, getattr(request, "negocio", None)), "application/pdf", f"fichas-{objeto.pk}.pdf")
