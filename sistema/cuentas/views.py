from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import password_validation
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from auditoria.servicios import diferencias, registrar
from nucleo import totp

from . import servicios
from .decoradores import requiere_permiso, requiere_sesion
from .formularios import (
    FormularioActivacion,
    FormularioAprobarDispositivo,
    FormularioCambioPropio,
    FormularioCodigo,
    FormularioConfirmar,
    FormularioDelegacion,
    FormularioEntrar,
    FormularioRevision,
    FormularioRol,
    FormularioUsuarioEditar,
    FormularioUsuarioNuevo,
)
from .models import CodigoActivacion, CodigoUsado, Delegacion, Dispositivo, PermisoRol, Rol, Usuario
from .permisos import PERMISOS

MENSAJE_FALLO = "Usuario o contraseña incorrectos, o la cuenta está bloqueada temporalmente."
SEGUNDOS_PASO_CODIGO = 300


def _destino_seguro(request, valor, defecto="inicio"):
    if valor and url_has_allowed_host_and_scheme(valor, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return valor
    return defecto


def _completar_inicio(request, usuario):
    siguiente = request.session.get("siguiente_tras_entrar")
    servicios.reiniciar_intentos(usuario)
    login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
    request.session["ultima_actividad"] = timezone.now().timestamp()
    servicios.ligar_sesion(request)
    servicios.marcar_reingreso(request)
    registrar("inicio_sesion", usuario=usuario, objeto=usuario, datos={"dispositivo": request.dispositivo.pk if request.dispositivo else None}, request=request)
    if servicios.tiene_avisos(usuario):
        messages.warning(request, "Hay avisos sobre tu código de autorización. Revísalos.")
        return redirect("autorizaciones")
    return redirect(_destino_seguro(request, siguiente))


def entrar(request):
    if request.user.is_authenticated:
        return redirect("inicio")
    formulario = FormularioEntrar(request.POST if request.method == "POST" else None)
    if request.method == "GET" and request.GET.get("siguiente"):
        request.session["siguiente_tras_entrar"] = request.GET["siguiente"]
    if request.method == "POST":
        if servicios.limite_intentos_superado(request):
            registrar("inicio_sesion_limitado", request=request)
            messages.error(request, "Demasiados intentos desde este equipo. Espera unos minutos.")
            return render(request, "cuentas/entrar.html", {"formulario": formulario}, status=429)
        servicios.contar_intento(request)
        if formulario.is_valid():
            usuario = Usuario.objects.filter(usuario__iexact=formulario.cleaned_data["usuario"]).first()
            if usuario is None:
                make_password(formulario.cleaned_data["contrasena"])
                registrar("inicio_sesion_fallido", datos={"motivo": "usuario_desconocido"}, request=request)
            elif usuario.esta_bloqueado():
                registrar("inicio_sesion_fallido", objeto=usuario, datos={"motivo": "bloqueado"}, request=request)
            elif not usuario.check_password(formulario.cleaned_data["contrasena"]):
                servicios.registrar_fallo(usuario, request)
            elif not usuario.activo:
                registrar("inicio_sesion_fallido", objeto=usuario, datos={"motivo": "inactivo"}, request=request)
            elif usuario.totp_confirmado:
                request.session["pendiente_codigo"] = usuario.pk
                request.session["pendiente_codigo_en"] = timezone.now().timestamp()
                return redirect("entrar_codigo")
            else:
                return _completar_inicio(request, usuario)
            messages.error(request, MENSAJE_FALLO)
    return render(request, "cuentas/entrar.html", {"formulario": formulario})


def entrar_codigo(request):
    pendiente = request.session.get("pendiente_codigo")
    marca = request.session.get("pendiente_codigo_en", 0)
    if not pendiente or timezone.now().timestamp() - marca > SEGUNDOS_PASO_CODIGO:
        request.session.pop("pendiente_codigo", None)
        return redirect("entrar")
    usuario = get_object_or_404(Usuario, pk=pendiente, activo=True)
    formulario = FormularioCodigo(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if servicios.limite_intentos_superado(request):
            messages.error(request, "Demasiados intentos desde este equipo. Espera unos minutos.")
            return render(request, "cuentas/entrar_codigo.html", {"formulario": formulario}, status=429)
        servicios.contar_intento(request)
        if formulario.is_valid():
            if usuario.esta_bloqueado():
                request.session.pop("pendiente_codigo", None)
                messages.error(request, MENSAJE_FALLO)
                return redirect("entrar")
            usado, motivo = servicios.consumir_codigo(usuario, formulario.cleaned_data["codigo"], CodigoUsado.INICIO_SESION)
            if usado is not None:
                request.session.pop("pendiente_codigo", None)
                return _completar_inicio(request, usuario)
            servicios.registrar_fallo(usuario, request, motivo=f"codigo_{motivo}")
            messages.error(request, "El código no es válido o ya se usó.")
    return render(request, "cuentas/entrar_codigo.html", {"formulario": formulario})


MENSAJE_ACTIVACION = "Usuario o código de activación no válidos, o la cuenta está bloqueada temporalmente."


def activar(request):
    if request.user.is_authenticated:
        return redirect("inicio")
    formulario = FormularioActivacion(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if servicios.limite_intentos_superado(request):
            messages.error(request, "Demasiados intentos desde este equipo. Espera unos minutos.")
            return render(request, "cuentas/activar.html", {"formulario": formulario}, status=429)
        servicios.contar_intento(request)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            usuario = Usuario.objects.filter(usuario__iexact=datos["usuario"]).first()
            activacion = None
            if usuario is None:
                make_password(datos["contrasena1"])
                registrar("codigo_activacion_fallido", datos={"motivo": "usuario_desconocido"}, request=request)
            elif usuario.esta_bloqueado() or not usuario.activo:
                registrar("codigo_activacion_fallido", objeto=usuario, datos={"motivo": "bloqueado" if usuario.activo else "inactivo"}, request=request)
            else:
                encontrado = servicios.buscar_activacion(usuario, datos["codigo"])
                if encontrado is not None and encontrado.vigente():
                    activacion = encontrado
                elif encontrado is not None and encontrado.usado_en is None and not encontrado.invalidado:
                    registrar("codigo_activacion_caducado", objeto=usuario, datos={"codigo": encontrado.pk}, request=request)
                    servicios.registrar_fallo(usuario, request, motivo="activacion_caducada")
                else:
                    registrar("codigo_activacion_fallido", objeto=usuario, datos={"motivo": "codigo"}, request=request)
                    servicios.registrar_fallo(usuario, request, motivo="activacion")
            if activacion is not None:
                try:
                    password_validation.validate_password(datos["contrasena1"], usuario)
                except ValidationError as error:
                    formulario.add_error("contrasena1", error)
                    return render(request, "cuentas/activar.html", {"formulario": formulario})
                with transaction.atomic():
                    quemado = CodigoActivacion.objects.filter(pk=activacion.pk, usado_en__isnull=True, invalidado=False).update(usado_en=timezone.now())
                    if quemado == 1:
                        usuario.set_password(datos["contrasena1"])
                        usuario.save(update_fields=["password"])
                        servicios.invalidar_activaciones(usuario)
                        registrar("cuenta_activada", usuario=usuario, objeto=usuario, datos={"codigo": activacion.pk, "generado_por": activacion.creado_por_id}, request=request)
                if quemado == 1:
                    if usuario.totp_confirmado:
                        request.session["pendiente_codigo"] = usuario.pk
                        request.session["pendiente_codigo_en"] = timezone.now().timestamp()
                        messages.info(request, "Contraseña definida. Escribe el código de tu autenticador.")
                        return redirect("entrar_codigo")
                    return _completar_inicio(request, usuario)
            messages.error(request, MENSAJE_ACTIVACION)
    return render(request, "cuentas/activar.html", {"formulario": formulario})


@require_POST
def salir(request):
    if request.user.is_authenticated:
        registrar("cierre_sesion", usuario=request.user, request=request)
    logout(request)
    return redirect("entrar")


@requiere_sesion
def confirmar(request):
    formulario = FormularioConfirmar(request.POST if request.method == "POST" else None)
    siguiente = request.GET.get("siguiente") or request.POST.get("siguiente", "")
    if request.method == "POST" and formulario.is_valid():
        usuario = request.user
        if usuario.esta_bloqueado():
            logout(request)
            return redirect("entrar")
        if usuario.check_password(formulario.cleaned_data["contrasena"]):
            servicios.reiniciar_intentos(usuario)
            servicios.marcar_reingreso(request)
            registrar("reingreso_confirmado", usuario=usuario, request=request)
            return redirect(_destino_seguro(request, siguiente))
        servicios.registrar_fallo(usuario, request, motivo="reingreso")
        messages.error(request, "La contraseña no es correcta.")
    return render(request, "cuentas/confirmar.html", {"formulario": formulario, "siguiente": siguiente})


@requiere_sesion
def alta_totp(request):
    usuario = request.user
    if usuario.totp_confirmado:
        return render(request, "cuentas/totp_listo.html")
    secreto = request.session.get("totp_propuesto")
    if not secreto:
        secreto = totp.generar_secreto()
        request.session["totp_propuesto"] = secreto
    formulario = FormularioCodigo(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        usado, _ = servicios.consumir_codigo(usuario, formulario.cleaned_data["codigo"], CodigoUsado.ALTA, secreto=secreto)
        if usado is not None:
            usuario.totp_secreto = secreto
            usuario.totp_confirmado = True
            usuario.save(update_fields=["totp_secreto", "totp_confirmado"])
            request.session.pop("totp_propuesto", None)
            registrar("totp_alta", usuario=usuario, objeto=usuario, request=request)
            messages.success(request, "Autenticador activado.")
            return redirect("inicio")
        messages.error(request, "El código no coincide. Revisa la hora del teléfono e inténtalo otra vez.")
    emisor = request.negocio.nombre if request.negocio else "Sistema de cobro"
    contexto = {"formulario": formulario, "secreto": secreto, "uri": totp.uri(secreto, usuario.usuario, emisor)}
    return render(request, "cuentas/totp.html", contexto)


@requiere_sesion
def cambiar_contrasena(request):
    formulario = FormularioCambioPropio(request.POST if request.method == "POST" else None, usuario=request.user)
    if request.method == "POST" and formulario.is_valid():
        request.user.set_password(formulario.cleaned_data["contrasena1"])
        request.user.save(update_fields=["password"])
        login(request, request.user, backend="django.contrib.auth.backends.ModelBackend")
        request.session["ultima_actividad"] = timezone.now().timestamp()
        servicios.ligar_sesion(request)
        registrar("contrasena_cambiada", usuario=request.user, objeto=request.user, request=request)
        messages.success(request, "Contraseña actualizada.")
        return redirect("inicio")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Cambiar mi contraseña", "boton": "Guardar"})


@requiere_sesion
def autorizaciones(request):
    codigos = CodigoUsado.objects.filter(autorizador=request.user, proposito=CodigoUsado.AUTORIZACION).select_related("usado_por", "solicitud__titular")[:100]
    bloqueos = servicios.avisos_pendientes(request.user).select_related("capturista", "solicitud__titular")
    return render(request, "cuentas/autorizaciones.html", {"codigos": codigos, "bloqueos": bloqueos})


@requiere_sesion
@require_POST
def aviso_enterado(request, pk):
    aviso = get_object_or_404(servicios.avisos_pendientes(request.user), pk=pk)
    aviso.visto = True
    aviso.save(update_fields=["visto"])
    registrar("aviso_codigo_enterado", usuario=request.user, objeto=aviso, datos={"capturista": aviso.capturista_id}, request=request)
    return redirect("autorizaciones")


@requiere_sesion
@require_POST
def revisar_autorizacion(request, pk):
    codigo = get_object_or_404(CodigoUsado, pk=pk, autorizador=request.user, revision=CodigoUsado.POR_REVISAR)
    formulario = FormularioRevision(request.POST)
    if formulario.is_valid():
        confirmar_codigo = formulario.cleaned_data["decision"] == "confirmar"
        codigo.revision = CodigoUsado.CONFIRMADO if confirmar_codigo else CodigoUsado.REPORTADO
        codigo.revisado_en = timezone.now()
        codigo.save(update_fields=["revision", "revisado_en"])
        registrar("codigo_confirmado" if confirmar_codigo else "codigo_reportado", usuario=request.user, objeto=codigo, datos={"solicitud": codigo.solicitud_id, "usado_por": codigo.usado_por_id}, request=request)
        if confirmar_codigo:
            messages.success(request, "Autorización confirmada.")
        else:
            messages.warning(request, "Autorización reportada. Quedó registrada en la auditoría.")
    return redirect("autorizaciones")


def dispositivo_pendiente(request):
    dispositivo = request.dispositivo
    if dispositivo is not None and dispositivo.aprobado:
        return redirect("inicio")
    return render(request, "cuentas/dispositivo_pendiente.html", {"dispositivo": dispositivo}, status=403)


@requiere_permiso("administrar_usuarios")
def usuarios(request):
    lista = Usuario.objects.select_related("rol").all()
    return render(request, "cuentas/usuarios.html", {"usuarios": lista, "ahora": timezone.now()})


@requiere_permiso("administrar_usuarios", reingreso=True)
def usuario_nuevo(request):
    formulario = FormularioUsuarioNuevo(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        exceso = servicios.permisos_que_exceden(request.user, datos["rol"].permisos())
        if exceso:
            servicios.rechazar_escalada(request.user, request, "crear_usuario_con_rol_superior", datos["rol"], exceso)
            messages.error(request, "No puedes crear un usuario con un rol que tiene permisos que tú no tienes.")
            return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Nuevo usuario", "boton": "Crear usuario", "volver": "usuarios"}, status=403)
        with transaction.atomic():
            nuevo = Usuario.objects.create_user(datos["usuario"], None, nombre=datos["nombre"], rol=datos["rol"])
            registrar("usuario_creado", usuario=request.user, objeto=nuevo, datos={"usuario": nuevo.usuario, "cambios": diferencias({}, {"nombre": nuevo.nombre, "rol": str(nuevo.rol), "activo": True})}, request=request)
            codigo, caduca = servicios.generar_activacion(nuevo, request.user, request)
        return render(request, "cuentas/codigo_activacion.html", {"objetivo": nuevo, "codigo": codigo, "caduca": caduca})
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Nuevo usuario", "boton": "Crear usuario", "volver": "usuarios"})


@requiere_permiso("administrar_usuarios", reingreso=True)
def usuario_editar(request, pk):
    objetivo = get_object_or_404(Usuario, pk=pk)
    exceso = servicios.permisos_que_exceden(request.user, objetivo.permisos_de_rol())
    if exceso:
        servicios.rechazar_escalada(request.user, request, "editar_usuario_superior", objetivo, exceso)
        raise PermissionDenied
    antes = {"nombre": objetivo.nombre, "rol": str(objetivo.rol) if objetivo.rol_id else None, "activo": objetivo.activo}
    formulario = FormularioUsuarioEditar(request.POST if request.method == "POST" else None, instance=objetivo)
    if request.method == "POST" and formulario.is_valid():
        rol_nuevo = formulario.cleaned_data.get("rol")
        exceso = servicios.permisos_que_exceden(request.user, rol_nuevo.permisos() if rol_nuevo else set())
        if exceso:
            servicios.rechazar_escalada(request.user, request, "asignar_rol_superior", objetivo, exceso)
            messages.error(request, "No puedes asignar un rol con permisos que tú no tienes.")
            return redirect("usuario_editar", pk=pk)
        with transaction.atomic():
            cambiado = formulario.save(commit=False)
            datos = formulario.cleaned_data
            if datos.get("desbloquear"):
                cambiado.intentos_fallidos = 0
                cambiado.bloqueado_hasta = None
            if datos.get("reiniciar_totp"):
                cambiado.totp_secreto = ""
                cambiado.totp_confirmado = False
            cambiado.save()
            if not servicios.quedan_administradores():
                transaction.set_rollback(True)
                messages.error(request, "El cambio dejaría el sistema sin nadie que administre usuarios y roles.")
                return redirect("usuario_editar", pk=pk)
            registrar(
                "usuario_cambiado",
                usuario=request.user,
                objeto=cambiado,
                datos={
                    "usuario": cambiado.usuario,
                    "cambios": diferencias(antes, {"nombre": cambiado.nombre, "rol": str(cambiado.rol) if cambiado.rol_id else None, "activo": cambiado.activo}),
                    "acceso_restablecido": bool(datos.get("restablecer_acceso")),
                    "desbloqueado": bool(datos.get("desbloquear")),
                    "totp_reiniciado": bool(datos.get("reiniciar_totp")),
                },
                request=request,
            )
            activacion = servicios.restablecer_acceso(cambiado, request.user, request) if datos.get("restablecer_acceso") else None
        if activacion is not None:
            return render(request, "cuentas/codigo_activacion.html", {"objetivo": cambiado, "codigo": activacion[0], "caduca": activacion[1]})
        messages.success(request, "Usuario actualizado.")
        return redirect("usuarios")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": f"Editar usuario {objetivo.usuario}", "boton": "Guardar", "volver": "usuarios"})


@requiere_permiso("administrar_roles")
def roles(request):
    lista = Rol.objects.prefetch_related("asignaciones").all()
    filas = [(rol, [PERMISOS[a.permiso] for a in rol.asignaciones.all() if a.permiso in PERMISOS]) for rol in lista]
    return render(request, "cuentas/roles.html", {"filas": filas})


def _guardar_rol(request, rol=None):
    if rol is not None:
        exceso = servicios.permisos_que_exceden(request.user, rol.permisos())
        if exceso:
            servicios.rechazar_escalada(request.user, request, "editar_rol_superior", rol, exceso)
            raise PermissionDenied
    formulario = FormularioRol(request.POST if request.method == "POST" else None, instance=rol)
    if request.method == "POST" and formulario.is_valid():
        antes_rol = {"nombre": rol.nombre, "nivel": rol.nivel, "minutos_inactividad": rol.minutos_inactividad, "requiere_totp": rol.requiere_totp, "permisos": sorted(rol.permisos())} if rol else {}
        nuevos = set(formulario.cleaned_data["permisos"])
        exceso = servicios.permisos_que_exceden(request.user, nuevos)
        if exceso:
            servicios.rechazar_escalada(request.user, request, "otorgar_permisos_a_rol", rol, exceso)
            messages.error(request, "No puedes dar a un rol permisos que tú no tienes.")
            return redirect("rol_editar", pk=rol.pk) if rol else redirect("rol_nuevo")
        with transaction.atomic():
            guardado = formulario.save()
            if rol is not None and not servicios.quedan_administradores(rol_modificado=guardado, permisos_nuevos=nuevos):
                transaction.set_rollback(True)
                messages.error(request, "El cambio dejaría el sistema sin nadie que administre usuarios y roles.")
                return redirect("rol_editar", pk=rol.pk)
            PermisoRol.objects.filter(rol=guardado).exclude(permiso__in=nuevos).delete()
            for permiso in nuevos:
                PermisoRol.objects.get_or_create(rol=guardado, permiso=permiso)
            registrar(
                "rol_creado" if rol is None else "rol_cambiado",
                usuario=request.user,
                objeto=guardado,
                datos={
                    "nombre": guardado.nombre,
                    "cambios": diferencias(antes_rol, {"nombre": guardado.nombre, "nivel": guardado.nivel, "minutos_inactividad": guardado.minutos_inactividad, "requiere_totp": guardado.requiere_totp, "permisos": sorted(nuevos)}),
                },
                request=request,
            )
        messages.success(request, "Rol guardado.")
        return redirect("roles")
    titulo = "Nuevo rol" if rol is None else f"Editar rol {rol.nombre}"
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": titulo, "boton": "Guardar", "volver": "roles"})


@requiere_permiso("administrar_roles", reingreso=True)
def rol_nuevo(request):
    return _guardar_rol(request)


@requiere_permiso("administrar_roles", reingreso=True)
def rol_editar(request, pk):
    return _guardar_rol(request, get_object_or_404(Rol, pk=pk))


@requiere_permiso("aprobar_dispositivos")
def dispositivos(request):
    pendientes = Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE, creado__gte=timezone.now() - timedelta(days=7))
    otros = Dispositivo.objects.exclude(estado=Dispositivo.PENDIENTE).select_related("aprobado_por")
    return render(request, "cuentas/dispositivos.html", {"pendientes": pendientes[:50], "otros": otros, "formulario": FormularioAprobarDispositivo()})


@requiere_permiso("aprobar_dispositivos", reingreso=True)
@require_POST
def dispositivo_aprobar(request, pk):
    dispositivo = get_object_or_404(Dispositivo, pk=pk, estado=Dispositivo.PENDIENTE)
    formulario = FormularioAprobarDispositivo(request.POST)
    if formulario.is_valid():
        servicios.aprobar_dispositivo(dispositivo, request.user, formulario.cleaned_data["nombre"], request)
        messages.success(request, f"Equipo {dispositivo.codigo} aprobado.")
    else:
        messages.error(request, "Escribe un nombre para el equipo.")
    return redirect("dispositivos")


@requiere_permiso("aprobar_dispositivos")
@require_POST
def dispositivos_descartar(request):
    descartados = Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).delete()[0]
    registrar("dispositivos_descartados", usuario=request.user, datos={"cantidad": descartados}, request=request)
    messages.success(request, f"Se descartaron {descartados} equipos pendientes.")
    return redirect("dispositivos")


@requiere_permiso("aprobar_dispositivos", reingreso=True)
@require_POST
def dispositivo_revocar(request, pk):
    dispositivo = get_object_or_404(Dispositivo, pk=pk, estado=Dispositivo.APROBADO)
    if request.dispositivo and dispositivo.pk == request.dispositivo.pk:
        messages.error(request, "No puedes revocar el equipo que estás usando.")
        return redirect("dispositivos")
    servicios.revocar_dispositivo(dispositivo, request.user, request)
    messages.success(request, "Equipo revocado.")
    return redirect("dispositivos")


@requiere_permiso("otorgar_delegaciones")
def delegaciones(request):
    lista = Delegacion.objects.select_related("otorgante", "receptor").all()[:200]
    ahora = timezone.now()
    filas = [(d, d.vigente(ahora)) for d in lista]
    return render(request, "cuentas/delegaciones.html", {"filas": filas, "permisos_nombres": PERMISOS})


@requiere_permiso("otorgar_delegaciones", reingreso=True)
def delegacion_nueva(request):
    formulario = FormularioDelegacion(request.POST if request.method == "POST" else None, otorgante=request.user)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        if not request.user.tiene_permiso_de_rol(datos["permiso"]):
            messages.error(request, "Solo puedes delegar permisos que tienes por tu rol.")
            return redirect("delegaciones")
        delegacion = Delegacion.objects.create(
            otorgante=request.user,
            receptor=datos["receptor"],
            permiso=datos["permiso"],
            vence=timezone.now() + timedelta(days=datos["dias"]) if datos.get("dias") else None,
            usos_maximos=datos.get("usos"),
            motivo=datos.get("motivo", ""),
        )
        registrar(
            "delegacion_otorgada",
            usuario=request.user,
            objeto=delegacion,
            datos={"receptor": delegacion.receptor_id, "permiso": delegacion.permiso, "vence": delegacion.vence, "usos_maximos": delegacion.usos_maximos},
            request=request,
        )
        messages.success(request, "Delegación otorgada.")
        return redirect("delegaciones")
    return render(request, "comun/formulario.html", {"formulario": formulario, "titulo": "Nueva delegación temporal", "boton": "Otorgar", "volver": "delegaciones"})


@requiere_permiso("otorgar_delegaciones")
@require_POST
def delegacion_revocar(request, pk):
    delegacion = get_object_or_404(Delegacion, pk=pk, revocada=False)
    delegacion.revocada = True
    delegacion.revocada_por = request.user
    delegacion.save(update_fields=["revocada", "revocada_por"])
    registrar("delegacion_revocada", usuario=request.user, objeto=delegacion, request=request)
    messages.success(request, "Delegación revocada.")
    return redirect("delegaciones")
