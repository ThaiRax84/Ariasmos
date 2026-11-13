from dataclasses import dataclass
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from auditoria.servicios import diferencias, registrar
from cobros import acciones, generacion, libro
from configuracion.models import hoy_negocio, parametro
from cuentas.models import CodigoUsado
from cuentas.servicios import consumir_codigo, usar_delegacion
from titulares.models import Familia, MotivoBaja, Titular
from titulares.servicios import foto_titular

from .models import IntentoCodigo, PoliticaAccion, Solicitud


class ErrorSolicitud(Exception):
    pass


@dataclass
class Resultado:
    via: str
    solicitud: Solicitud = None
    objeto: object = None


@dataclass
class Contexto:
    ejecutor: object
    autorizador: object
    solicitante: object
    solicitud: Solicitud = None
    request: object = None
    resultado: object = None


class Manejador:
    def llave(self, datos):
        return {}

    def exige_solicitud(self, usuario, titular, datos):
        return False

    def puede_resolver(self, usuario, datos):
        return True

    def rechazar(self, titular, datos, contexto=None):
        pass


class Alta(Manejador):
    def validar(self, titular, datos):
        if titular.estado != Titular.PENDIENTE:
            raise ErrorSolicitud("Solo se aprueba el alta de un registro pendiente.")

    def aplicar(self, titular, datos, contexto):
        titular.estado = Titular.ACTIVO
        titular.activo_desde = hoy_negocio()
        titular.save(update_fields=["estado", "activo_desde", "actualizado"])
        cargos = generacion.cargos_de_alta(titular, request=contexto.request)
        return {"cargos_iniciales": [str(c) for c in cargos]}

    def rechazar(self, titular, datos, contexto=None):
        titular.estado = Titular.RECHAZADO
        titular.save(update_fields=["estado", "actualizado"])


class Baja(Manejador):
    def validar(self, titular, datos):
        if titular.estado != Titular.ACTIVO:
            raise ErrorSolicitud("Solo se da de baja un registro activo.")
        if not MotivoBaja.objects.filter(pk=datos.get("motivo"), activo=True).exists():
            raise ErrorSolicitud("El motivo de baja no es válido.")

    def aplicar(self, titular, datos, contexto):
        titular.estado = Titular.BAJA
        titular.motivo_baja_id = datos["motivo"]
        titular.fecha_baja = timezone.now()
        titular.save(update_fields=["estado", "motivo_baja", "fecha_baja", "actualizado"])


class Reactivacion(Manejador):
    def validar(self, titular, datos):
        if titular.estado != Titular.BAJA:
            raise ErrorSolicitud("Solo se reactiva un registro dado de baja.")

    def aplicar(self, titular, datos, contexto):
        titular.estado = Titular.ACTIVO
        titular.motivo_baja = None
        titular.fecha_baja = None
        titular.activo_desde = hoy_negocio()
        titular.save(update_fields=["estado", "motivo_baja", "fecha_baja", "activo_desde", "actualizado"])


class CorreccionNombre(Manejador):
    def validar(self, titular, datos):
        if titular.estado not in (Titular.ACTIVO, Titular.BAJA):
            raise ErrorSolicitud("La corrección de nombre aplica a registros activos o dados de baja.")
        nombre, apellidos = (datos.get("nombre") or "").strip(), (datos.get("apellidos") or "").strip()
        if not nombre or not apellidos:
            raise ErrorSolicitud("Indica el nombre y los apellidos propuestos.")
        if nombre == titular.nombre and apellidos == titular.apellidos:
            raise ErrorSolicitud("El nombre propuesto es igual al actual.")

    def aplicar(self, titular, datos, contexto):
        titular.nombre = datos["nombre"].strip()
        titular.apellidos = datos["apellidos"].strip()
        titular.save(update_fields=["nombre", "apellidos", "actualizado"])


class CambioFamilia(Manejador):
    MODOS = ("ligar", "crear", "desligar")

    def validar(self, titular, datos):
        modo = datos.get("modo")
        if modo not in self.MODOS:
            raise ErrorSolicitud("Indica si se liga, se crea o se desliga la familia.")
        if titular.estado == Titular.RECHAZADO:
            raise ErrorSolicitud("Un registro rechazado no se liga a una familia.")
        if modo == "ligar":
            familia = Familia.objects.filter(pk=datos.get("familia"), activa=True).first()
            if familia is None:
                raise ErrorSolicitud("La familia elegida no existe o no está activa.")
            if familia.pk == titular.familia_id:
                raise ErrorSolicitud("Ya pertenece a esa familia.")
            return familia
        if modo == "crear":
            nombre = (datos.get("nombre") or "").strip()
            if not 0 < len(nombre) <= 100:
                raise ErrorSolicitud("Escribe el nombre de la familia nueva.")
            return None
        if titular.familia_id is None:
            raise ErrorSolicitud("No pertenece a ninguna familia.")
        return None

    def aplicar(self, titular, datos, contexto):
        familia = self.validar(titular, datos)
        anterior = str(titular.familia) if titular.familia_id else None
        if datos["modo"] == "crear":
            familia = Familia.objects.create(nombre=datos["nombre"].strip())
            registrar("familia_creada", usuario=contexto.ejecutor, objeto=familia, titular=titular.pk, datos={"nombre": familia.nombre}, request=contexto.request)
        titular.familia = familia if datos["modo"] != "desligar" else None
        titular.save(update_fields=["familia", "actualizado"])
        return {"cambios": {"familia": [anterior, str(titular.familia) if titular.familia_id else None]}}


