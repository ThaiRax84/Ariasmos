from dataclasses import dataclass
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from auditoria.servicios import registrar
from configuracion.models import parametro
from cuentas.models import CodigoUsado
from cuentas.servicios import consumir_codigo, usar_delegacion
from titulares.models import MotivoBaja, Titular

from .models import IntentoCodigo, PoliticaAccion, Solicitud


class ErrorSolicitud(Exception):
    pass


@dataclass
class Resultado:
    via: str
    solicitud: Solicitud = None


class Alta:
    def validar(self, titular, datos):
        if titular.estado != Titular.PENDIENTE:
            raise ErrorSolicitud("Solo se aprueba el alta de un registro pendiente.")

    def aplicar(self, titular, datos):
        titular.estado = Titular.ACTIVO
        titular.save(update_fields=["estado", "actualizado"])

    def rechazar(self, titular, datos):
        titular.estado = Titular.RECHAZADO
        titular.save(update_fields=["estado", "actualizado"])


class Baja:
    def validar(self, titular, datos):
        if titular.estado != Titular.ACTIVO:
            raise ErrorSolicitud("Solo se da de baja un registro activo.")
        if not MotivoBaja.objects.filter(pk=datos.get("motivo"), activo=True).exists():
            raise ErrorSolicitud("El motivo de baja no es válido.")

    def aplicar(self, titular, datos):
        titular.estado = Titular.BAJA
        titular.motivo_baja_id = datos["motivo"]
        titular.fecha_baja = timezone.now()
        titular.save(update_fields=["estado", "motivo_baja", "fecha_baja", "actualizado"])

    def rechazar(self, titular, datos):
        pass


class Reactivacion:
    def validar(self, titular, datos):
        if titular.estado != Titular.BAJA:
            raise ErrorSolicitud("Solo se reactiva un registro dado de baja.")

    def aplicar(self, titular, datos):
        titular.estado = Titular.ACTIVO
        titular.motivo_baja = None
        titular.fecha_baja = None
        titular.save(update_fields=["estado", "motivo_baja", "fecha_baja", "actualizado"])

    def rechazar(self, titular, datos):
        pass


MANEJADORES = {"alta": Alta(), "baja": Baja(), "reactivacion": Reactivacion()}


def politica_de(accion):
    try:
        return PoliticaAccion.objects.get(accion=accion)
    except PoliticaAccion.DoesNotExist:
        raise ErrorSolicitud("La acción no tiene política configurada.")


def caducar_vencidas():
    for solicitud in Solicitud.objects.filter(estado=Solicitud.PENDIENTE, caduca_en__lte=timezone.now()):
        with transaction.atomic():
            actualizadas = Solicitud.objects.filter(pk=solicitud.pk, estado=Solicitud.PENDIENTE).update(
                estado=Solicitud.CADUCADA, resuelta_en=timezone.now()
            )
            if actualizadas:
                registrar("solicitud_caducada", objeto=solicitud, datos={"accion": solicitud.accion, "titular": solicitud.titular_id})


def puede_ejecutar_o_solicitar(usuario, accion):
    politica = PoliticaAccion.objects.filter(accion=accion).first()
    if politica is None:
        return False
    return usuario.tiene_permiso(politica.permiso_directo) or usuario.tiene_permiso(politica.permiso_solicitar)


def ejecutar(accion, usuario, titular, datos=None, request=None):
    datos = datos or {}
    politica = politica_de(accion)
    manejador = MANEJADORES[accion]
    if not (usuario.tiene_permiso(politica.permiso_directo) or usuario.tiene_permiso(politica.permiso_solicitar)):
        registrar("acceso_denegado", usuario=usuario, objeto=titular, datos={"accion": accion}, request=request)
        raise PermissionDenied
    caducar_vencidas()
    with transaction.atomic():
        titular = Titular.objects.get(pk=titular.pk)
        manejador.validar(titular, datos)
        if Solicitud.objects.filter(titular=titular, accion=accion, estado=Solicitud.PENDIENTE).exists():
            raise ErrorSolicitud("Ya hay una solicitud pendiente para esta acción.")
        if usuario.tiene_permiso_de_rol(politica.permiso_directo):
            manejador.aplicar(titular, datos)
            registrar(f"{accion}_aplicada", usuario=usuario, objeto=titular, datos={"via": "directa", **datos}, request=request)
            return Resultado("directa")
        if politica.permite_delegacion:
            delegacion = usar_delegacion(usuario, politica.permiso_directo, request=request, contexto={"accion": accion, "titular": titular.pk})
            if delegacion is not None:
                manejador.aplicar(titular, datos)
                registrar(
                    f"{accion}_aplicada",
                    usuario=usuario,
                    objeto=titular,
                    datos={"via": "delegacion", "delegacion": delegacion.pk, "otorgante": delegacion.otorgante_id, **datos},
                    request=request,
                )
                return Resultado("delegacion")
        if not usuario.tiene_permiso(politica.permiso_solicitar):
            raise PermissionDenied
        solicitud = Solicitud.objects.create(
            accion=accion,
            titular=titular,
            datos=datos,
            solicitante=usuario,
            caduca_en=timezone.now() + timedelta(hours=politica.horas_caducidad),
        )
        registrar("solicitud_creada", usuario=usuario, objeto=solicitud, datos={"accion": accion, "titular": titular.pk, **datos}, request=request)
        return Resultado("solicitud", solicitud)


