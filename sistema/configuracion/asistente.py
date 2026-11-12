import hashlib
import hmac

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from auditoria.servicios import registrar
from cobros.models import ConceptoCobro, ReglaRecargo
from cuentas import servicios as cuentas_servicios
from cuentas.formularios import FormularioCodigo
from cuentas.models import CodigoUsado, Usuario
from nucleo import totp

from . import plantillas
from .formularios import FormularioAsistenteConceptos, FormularioAsistenteNegocio, FormularioAsistenteUsuario
from .models import Negocio

CLAVE_SESION = "asistente"


def _disponible(request):
    negocio = Negocio.actual()
    if negocio and negocio.configurado:
        raise Http404
    return negocio


def _estado(request):
    return request.session.get(CLAVE_SESION) or {}


def _guardar_estado(request, **cambios):
    estado = dict(_estado(request))
    estado.update(cambios)
    request.session[CLAVE_SESION] = estado


def _token_valido(token):
    esperado = getattr(settings, "TOKEN_ASISTENTE_HASH", "")
    if not esperado or not token:
        return False
    return hmac.compare_digest(hashlib.sha256(token.encode("utf-8")).hexdigest(), esperado)


def inicio(request):
    negocio = _disponible(request)
    opciones = plantillas.disponibles()
    instancia = negocio or Negocio(pk=1)
    formulario = FormularioAsistenteNegocio(request.POST if request.method == "POST" else None, instance=instancia, plantillas=opciones, initial={"plantilla": negocio.plantilla if negocio else ""})
    if request.method == "POST" and formulario.is_valid():
        if not _token_valido(formulario.cleaned_data["token"]):
            registrar("asistente_token_invalido", request=request)
            messages.error(request, "El token de instalación no es correcto.")
        else:
            with transaction.atomic():
                guardado = formulario.save(commit=False)
                guardado.pk = 1
                guardado.plantilla = formulario.cleaned_data["plantilla"]
                guardado.configurado = False
                guardado.save()
                plantillas.cargar(guardado.plantilla)
                registrar("asistente_negocio", objeto=guardado, datos={"nombre": guardado.nombre, "plantilla": guardado.plantilla}, request=request)
            _guardar_estado(request, autorizado=True)
            return redirect("asistente:conceptos")
    return render(request, "asistente/paso.html", {"formulario": formulario, "paso": 1, "titulo": "Datos del negocio"})


def _exigir_autorizado(request):
    negocio = _disponible(request)
    if negocio is None or not _estado(request).get("autorizado"):
        return None
    return negocio


def conceptos(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    datos_plantilla = plantillas.leer(negocio.plantilla)
    lista = ConceptoCobro.objects.all()
    formulario = FormularioAsistenteConceptos(request.POST if request.method == "POST" else None, conceptos=lista, con_recargo=plantillas.conceptos_con_recargo(datos_plantilla))
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        with transaction.atomic():
            for concepto in lista:
                importe = datos.get(f"importe_{concepto.pk}")
                if importe is not None:
                    concepto.importe_centavos = importe
                if datos.get(f"dia_{concepto.pk}"):
                    concepto.dia_vencimiento = datos[f"dia_{concepto.pk}"]
                valor = datos.get(f"recargo_valor_{concepto.pk}")
                if valor:
                    regla, _ = ReglaRecargo.objects.update_or_create(
                        nombre=f"Recargo de {concepto.nombre}",
                        defaults={"tipo": datos[f"recargo_tipo_{concepto.pk}"], "valor": valor, "dias_gracia": datos.get(f"recargo_gracia_{concepto.pk}") or 0},
                    )
                    concepto.regla_recargo = regla
                concepto.save()
            registrar("asistente_conceptos", datos={"conceptos": [c.pk for c in lista]}, request=request)
        return redirect("asistente:usuario")
    return render(request, "asistente/paso.html", {"formulario": formulario, "paso": 2, "titulo": "Conceptos de cobro e importes"})


def usuario(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    formulario = FormularioAsistenteUsuario(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        existente = Usuario.objects.filter(usuario__iexact=datos["usuario"]).first()
        if existente and existente.pk != _estado(request).get("usuario"):
            formulario.add_error("usuario", "Ese usuario ya existe.")
        else:
            rol = plantillas.rol_inicial(plantillas.leer(negocio.plantilla))
            with transaction.atomic():
                if existente:
                    existente.nombre = datos["nombre"]
                    existente.rol = rol
                    existente.set_password(datos["contrasena1"])
                    existente.save()
                    nuevo = existente
                else:
                    nuevo = Usuario.objects.create_user(datos["usuario"], datos["contrasena1"], nombre=datos["nombre"], rol=rol)
                registrar("usuario_creado", objeto=nuevo, datos={"usuario": nuevo.usuario, "rol": rol.pk, "origen": "asistente"}, request=request)
            _guardar_estado(request, usuario=nuevo.pk, secreto=totp.generar_secreto())
            return redirect("asistente:codigo")
    return render(request, "asistente/paso.html", {"formulario": formulario, "paso": 3, "titulo": "Primer usuario de Dirección"})


def codigo(request):
    negocio = _exigir_autorizado(request)
    estado = _estado(request)
    if negocio is None or not estado.get("usuario") or not estado.get("secreto"):
        return redirect("asistente:inicio")
    nuevo = Usuario.objects.get(pk=estado["usuario"])
    secreto = estado["secreto"]
    formulario = FormularioCodigo(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        with transaction.atomic():
            usado, _ = cuentas_servicios.consumir_codigo(nuevo, formulario.cleaned_data["codigo"], CodigoUsado.ALTA, secreto=secreto)
            if usado is not None:
                nuevo.totp_secreto = secreto
                nuevo.totp_confirmado = True
                nuevo.save(update_fields=["totp_secreto", "totp_confirmado"])
                dispositivo = request.dispositivo
                cuentas_servicios.aprobar_dispositivo(dispositivo, nuevo, "Servidor (asistente)", request)
                Negocio.objects.filter(pk=1).update(configurado=True)
                registrar("asistente_completado", usuario=nuevo, objeto=negocio, request=request)
        if usado is not None:
            request.session.pop(CLAVE_SESION, None)
            login(request, nuevo, backend="django.contrib.auth.backends.ModelBackend")
            request.session["ultima_actividad"] = timezone.now().timestamp()
            cuentas_servicios.ligar_sesion(request)
            cuentas_servicios.marcar_reingreso(request)
            registrar("inicio_sesion", usuario=nuevo, objeto=nuevo, request=request)
            messages.success(request, "Instalación lista.")
            return redirect("inicio")
        messages.error(request, "El código no coincide. Revisa la hora del teléfono.")
    contexto = {
        "formulario": formulario,
        "paso": 4,
        "titulo": "Autenticador del primer usuario",
        "secreto": secreto,
        "uri": totp.uri(secreto, nuevo.usuario, negocio.nombre),
    }
    return render(request, "asistente/codigo.html", contexto)
