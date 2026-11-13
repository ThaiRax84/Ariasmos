from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.servicios import diferencias, registrar
from banco.ficha import datos_de_pago
from cobros.estado import estado_cuenta
from configuracion.models import parametro, vocabulario
from cuentas.decoradores import requiere_permiso
from nucleo.matricula import normalizar
from solicitudes import motor
from solicitudes.models import Solicitud

from . import contactos
from .historial import historial
from .formularios import FormularioAlta, FormularioBaja, FormularioCambioFamilia, FormularioEditarContacto, FormularioNota, FormularioTitular
from .models import Contacto, Familia, Titular
from .servicios import crear_titular, foto_titular, guardar_contacto

CAPTURA = ("solicitar_alta_baja", "alta_baja_directa")


def _avisar_resultado(request, resultado):
    if resultado.via == "directa":
        messages.success(request, "Aplicado directamente.")
    elif resultado.via == "delegacion":
        messages.success(request, "Aplicado con tu delegación temporal.")
    else:
        messages.info(request, "Solicitud enviada. Queda pendiente de aprobación; también puede autorizarse con código por teléfono.")


@requiere_permiso("ver_titulares")
def lista(request):
    consulta = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    titulares = Titular.objects.select_related("agrupacion")
    if consulta:
        digitos = normalizar(consulta)
        filtro = Q(nombre__icontains=consulta) | Q(apellidos__icontains=consulta)
        if digitos:
            filtro |= Q(matricula__startswith=digitos)
        titulares = titulares.filter(filtro)
    if estado in dict(Titular.ESTADOS):
        titulares = titulares.filter(estado=estado)
    return render(request, "titulares/lista.html", {"titulares": titulares[:200], "q": consulta, "estado": estado, "estados": Titular.ESTADOS})


@requiere_permiso(*CAPTURA)
def nuevo(request):
    voc = vocabulario()
    if not motor.puede_ejecutar_o_solicitar(request.user, "alta"):
        raise PermissionDenied
    formulario = FormularioAlta(request.POST if request.method == "POST" else None, voc=voc)
    if request.method == "POST" and formulario.is_valid():
        limite = parametro("maximo_altas_pendientes_por_capturista")
        if Titular.objects.filter(creado_por=request.user, estado=Titular.PENDIENTE).count() >= limite:
            registrar("alta_rechazada_por_tope", usuario=request.user, datos={"limite": limite}, request=request)
            formulario.add_error(None, f"Tienes {limite} altas pendientes de aprobación. Espera a que se resuelvan antes de capturar otra.")
            return render(request, "titulares/nuevo.html", {"formulario": formulario}, status=429)
        with transaction.atomic():
            titular = crear_titular(
                request.user,
                formulario.datos_titular(),
                contacto=formulario.datos_contacto(),
                conceptos=list(formulario.cleaned_data.get("conceptos") or []),
                request=request,
                familia_nueva=(formulario.cleaned_data.get("familia_nueva") or "").strip() or None,
            )
            resultado = motor.ejecutar("alta", request.user, titular, request=request)
        _avisar_resultado(request, resultado)
        return redirect("titulares:detalle", pk=titular.pk)
    return render(request, "titulares/nuevo.html", {"formulario": formulario})


@requiere_permiso("ver_titulares")
def detalle(request, pk):
    titular = get_object_or_404(Titular.objects.select_related("agrupacion", "motivo_baja", "creado_por"), pk=pk)
    lista_contactos = [(c, contactos.detalle(c)) for c in titular.contactos.select_related("relacion")]
    solicitudes = titular.solicitudes.select_related("solicitante", "resuelta_por")[:20]
    abierta = {s.accion for s in titular.solicitudes.filter(estado=Solicitud.PENDIENTE)}
    contexto = {
        "titular": titular,
        "contactos": lista_contactos,
        "solicitudes": solicitudes,
        "puede_capturar": any(request.user.tiene_permiso(p) for p in CAPTURA),
        "alta_abierta": "alta" in abierta,
        "baja_abierta": "baja" in abierta,
        "reactivacion_abierta": "reactivacion" in abierta,
        "planes": titular.planes.select_related("concepto"),
        "estado": estado_cuenta([titular]),
        "contacto_familia": contactos.principal(titular) if titular.familia_id else None,
    }
    return render(request, "titulares/detalle.html", contexto)


@requiere_permiso("ver_titulares")
def familias(request):
    lista = Familia.objects.annotate(total=Count("miembros")).order_by("nombre")
    return render(request, "titulares/familias.html", {"familias": lista})