def _verificar_resolvible(solicitud, usuario, request, evento):
    if solicitud.estado != Solicitud.PENDIENTE:
        raise ErrorSolicitud("La solicitud ya no está pendiente.")
    if solicitud.caduca_en <= timezone.now():
        caducar_vencidas()
        raise ErrorSolicitud("La solicitud caducó.")
    if usuario.pk == solicitud.solicitante_id:
        registrar(evento, usuario=usuario, objeto=solicitud, datos={"motivo": "autoaprobacion"}, request=request)
        raise ErrorSolicitud("Nadie puede resolver su propia solicitud.")


def _autorizar_resolucion(solicitud, usuario, politica, request):
    if usuario.tiene_permiso_de_rol(politica.permiso_aprobar):
        return Solicitud.BANDEJA, None
    if politica.permite_delegacion:
        delegacion = usar_delegacion(usuario, politica.permiso_aprobar, request=request, contexto={"solicitud": solicitud.pk})
        if delegacion is not None:
            return Solicitud.DELEGACION, delegacion
    registrar("acceso_denegado", usuario=usuario, objeto=solicitud, datos={"accion": "resolver"}, request=request)
    raise PermissionDenied


def _cerrar(solicitud, estado, resolutor, via, nota=""):
    solicitud.estado = estado
    solicitud.resuelta_por = resolutor
    solicitud.resuelta_en = timezone.now()
    solicitud.via = via
    solicitud.nota_resolucion = nota[:300]
    solicitud.save()


def aprobar(solicitud, usuario, request=None):
    politica = politica_de(solicitud.accion)
    _verificar_resolvible(solicitud, usuario, request, "aprobacion_rechazada")
    if not (usuario.tiene_permiso(politica.permiso_aprobar)):
        registrar("acceso_denegado", usuario=usuario, objeto=solicitud, datos={"accion": "aprobar"}, request=request)
        raise PermissionDenied
    with transaction.atomic():
        solicitud = Solicitud.objects.select_related("titular").get(pk=solicitud.pk)
        if solicitud.estado != Solicitud.PENDIENTE:
            raise ErrorSolicitud("La solicitud ya no está pendiente.")
        via, delegacion = _autorizar_resolucion(solicitud, usuario, politica, request)
        manejador = MANEJADORES[solicitud.accion]
        manejador.validar(solicitud.titular, solicitud.datos)
        manejador.aplicar(solicitud.titular, solicitud.datos)
        _cerrar(solicitud, Solicitud.APROBADA, usuario, via)
        registrar(
            "solicitud_aprobada",
            usuario=usuario,
            objeto=solicitud,
            datos={"accion": solicitud.accion, "titular": solicitud.titular_id, "via": via, "delegacion": delegacion.pk if delegacion else None},
            request=request,
        )
    return solicitud


def rechazar(solicitud, usuario, nota="", request=None):
    politica = politica_de(solicitud.accion)
    _verificar_resolvible(solicitud, usuario, request, "rechazo_no_permitido")
    if not usuario.tiene_permiso(politica.permiso_aprobar):
        registrar("acceso_denegado", usuario=usuario, objeto=solicitud, datos={"accion": "rechazar"}, request=request)
        raise PermissionDenied
    with transaction.atomic():
        solicitud = Solicitud.objects.select_related("titular").get(pk=solicitud.pk)
        if solicitud.estado != Solicitud.PENDIENTE:
            raise ErrorSolicitud("La solicitud ya no está pendiente.")
        via, delegacion = _autorizar_resolucion(solicitud, usuario, politica, request)
        MANEJADORES[solicitud.accion].rechazar(solicitud.titular, solicitud.datos)
        _cerrar(solicitud, Solicitud.RECHAZADA, usuario, via, nota)
        registrar(
            "solicitud_rechazada",
            usuario=usuario,
            objeto=solicitud,
            datos={"accion": solicitud.accion, "titular": solicitud.titular_id, "via": via, "nota": nota},
            request=request,
        )
    return solicitud


def autorizadores_posibles(solicitud):
    from cuentas.models import Usuario

    politica = politica_de(solicitud.accion)
    candidatos = Usuario.objects.filter(activo=True, totp_confirmado=True).exclude(pk=solicitud.solicitante_id).select_related("rol")
    return [u for u in candidatos if u.tiene_permiso_de_rol(politica.permiso_aprobar)]