MANEJADORES = {
    "alta": Alta(),
    "baja": Baja(),
    "reactivacion": Reactivacion(),
    "correccion_nombre": CorreccionNombre(),
    "cambio_familia": CambioFamilia(),
    "beca": acciones.OtorgarBeca(),
    "prorroga": acciones.OtorgarProrroga(),
    "cancelar_cargo": acciones.Cancelar(),
    "condonar_recargo": acciones.Condonar(),
    "revertir_pago": acciones.Revertir(),
    "pago_sobre_tope": acciones.PagoSobreTope(),
}

ERRORES_DE_ACCION = (acciones.ErrorAccion, libro.ErrorLibro)


def _validar(manejador, titular, datos):
    try:
        manejador.validar(titular, datos)
    except ERRORES_DE_ACCION as error:
        raise ErrorSolicitud(str(error))


def _aplicar(manejador, titular, datos, contexto):
    antes = foto_titular(titular)
    try:
        detalle = dict(manejador.aplicar(titular, datos, contexto) or {})
    except ERRORES_DE_ACCION as error:
        raise ErrorSolicitud(str(error))
    titular.refresh_from_db()
    cambios = diferencias(antes, foto_titular(titular))
    cambios.update(detalle.pop("cambios", {}))
    return cambios, detalle


def _rechazar(manejador, titular, datos, contexto=None):
    antes = foto_titular(titular)
    manejador.rechazar(titular, datos, contexto)
    return diferencias(antes, foto_titular(titular))


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
        _validar(manejador, titular, datos)
        if Solicitud.objects.filter(titular=titular, accion=accion, estado=Solicitud.PENDIENTE, **manejador.llave(datos)).exists():
            raise ErrorSolicitud("Ya hay una solicitud pendiente para esta acción.")
        contexto = Contexto(ejecutor=usuario, autorizador=usuario, solicitante=usuario, request=request)
        forzada = manejador.exige_solicitud(usuario, titular, datos)
        if forzada:
            registrar("solicitud_obligatoria", usuario=usuario, objeto=titular, datos={"accion": accion, "motivo": "pago_cobrado_por_quien_revierte"}, request=request)
        if not forzada and usuario.tiene_permiso_de_rol(politica.permiso_directo):
            cambios, detalle = _aplicar(manejador, titular, datos, contexto)
            registrar(f"{accion}_aplicada", usuario=usuario, objeto=titular, datos={"via": "directa", **datos, **detalle, "cambios": cambios}, request=request)
            return Resultado("directa", objeto=contexto.resultado)
        if politica.permite_delegacion and not forzada:
            delegacion = usar_delegacion(usuario, politica.permiso_directo, request=request, contexto={"accion": accion, "titular": titular.pk})
            if delegacion is not None:
                contexto.autorizador = delegacion.otorgante
                cambios, detalle = _aplicar(manejador, titular, datos, contexto)
                registrar(
                    f"{accion}_aplicada",
                    usuario=usuario,
                    objeto=titular,
                    datos={"via": "delegacion", "delegacion": delegacion.pk, "otorgante": str(delegacion.otorgante), **datos, **detalle, "cambios": cambios},
                    request=request,
                )
                return Resultado("delegacion", objeto=contexto.resultado)
        if not forzada and not usuario.tiene_permiso(politica.permiso_solicitar):
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
    if not MANEJADORES[solicitud.accion].puede_resolver(usuario, solicitud.datos):
        registrar(evento, usuario=usuario, objeto=solicitud, datos={"motivo": "cobro_propio"}, request=request)
        raise ErrorSolicitud("Nadie resuelve la reversión de un pago que él mismo cobró.")


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
        _validar(manejador, solicitud.titular, solicitud.datos)
        contexto = Contexto(ejecutor=usuario, autorizador=usuario, solicitante=solicitud.solicitante, solicitud=solicitud, request=request)
        cambios, detalle = _aplicar(manejador, solicitud.titular, solicitud.datos, contexto)
        _cerrar(solicitud, Solicitud.APROBADA, usuario, via)
        registrar(
            "solicitud_aprobada",
            usuario=usuario,
            objeto=solicitud,
            datos={"accion": solicitud.accion, "titular": solicitud.titular_id, "via": via, "delegacion": delegacion.pk if delegacion else None, "solicitante": str(solicitud.solicitante), **detalle, "cambios": cambios},
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
        cambios = _rechazar(MANEJADORES[solicitud.accion], solicitud.titular, solicitud.datos, None)
        _cerrar(solicitud, Solicitud.RECHAZADA, usuario, via, nota)
        registrar(
            "solicitud_rechazada",
            usuario=usuario,
            objeto=solicitud,
            datos={"accion": solicitud.accion, "titular": solicitud.titular_id, "via": via, "nota": nota, "solicitante": str(solicitud.solicitante), "cambios": cambios},
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
    if not MANEJADORES[solicitud.accion].puede_resolver(autorizador, solicitud.datos):
        registrar("aprobacion_rechazada", usuario=capturista, objeto=solicitud, datos={"motivo": "cobro_propio", "autorizador": autorizador.pk}, request=request)
        raise ErrorSolicitud("Nadie autoriza la reversión de un pago que él mismo cobró.")
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
            _validar(manejador, solicitud.titular, solicitud.datos)
            contexto = Contexto(ejecutor=capturista, autorizador=autorizador, solicitante=solicitud.solicitante, solicitud=solicitud, request=request)
            cambios, detalle = _aplicar(manejador, solicitud.titular, solicitud.datos, contexto)
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
                    "autorizador_nombre": str(autorizador),
                    **detalle,
                    "cambios": cambios,
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
