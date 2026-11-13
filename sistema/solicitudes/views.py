from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.servicios import diferencias, registrar
from cobros import libro
from cobros.models import Cargo, ConceptoCobro, Pago
from cuentas.decoradores import requiere_permiso
from nucleo.dinero import formatear
from titulares.models import Familia

from . import motor
from .formularios import FormularioCodigoTelefono, FormularioPolitica, FormularioRechazo
from .models import PoliticaAccion, Solicitud

VEN_BANDEJA = ("solicitar_alta_baja", "alta_baja_directa", "aprobar_solicitudes")


def describir(solicitud):
    datos = solicitud.datos or {}
    filas = []
    if solicitud.accion == "beca":
        concepto = ConceptoCobro.objects.filter(pk=datos.get("concepto")).first()
        enteros, resto = divmod(int(datos.get("puntos_base") or 0), 100)
        filas += [("Concepto", str(concepto) if concepto else "—"), ("Porcentaje", f"{enteros}.{resto:02d} %"), ("Vigencia", f"{datos.get('desde')} a {datos.get('hasta') or 'sin fin'}")]
    elif solicitud.accion in ("prorroga", "cancelar_cargo", "condonar_recargo"):
        cargo = libro.con_saldo(Cargo.objects.filter(pk=datos.get("cargo"))).first()
        if cargo is not None:
            filas += [("Cargo", str(cargo)), ("Saldo actual", formatear(cargo.saldo)), ("Vence", cargo.vencimiento.strftime("%d/%m/%Y"))]
        if datos.get("fecha_limite"):
            filas.append(("Nueva fecha límite", datos["fecha_limite"]))
        if datos.get("importe"):
            filas.append(("Importe", formatear(datos["importe"])))
    elif solicitud.accion == "revertir_pago":
        pago = Pago.objects.filter(pk=datos.get("pago")).select_related("recibo").first()
        if pago is not None:
            filas += [("Recibo", str(pago.recibo)), ("Importe", formatear(pago.importe)), ("Medio", pago.get_medio_display())]
    elif solicitud.accion == "pago_sobre_tope":
        filas.append(("Importe recibido", formatear(int(datos.get("importe") or 0))))
    elif solicitud.accion == "cambio_familia":
        modo = {"ligar": "Ligar a", "crear": "Crear y ligar a", "desligar": "Desligar de"}.get(datos.get("modo"), "")
        familia = Familia.objects.filter(pk=datos.get("familia")).first()
        destino = datos.get("nombre") or (str(familia) if familia else str(solicitud.titular.familia or ""))
        filas.append((modo, destino))
    if datos.get("motivo"):
        filas.append(("Motivo", datos["motivo"]))
    return filas


def puede_ver(usuario, solicitud):
    if solicitud.solicitante_id == usuario.pk:
        return True
    politica = PoliticaAccion.objects.filter(accion=solicitud.accion).first()
    return politica is not None and usuario.tiene_permiso(politica.permiso_aprobar)


def pendientes_para(usuario):
    politicas = {p.accion: p for p in PoliticaAccion.objects.all()}
    acciones = [a for a, p in politicas.items() if usuario.tiene_permiso(p.permiso_aprobar)]
    consulta = Solicitud.objects.filter(estado=Solicitud.PENDIENTE, accion__in=acciones).exclude(solicitante=usuario)
    filas = list(consulta.select_related("titular", "solicitante").order_by("creada"))
    return [(s, s.resaltada(politicas[s.accion])) for s in filas]


@requiere_permiso(*VEN_BANDEJA)
def bandeja(request):
    motor.caducar_vencidas()
    propias = Solicitud.objects.filter(solicitante=request.user).select_related("titular", "resuelta_por")[:50]
    return render(request, "solicitudes/bandeja.html", {"pendientes": pendientes_para(request.user), "propias": propias})


