import secrets
from datetime import date, timedelta

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from caja.models import Traslado
from cuentas.decoradores import requiere_permiso
from configuracion.models import Negocio
from nucleo.matricula import normalizar
from proyecto.captura import CampoGuiadoTexto
from titulares.models import Titular

from . import conciliacion, lectura
from .models import HORAS_CARGA, CargaTemporal, CuentaBancaria, Importacion, MovimientoBancario, depurar_cargas

CONCILIA = "conciliar_banco"
VEN_COLA = ("sugerir_conciliacion", "conciliar_banco")
REVISA = "ver_auditoria"


class FormularioSubida(forms.Form):
    archivo = forms.FileField(label="Estado de cuenta (PDF) o archivo de movimientos (Excel .xlsx o CSV)")
    cuenta = forms.ModelChoiceField(label="Cuenta (solo para Excel o CSV; el PDF trae su CLABE)", queryset=CuentaBancaria.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cuenta"].queryset = CuentaBancaria.objects.filter(activa=True).select_related("banco")


class FormularioColumnas(forms.Form):
    def __init__(self, *args, filas=None, encabezado=0, propuesta=None, **kwargs):
        super().__init__(*args, **kwargs)
        titulos = filas[encabezado]
        muestra = filas[encabezado + 1] if len(filas) > encabezado + 1 else [""] * len(titulos)
        opciones = [("", "— no usar —")] + [(str(i), f"{t or f'Columna {i + 1}'} (ej. {muestra[i][:20] if i < len(muestra) else ''})") for i, t in enumerate(titulos)]
        etiquetas = {"fecha": "Fecha", "descripcion": "Descripción", "concepto": "Concepto", "referencia": "Referencia", "abono": "Abonos (depósitos)", "cargo": "Cargos (retiros)", "importe": "Importe con signo", "saldo": "Saldo"}
        for papel in conciliacion.PAPELES:
            valor = (propuesta or {}).get(papel)
            self.fields[papel] = forms.ChoiceField(label=etiquetas[papel], choices=opciones, required=False, initial="" if valor is None else str(valor))

    def columnas(self):
        return {papel: int(valor) for papel, valor in self.cleaned_data.items() if valor not in ("", None)}


class FormularioMatricula(forms.Form):
    matricula = CampoGuiadoTexto(label="Matrícula", max_length=20, acepta="matricula")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        negocio = Negocio.actual()
        self.fields["matricula"].maximo_tecleo = (negocio.longitud_matricula if negocio else 7) + 2

    def clean_matricula(self):
        digitos = normalizar(self.cleaned_data["matricula"])
        titular = Titular.objects.filter(matricula=digitos).exclude(estado=Titular.RECHAZADO).first()
        if titular is None:
            raise forms.ValidationError("No hay un registro con esa matrícula.")
        return titular


class FormularioMotivo(forms.Form):
    motivo = forms.CharField(label="Motivo", max_length=300)


def carga_de(request, token, tipos):
    carga = CargaTemporal.objects.filter(token=token, usuario=request.user, tipo__in=tipos, creada__gte=timezone.now() - timedelta(hours=HORAS_CARGA)).first()
    if carga is None:
        raise Http404
    return carga


@requiere_permiso(CONCILIA)
def importar(request):
    depurar_cargas()
    formulario = FormularioSubida(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        archivo = formulario.cleaned_data["archivo"]
        try:
            contenido = lectura.leer_subida(archivo, lectura.LIMITE_PDF)
            nombre = lectura.nombre_saneado(archivo.name)
            if contenido.startswith(b"%PDF") or nombre.lower().endswith(".pdf"):
                cuenta, movimientos, resumen = conciliacion.movimientos_de_pdf(lectura.lineas_de_pdf(contenido))
                datos = {"cuenta": cuenta.pk, "movimientos": movimientos, "resumen": resumen, "adaptador": Importacion.ESTADO_PDF}
                tipo = CargaTemporal.BANCO_PDF
            else:
                cuenta = formulario.cleaned_data.get("cuenta")
                if cuenta is None:
                    raise conciliacion.ErrorConciliacion("Elige la cuenta a la que pertenece el archivo.")
                filas = lectura.filas_de_hoja(nombre, contenido)
                encabezado, propuesta = conciliacion.proponer_columnas(filas, cuenta)
                datos = {"cuenta": cuenta.pk, "filas": filas, "encabezado": encabezado, "propuesta": propuesta, "adaptador": Importacion.ARCHIVO}
                tipo = CargaTemporal.BANCO_ARCHIVO
        except (lectura.ErrorLectura, conciliacion.ErrorConciliacion) as error:
            formulario.add_error("archivo", str(error))
        else:
            carga = CargaTemporal.objects.create(token=secrets.token_urlsafe(32), tipo=tipo, usuario=request.user, nombre_archivo=nombre, sha256=lectura.huella_archivo(contenido), datos=datos)
            destino = "conciliacion:previa" if tipo == CargaTemporal.BANCO_PDF else "conciliacion:columnas"
            return redirect(destino, token=carga.token)
    return render(request, "banco/importar.html", {"formulario": formulario})


@requiere_permiso(CONCILIA)
def columnas(request, token):
    carga = carga_de(request, token, [CargaTemporal.BANCO_ARCHIVO])
    datos = carga.datos
    formulario = FormularioColumnas(request.POST if request.method == "POST" else None, filas=datos["filas"], encabezado=datos["encabezado"], propuesta=datos.get("propuesta"))
    if request.method == "POST" and formulario.is_valid():
        cuenta = get_object_or_404(CuentaBancaria, pk=datos["cuenta"])
        try:
            movimientos = conciliacion.movimientos_de_filas(datos["filas"], datos["encabezado"], formulario.columnas(), cuenta)
        except conciliacion.ErrorConciliacion as error:
            formulario.add_error(None, str(error))
        else:
            datos.update({"columnas": formulario.columnas(), "movimientos": movimientos})
            CargaTemporal.objects.filter(pk=carga.pk).update(datos=datos)
            return redirect("conciliacion:previa", token=token)
    muestra = datos["filas"][datos["encabezado"]: datos["encabezado"] + 6]
    return render(request, "banco/columnas.html", {"formulario": formulario, "muestra": muestra, "carga": carga})


@requiere_permiso(CONCILIA)
def previa(request, token):
    carga = carga_de(request, token, [CargaTemporal.BANCO_PDF, CargaTemporal.BANCO_ARCHIVO])
    datos = carga.datos
    if "movimientos" not in datos:
        return redirect("conciliacion:columnas", token=token)
    cuenta = get_object_or_404(CuentaBancaria, pk=datos["cuenta"])
    if request.method == "POST":
        try:
            with transaction.atomic():
                if not CargaTemporal.objects.filter(pk=carga.pk).delete()[0]:
                    raise conciliacion.ErrorConciliacion("Esta importación ya se confirmó.")
                importacion = conciliacion.importar(cuenta, datos["movimientos"], datos["adaptador"], carga.nombre_archivo, carga.sha256, request.user, datos.get("resumen"), request)
                if datos["adaptador"] == Importacion.ARCHIVO:
                    conciliacion.recordar_columnas(cuenta, datos["filas"], datos["encabezado"], datos["columnas"])
        except conciliacion.ErrorConciliacion as error:
            messages.error(request, str(error))
            return redirect("conciliacion:importar")
        messages.success(request, f"Importación lista: {importacion.aplicados} aplicados, {importacion.sugeridos + importacion.sin_pista} por identificar, {importacion.duplicados} ya estaban.")
        return redirect("conciliacion:importacion", pk=importacion.pk)
    resumen = conciliacion.vista_previa(cuenta, datos["movimientos"], datos["adaptador"])
    try:
        clasificacion, rechazo = conciliacion.continuidad(cuenta, datos["adaptador"], datos.get("resumen")), ""
    except conciliacion.ErrorConciliacion as error:
        clasificacion, rechazo = "", str(error)
    estado = dict(datos.get("resumen") or {})
    for clave in ("periodo_inicio", "periodo_fin"):
        estado[clave] = date.fromisoformat(estado[clave]) if estado.get(clave) else None
    return render(request, "banco/previa.html", {"carga": carga, "cuenta": cuenta, "resumen": resumen, "movimientos": [{**m, "fecha": date.fromisoformat(m["fecha"])} for m in datos["movimientos"][:100]], "estado": estado or None, "clasificacion": dict(Importacion.CONTINUIDADES).get(clasificacion, ""), "rechazo": rechazo})


@requiere_permiso(CONCILIA)
def importaciones(request):
    consulta = Importacion.objects.select_related("cuenta__banco", "creada_por", "revisada_por", "liberada_por").annotate(aplicados_vigentes=Count("lista", filter=Q(lista__estado=MovimientoBancario.APLICADO)))
    return render(request, "banco/importaciones.html", {"importaciones": consulta[:100]})


@requiere_permiso(CONCILIA, REVISA)
def importacion(request, pk):
    objeto = get_object_or_404(Importacion.objects.select_related("cuenta__banco", "creada_por", "revisada_por"), pk=pk)
    aplicados = objeto.lista.filter(estado=MovimientoBancario.APLICADO).aggregate(n=Count("id"), t=Sum("importe"))
    contexto = {
        "importacion": objeto,
        "movimientos": objeto.lista.select_related("pago__titular", "pago__recibo"),
        "aplicados": aplicados["n"],
        "monto": aplicados["t"] or 0,
        "puede_revisar": objeto.requiere_revision and objeto.revisada_por_id is None and request.user.tiene_permiso(REVISA) and objeto.creada_por_id != request.user.pk and not conciliacion.libero_algo(objeto, request.user),
        "retenidos": list(conciliacion.retenidos(objeto).order_by("fecha", "id")),
        "puede_liberar": request.user.tiene_permiso(CONCILIA),
    }
    return render(request, "banco/importacion.html", contexto)


@requiere_permiso(REVISA)
@require_POST
def revisada(request, pk):
    objeto = get_object_or_404(Importacion, pk=pk)
    try:
        conciliacion.marcar_revisada(objeto, request.user, request)
    except conciliacion.RevisionPropia:
        raise PermissionDenied
    except conciliacion.ErrorConciliacion as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Importación marcada como revisada.")
    return redirect("conciliacion:importacion", pk=pk)


@requiere_permiso(CONCILIA)
@require_POST
def liberar(request, pk):
    objeto = get_object_or_404(Importacion.objects.select_related("cuenta"), pk=pk)
    elegidos = None
    if request.POST.get("alcance") == "elegidos":
        elegidos = [valor for valor in request.POST.getlist("movimiento") if valor.isdigit() and len(valor) < 12]
        if not elegidos:
            messages.error(request, "Marca los movimientos que quieres liberar.")
            return redirect("conciliacion:importacion", pk=pk)
    try:
        aplicados, depositos = conciliacion.liberar(objeto, request.user, request, movimientos=elegidos)
    except conciliacion.ErrorConciliacion as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Movimientos liberados: {aplicados} pago{'s' if aplicados != 1 else ''} aplicado{'s' if aplicados != 1 else ''} y {depositos} depósito{'s' if depositos != 1 else ''} conciliado{'s' if depositos != 1 else ''}.")
    return redirect("conciliacion:importacion", pk=pk)


@requiere_permiso(*VEN_COLA)
def cola(request):
    pendientes = MovimientoBancario.objects.filter(estado=MovimientoBancario.POR_IDENTIFICAR).select_related("cuenta__banco", "propuesta").order_by("fecha", "id")
    return render(request, "banco/cola.html", {"movimientos": pendientes[:300]})


@requiere_permiso(*VEN_COLA)
def movimiento(request, pk):
    objeto = get_object_or_404(MovimientoBancario.objects.select_related("cuenta__banco", "propuesta", "propuesta_por", "pago__titular", "pago__recibo", "traslado__origen", "resuelto_por"), pk=pk)
    concilia = request.user.tiene_permiso(CONCILIA)
    sugeridos = [t for t in (Titular.objects.filter(matricula=m).first() for m in ([objeto.sugerencia] if objeto.sugerencia else []) + list(objeto.alternativas or [])) if t]
    contexto = {
        "movimiento": objeto,
        "concilia": concilia,
        "sugeridos": sugeridos,
        "formulario": FormularioMatricula(initial={"matricula": (objeto.propuesta.matricula if objeto.propuesta else objeto.sugerencia)}),
        "motivo": FormularioMotivo(),
        "depositos": list(conciliacion.candidatos_deposito(objeto.cuenta, objeto.importe, objeto.fecha)) if objeto.clase == MovimientoBancario.EFECTIVO and objeto.estado == MovimientoBancario.POR_IDENTIFICAR else [],
    }
    return render(request, "banco/movimiento.html", contexto)


def _resolver(request, pk, accion):
    objeto = get_object_or_404(MovimientoBancario, pk=pk)
    try:
        accion(objeto)
    except conciliacion.ErrorConciliacion as error:
        messages.error(request, str(error))
    return redirect("conciliacion:movimiento", pk=pk)


@requiere_permiso("sugerir_conciliacion", "conciliar_banco")
@require_POST
def proponer(request, pk):
    formulario = FormularioMatricula(request.POST)
    if not formulario.is_valid():
        messages.error(request, "; ".join(formulario.errors.get("matricula", ["Matrícula no válida."])))
        return redirect("conciliacion:movimiento", pk=pk)
    respuesta = _resolver(request, pk, lambda m: conciliacion.proponer(m, formulario.cleaned_data["matricula"], request.user, request))
    messages.info(request, "Propuesta registrada; Supervisión la confirmará.")
    return respuesta


@requiere_permiso(CONCILIA)
@require_POST
def confirmar(request, pk):
    formulario = FormularioMatricula(request.POST)
    if not formulario.is_valid():
        messages.error(request, "; ".join(formulario.errors.get("matricula", ["Matrícula no válida."])))
        return redirect("conciliacion:movimiento", pk=pk)
    return _resolver(request, pk, lambda m: conciliacion.confirmar(m, formulario.cleaned_data["matricula"], request.user, request))


@requiere_permiso(CONCILIA)
@require_POST
def no_cobro(request, pk):
    formulario = FormularioMotivo(request.POST)
    if not formulario.is_valid():
        messages.error(request, "Escribe el motivo.")
        return redirect("conciliacion:movimiento", pk=pk)
    return _resolver(request, pk, lambda m: conciliacion.no_es_cobro(m, formulario.cleaned_data["motivo"], request.user, request))


@requiere_permiso(CONCILIA)
@require_POST
def emparejar(request, pk):
    traslado = get_object_or_404(Traslado, pk=request.POST.get("traslado") or 0, tipo=Traslado.DEPOSITO)
    return _resolver(request, pk, lambda m: conciliacion.conciliar_deposito(m, traslado, request.user, request))