def autorizar_con_codigo(solicitud, capturista, autorizador, codigo, request=None):
    politica = politica_de(solicitud.accion)
    if capturista.pk != solicitud.solicitante_id:
        registrar("acceso_denegado", usuario=capturista, objeto=solicitud, datos={"accion": "codigo"}, request=request)
        raise PermissionDenied
    if not politica.permite_codigo:
        raise ErrorSolicitud("Esta acción no admite autorización por código.")
    if autorizador.pk == solicitud.solicitante_id:
        registrar("aprobacion_rechazada", usuario=capturista, objeto=solicitud, datos={"motivo": "autoaprobacion"}, request=request)
        raise ErrorSolicitud("Nadie puede autorizar su propia solicitud.")
    if solicitud.estado != Solicitud.PENDIENTE:
        raise ErrorSolicitud("La solicitud ya no está pendiente.")
    if solicitud.caduca_en <= timezone.now():
        caducar_vencidas()
        raise ErrorSolicitud("La solicitud caducó.")
    if not (autorizador.activo and autorizador.totp_confirmado and autorizador.tiene_permiso_de_rol(politica.permiso_aprobar)):
        registrar("codigo_rechazado", usuario=capturista, objeto=solicitud, datos={"autorizador": autorizador.pk, "motivo": "sin_facultad"}, request=request)
        raise ErrorSolicitud("Esa persona no puede autorizar esta solicitud.")
    bloqueo = motivo_de_bloqueo(capturista, autorizador, solicitud)
    if bloqueo is not None:
        _registrar_bloqueo(capturista, autorizador, solicitud, bloqueo, request)
        raise ErrorSolicitud("Demasiados códigos erróneos; usa la bandeja o espera una hora.")
    with transaction.atomic():
        solicitud = Solicitud.objects.select_related("titular").get(pk=solicitud.pk)
        if solicitud.estado != Solicitud.PENDIENTE:
            raise ErrorSolicitud("La solicitud ya no está pendiente.")
        usado, motivo = consumir_codigo(autorizador, codigo, CodigoUsado.AUTORIZACION, usado_por=capturista, solicitud=solicitud)
        if usado is not None:
            manejador = MANEJADORES[solicitud.accion]
            manejador.validar(solicitud.titular, solicitud.datos)
            manejador.aplicar(solicitud.titular, solicitud.datos)
            _cerrar(solicitud, Solicitud.APROBADA, autorizador, Solicitud.CODIGO)
            registrar(
                "solicitud_aprobada",
                usuario=capturista,
                objeto=solicitud,
                datos={
                    "accion": solicitud.accion,
                    "titular": solicitud.titular_id,
                    "via": Solicitud.CODIGO,
                    "autorizador": autorizador.pk,
                    "autorizador_usuario": autorizador.usuario,
                    "codigo_usado": usado.pk,
                },
                request=request,
            )
            return solicitud
    IntentoCodigo.objects.create(tipo=IntentoCodigo.FALLIDO, capturista=capturista, autorizador=autorizador, solicitud=solicitud, motivo=motivo)
    registrar("codigo_rechazado", usuario=capturista, objeto=solicitud, datos={"autorizador": autorizador.pk, "motivo": motivo}, request=request)
    bloqueo = motivo_de_bloqueo(capturista, autorizador, solicitud)
    if bloqueo is not None:
        _registrar_bloqueo(capturista, autorizador, solicitud, bloqueo, request)
    if motivo == "reutilizado":
        raise ErrorSolicitud("Ese código ya se usó. Pide uno nuevo.")
    raise ErrorSolicitud("El código no es válido.")


def motivo_de_bloqueo(capturista, autorizador, solicitud):
    fallidos = IntentoCodigo.objects.filter(tipo=IntentoCodigo.FALLIDO)
    recientes = fallidos.filter(momento__gte=timezone.now() - timedelta(hours=1))
    limite = parametro("intentos_codigo_por_hora")
    if recientes.filter(capturista=capturista).count() >= limite:
        return "capturista"
    if recientes.filter(autorizador=autorizador).count() >= limite:
        return "autorizador"
    if fallidos.filter(solicitud=solicitud).count() >= parametro("intentos_codigo_por_solicitud"):
        return "solicitud"
    return None


def _registrar_bloqueo(capturista, autorizador, solicitud, motivo, request):
    IntentoCodigo.objects.create(tipo=IntentoCodigo.BLOQUEO, capturista=capturista, autorizador=autorizador, solicitud=solicitud, motivo=motivo)
    registrar(
        "codigo_bloqueado",
        usuario=capturista,
        objeto=solicitud,
        datos={"capturista": capturista.pk, "autorizador": autorizador.pk, "motivo": motivo},
        request=request,
    )