@requiere_permiso(*VEN_BANDEJA)
def detalle(request, pk):
    solicitud = get_object_or_404(Solicitud.objects.select_related("titular", "solicitante", "resuelta_por"), pk=pk)
    if not puede_ver(request.user, solicitud):
        registrar("acceso_denegado", request=request, objeto=solicitud)
        raise PermissionDenied
    politica = solicitud.politica()
    contexto = {
        "solicitud": solicitud,
        "puede_resolver": solicitud.estado == Solicitud.PENDIENTE and solicitud.solicitante_id != request.user.pk and request.user.tiene_permiso(politica.permiso_aprobar),
        "puede_codigo": solicitud.estado == Solicitud.PENDIENTE and solicitud.solicitante_id == request.user.pk and politica.permite_codigo,
        "formulario_rechazo": FormularioRechazo(),
        "resaltada": solicitud.resaltada(politica),
        "descripcion": describir(solicitud),
    }
    return render(request, "solicitudes/detalle.html", contexto)


@requiere_permiso("aprobar_solicitudes")
@require_POST
def aprobar(request, pk):
    solicitud = get_object_or_404(Solicitud, pk=pk)
    try:
        motor.aprobar(solicitud, request.user, request=request)
        messages.success(request, "Solicitud aprobada.")
    except motor.ErrorSolicitud as error:
        messages.error(request, str(error))
    return redirect("solicitudes:detalle", pk=pk)


@requiere_permiso("aprobar_solicitudes")
@require_POST
def rechazar(request, pk):
    solicitud = get_object_or_404(Solicitud, pk=pk)
    formulario = FormularioRechazo(request.POST)
    nota = formulario.cleaned_data.get("nota", "") if formulario.is_valid() else ""
    try:
        motor.rechazar(solicitud, request.user, nota, request=request)
        messages.success(request, "Solicitud rechazada.")
    except motor.ErrorSolicitud as error:
        messages.error(request, str(error))
    return redirect("solicitudes:detalle", pk=pk)


@requiere_permiso("solicitar_alta_baja")
def codigo(request, pk):
    solicitud = get_object_or_404(Solicitud.objects.select_related("titular"), pk=pk)
    if solicitud.solicitante_id != request.user.pk:
        registrar("acceso_denegado", request=request, objeto=solicitud, datos={"accion": "codigo"})
        raise PermissionDenied
    if solicitud.estado != Solicitud.PENDIENTE:
        messages.info(request, "La solicitud ya no está pendiente.")
        return redirect("solicitudes:detalle", pk=pk)
    formulario = FormularioCodigoTelefono(request.POST if request.method == "POST" else None, autorizadores=motor.autorizadores_posibles(solicitud))
    if request.method == "POST" and formulario.is_valid():
        try:
            motor.autorizar_con_codigo(solicitud, request.user, formulario.usuario_autorizador(), formulario.cleaned_data["codigo"], request=request)
            messages.success(request, "Autorizado con código.")
            return redirect("solicitudes:detalle", pk=pk)
        except motor.ErrorSolicitud as error:
            messages.error(request, str(error))
    return render(request, "solicitudes/codigo.html", {"solicitud": solicitud, "formulario": formulario})


@requiere_permiso("administrar_politicas")
def politicas(request):
    return render(request, "solicitudes/politicas.html", {"politicas": PoliticaAccion.objects.all()})


@requiere_permiso("administrar_politicas", reingreso=True)
def politica_editar(request, pk):
    politica = get_object_or_404(PoliticaAccion, pk=pk)
    antes = FormularioPolitica(instance=politica).initial
    formulario = FormularioPolitica(request.POST if request.method == "POST" else None, instance=politica)
    if request.method == "POST" and formulario.is_valid():
        guardada = formulario.save()
        registrar("politica_cambiada", usuario=request.user, objeto=guardada, datos={"accion": guardada.accion, "cambios": diferencias(antes, FormularioPolitica(instance=guardada).initial)}, request=request)
        messages.success(request, "Política guardada.")
        return redirect("solicitudes:politicas")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"Política: {politica}", "boton": "Guardar"})