@requiere_permiso("ver_titulares")
def familia(request, pk):
    objeto = get_object_or_404(Familia, pk=pk)
    miembros = list(objeto.miembros.order_by("apellidos", "nombre"))
    lista_contactos = [(c, contactos.detalle(c)) for c in objeto.contactos.select_related("relacion")]
    return render(request, "titulares/familia.html", {"familia": objeto, "miembros": miembros, "contactos": lista_contactos, "estado": estado_cuenta(miembros), "puede_capturar": any(request.user.tiene_permiso(p) for p in CAPTURA)})


@requiere_permiso(*CAPTURA)
def familia_contacto(request, pk, contacto_pk=None):
    objeto = get_object_or_404(Familia, pk=pk)
    contacto = get_object_or_404(Contacto, pk=contacto_pk, familia=objeto) if contacto_pk else None
    inicial = {"contacto_principal": contacto.principal} if contacto else {}
    formulario = FormularioEditarContacto(request.POST if request.method == "POST" else None, inicial_contacto=contacto, initial=inicial)
    if request.method == "POST" and formulario.is_valid():
        marcado = bool(formulario.cleaned_data.get("contacto_principal"))
        principal = (contacto.principal or marcado) if contacto else (marcado or None)
        guardar_contacto(request.user, None, formulario.datos_contacto(), contacto=contacto, principal=principal, request=request, familia=objeto)
        messages.success(request, "Contacto guardado.")
        return redirect("titulares:familia", pk=pk)
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"Contacto de {objeto}", "boton": "Guardar"})


@requiere_permiso(*CAPTURA)
def cambiar_familia(request, pk):
    titular = get_object_or_404(Titular.objects.select_related("familia"), pk=pk)
    if not motor.puede_ejecutar_o_solicitar(request.user, "cambio_familia"):
        raise PermissionDenied
    formulario = FormularioCambioFamilia(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        try:
            resultado = motor.ejecutar("cambio_familia", request.user, titular, formulario.datos(), request=request)
        except motor.ErrorSolicitud as error:
            messages.error(request, str(error))
        else:
            _avisar_resultado(request, resultado)
            if resultado.solicitud is not None:
                return redirect("solicitudes:detalle", pk=resultado.solicitud.pk)
            return redirect("titulares:detalle", pk=pk)
    actual = f" (hoy: {titular.familia})" if titular.familia_id else ""
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"Familia de {titular}{actual}", "boton": "Enviar"})


@requiere_permiso("ver_titulares")
def ver_historial(request, pk):
    titular = get_object_or_404(Titular, pk=pk)
    return render(request, "titulares/historial.html", {"titular": titular, "filas": historial(titular, vocabulario())})


@requiere_permiso("ver_titulares")
def ficha_pago(request, pk):
    titular = get_object_or_404(Titular, pk=pk)
    contacto = contactos.principal(titular)
    registrar("ficha_pago_consultada", usuario=request.user, objeto=titular, request=request)
    contexto = {"titular": titular, "contacto": contacto, "contacto_detalle": contactos.detalle(contacto) if contacto else [], "pago": datos_de_pago()}
    return render(request, "titulares/ficha_pago.html", contexto)


@requiere_permiso(*CAPTURA)
def editar(request, pk):
    titular = get_object_or_404(Titular, pk=pk)
    if titular.estado == Titular.RECHAZADO:
        raise PermissionDenied
    original = foto_titular(titular)
    nombre_actual, apellidos_actual = titular.nombre, titular.apellidos
    formulario = FormularioTitular(request.POST if request.method == "POST" else None, instance=titular, voc=vocabulario())
    if titular.estado != Titular.PENDIENTE:
        formulario.fields["nombre"].help_text = "Cambiar el nombre de un registro aprobado requiere autorización."
    if request.method == "POST" and formulario.is_valid():
        propuesto = {"nombre": formulario.cleaned_data["nombre"].strip(), "apellidos": formulario.cleaned_data["apellidos"].strip()}
        libre = titular.estado == Titular.PENDIENTE
        cambia_nombre = (propuesto["nombre"], propuesto["apellidos"]) != (nombre_actual, apellidos_actual)
        with transaction.atomic():
            guardado = formulario.save(commit=False)
            if not libre:
                guardado.nombre, guardado.apellidos = nombre_actual, apellidos_actual
            guardado.save()
            cambios = diferencias(original, foto_titular(guardado))
            if cambios:
                registrar("titular_editado", usuario=request.user, objeto=guardado, datos={"cambios": cambios}, request=request)
        if cambios:
            messages.success(request, "Datos guardados.")
        if cambia_nombre and not libre:
            _corregir_nombre(request, guardado, propuesto, nombre_actual, apellidos_actual)
        elif not cambios:
            messages.info(request, "No hubo cambios.")
        return redirect("titulares:detalle", pk=pk)
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"Editar {titular}", "boton": "Guardar"})


def _corregir_nombre(request, titular, propuesto, nombre_actual, apellidos_actual):
    datos = dict(propuesto, nombre_anterior=nombre_actual, apellidos_anterior=apellidos_actual)
    try:
        resultado = motor.ejecutar("correccion_nombre", request.user, titular, datos, request=request)
    except motor.ErrorSolicitud as error:
        messages.error(request, f"El nombre no se cambió: {error}")
        return
    except PermissionDenied:
        messages.error(request, "El nombre no se cambió: no tienes permiso para corregirlo.")
        return
    if resultado.solicitud is None:
        messages.success(request, "Nombre corregido.")
    else:
        messages.warning(request, "El cambio de nombre quedó como SOLICITUD pendiente de aprobación; el nombre no cambia hasta que se apruebe. Los demás datos ya se guardaron.")


@requiere_permiso(*CAPTURA)
def contacto_nuevo(request, pk):
    titular = get_object_or_404(Titular, pk=pk)
    formulario = FormularioEditarContacto(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        guardar_contacto(request.user, titular, formulario.datos_contacto(), principal=formulario.cleaned_data.get("contacto_principal") or None, request=request)
        messages.success(request, "Contacto agregado.")
        return redirect("titulares:detalle", pk=pk)
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"Nuevo contacto de {titular}", "boton": "Guardar"})


@requiere_permiso(*CAPTURA)
def contacto_editar(request, pk, contacto_pk):
    titular = get_object_or_404(Titular, pk=pk)
    contacto = get_object_or_404(Contacto, pk=contacto_pk, titular=titular)
    formulario = FormularioEditarContacto(request.POST if request.method == "POST" else None, inicial_contacto=contacto, initial={"contacto_principal": contacto.principal})
    if request.method == "POST" and formulario.is_valid():
        marcado = bool(formulario.cleaned_data.get("contacto_principal"))
        if contacto.principal and not marcado:
            messages.error(request, "Marca otro contacto como principal en lugar de quitarle la marca a este.")
            return redirect("titulares:contacto_editar", pk=pk, contacto_pk=contacto_pk)
        principal = contacto.principal or marcado
        guardar_contacto(request.user, titular, formulario.datos_contacto(), contacto=contacto, principal=principal, request=request)
        messages.success(request, "Contacto actualizado.")
        return redirect("titulares:detalle", pk=pk)
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"Editar contacto de {titular}", "boton": "Guardar"})


def _accion_titular(request, pk, accion, formulario_clase, plantilla_titulo):
    titular = get_object_or_404(Titular, pk=pk)
    if not motor.puede_ejecutar_o_solicitar(request.user, accion):
        raise PermissionDenied
    formulario = formulario_clase(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        datos = {}
        if "motivo" in formulario.cleaned_data:
            datos["motivo"] = formulario.cleaned_data["motivo"].pk
        if formulario.cleaned_data.get("nota"):
            datos["nota"] = formulario.cleaned_data["nota"]
        try:
            resultado = motor.ejecutar(accion, request.user, titular, datos, request=request)
        except motor.ErrorSolicitud as error:
            messages.error(request, str(error))
            return redirect("titulares:detalle", pk=pk)
        _avisar_resultado(request, resultado)
        if resultado.solicitud is not None:
            return redirect("solicitudes:detalle", pk=resultado.solicitud.pk)
        return redirect("titulares:detalle", pk=pk)
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"{plantilla_titulo}: {titular}", "boton": "Enviar"})


@requiere_permiso(*CAPTURA)
def baja(request, pk):
    return _accion_titular(request, pk, "baja", FormularioBaja, "Baja")


@requiere_permiso(*CAPTURA)
def reactivar(request, pk):
    return _accion_titular(request, pk, "reactivacion", FormularioNota, "Reactivación")


@requiere_permiso(*CAPTURA)
def solicitar_alta(request, pk):
    return _accion_titular(request, pk, "alta", FormularioNota, "Aprobación de alta")
