from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Evento
from cuentas.models import CodigoUsado, Delegacion
from solicitudes import motor
from solicitudes.models import Solicitud
from titulares.models import CampoContacto, MotivoBaja, Titular

from .conftest import CONTRASENA, cliente, codigo_actual


def datos_alta(nombre="Ana", telefono="55 1234 5678"):
    campo = CampoContacto.objects.get(tipo=CampoContacto.TELEFONO)
    return {
        "nombre": nombre,
        "apellidos": "Prueba",
        "contacto_nombre": "Responsable",
        campo.clave: telefono,
        "constancia_consentimiento": "on",
    }


def alta_por_vista(c, nombre="Ana"):
    respuesta = c.post(reverse("titulares:nuevo"), datos_alta(nombre))
    assert respuesta.status_code == 302, respuesta.content.decode()[:2000]
    return Titular.objects.get(nombre=nombre)


def motivo():
    return MotivoBaja.objects.first()


def test_alta_y_baja_por_bandeja(personas):
    op, sup = cliente(personas["op"]), cliente(personas["sup"])
    titular = alta_por_vista(op)
    assert titular.estado == Titular.PENDIENTE
    assert len(titular.matricula) == 7
    solicitud = Solicitud.objects.get(titular=titular, accion="alta")
    assert solicitud.estado == Solicitud.PENDIENTE
    assert sup.get(reverse("inicio")).content.decode().count(titular.matricula_formateada) >= 1
    assert sup.post(reverse("solicitudes:aprobar", args=[solicitud.pk])).status_code == 302
    titular.refresh_from_db()
    solicitud.refresh_from_db()
    assert titular.estado == Titular.ACTIVO
    assert solicitud.resuelta_por == personas["sup"] and solicitud.via == Solicitud.BANDEJA

    respuesta = op.post(reverse("titulares:baja", args=[titular.pk]), {"motivo": motivo().pk, "nota": "se muda"})
    assert respuesta.status_code == 302
    baja = Solicitud.objects.get(titular=titular, accion="baja")
    sup.post(reverse("solicitudes:aprobar", args=[baja.pk]))
    titular.refresh_from_db()
    assert titular.estado == Titular.BAJA and titular.motivo_baja == motivo()

    op.post(reverse("titulares:reactivar", args=[titular.pk]), {})
    reactivacion = Solicitud.objects.get(titular=titular, accion="reactivacion")
    sup.post(reverse("solicitudes:aprobar", args=[reactivacion.pk]))
    titular.refresh_from_db()
    assert titular.estado == Titular.ACTIVO
    acciones = set(Evento.objects.values_list("accion", flat=True))
    assert {"titular_creado", "solicitud_creada", "solicitud_aprobada"} <= acciones


def test_alta_directa_por_supervision(personas):
    titular = alta_por_vista(cliente(personas["sup"]))
    assert titular.estado == Titular.ACTIVO
    assert not Solicitud.objects.filter(titular=titular).exists()
    assert Evento.objects.filter(accion="alta_aplicada", datos__via="directa").exists()


def test_rechazo_de_alta_conserva_matricula(personas):
    op, sup = cliente(personas["op"]), cliente(personas["sup"])
    titular = alta_por_vista(op)
    solicitud = Solicitud.objects.get(titular=titular)
    sup.post(reverse("solicitudes:rechazar", args=[solicitud.pk]), {"nota": "datos incompletos"})
    titular.refresh_from_db()
    assert titular.estado == Titular.RECHAZADO
    otro = alta_por_vista(op, "Beto")
    assert otro.matricula != titular.matricula


def test_alta_y_baja_por_delegacion(personas):
    op, sup = cliente(personas["op"]), cliente(personas["sup"])
    respuesta = sup.post(reverse("delegacion_nueva"), {"receptor": personas["op"].pk, "permiso": "alta_baja_directa", "usos": 2, "motivo": "semana de inscripciones"})
    assert respuesta.status_code == 302
    delegacion = Delegacion.objects.get()
    titular = alta_por_vista(op, "Delegada")
    assert titular.estado == Titular.ACTIVO
    op.post(reverse("titulares:baja", args=[titular.pk]), {"motivo": motivo().pk})
    titular.refresh_from_db()
    assert titular.estado == Titular.BAJA
    delegacion.refresh_from_db()
    assert delegacion.usos == 2 and not delegacion.vigente()
    assert Evento.objects.filter(accion="delegacion_usada").count() == 2
    agotada = alta_por_vista(op, "Agotada")
    assert agotada.estado == Titular.PENDIENTE
    assert Solicitud.objects.filter(titular=agotada, estado=Solicitud.PENDIENTE).exists()


def test_delegacion_vencida_no_aplica(personas):
    Delegacion.objects.create(otorgante=personas["sup"], receptor=personas["op"], permiso="alta_baja_directa", vence=timezone.now() - timedelta(minutes=1))
    titular = alta_por_vista(cliente(personas["op"]), "Vencida")
    assert titular.estado == Titular.PENDIENTE
    assert not Evento.objects.filter(accion="delegacion_usada").exists()


def test_delegacion_revocada_no_aplica(personas):
    Delegacion.objects.create(otorgante=personas["sup"], receptor=personas["op"], permiso="alta_baja_directa", usos_maximos=5, revocada=True)
    titular = alta_por_vista(cliente(personas["op"]), "Revocada")
    assert titular.estado == Titular.PENDIENTE


def test_no_se_delega_lo_que_no_se_tiene(personas):
    c = cliente(personas["op"])
    assert c.get(reverse("delegacion_nueva")).status_code == 403


def test_alta_y_baja_por_codigo_telefonico(personas):
    op = cliente(personas["op"])
    titular = alta_por_vista(op, "Codigo")
    solicitud = Solicitud.objects.get(titular=titular)
    respuesta = op.post(reverse("solicitudes:codigo", args=[solicitud.pk]), {"autorizador": personas["sup"].pk, "codigo": codigo_actual(personas["sup"])})
    assert respuesta.status_code == 302
    titular.refresh_from_db()
    solicitud.refresh_from_db()
    assert titular.estado == Titular.ACTIVO
    assert solicitud.via == Solicitud.CODIGO and solicitud.resuelta_por == personas["sup"]
    usado = CodigoUsado.objects.get(solicitud=solicitud)
    assert usado.revision == CodigoUsado.POR_REVISAR and usado.usado_por == personas["op"]

    op.post(reverse("titulares:baja", args=[titular.pk]), {"motivo": motivo().pk})
    baja = Solicitud.objects.get(titular=titular, accion="baja")
    op.post(reverse("solicitudes:codigo", args=[baja.pk]), {"autorizador": personas["sup2"].pk, "codigo": codigo_actual(personas["sup2"])})
    titular.refresh_from_db()
    assert titular.estado == Titular.BAJA

    aviso = cliente(credencial=None)
    respuesta = aviso.post(reverse("entrar"), {"usuario": "supervision", "contrasena": CONTRASENA})
    assert respuesta.url == reverse("entrar_codigo")
    respuesta = aviso.post(reverse("entrar_codigo"), {"codigo": codigo_actual(personas["sup"], 1)})
    assert respuesta.url == reverse("autorizaciones")
    pagina = aviso.get(reverse("autorizaciones")).content.decode()
    assert "Por revisar" in pagina
    aviso.post(reverse("revisar_autorizacion", args=[usado.pk]), {"decision": "reportar"})
    usado.refresh_from_db()
    assert usado.revision == CodigoUsado.REPORTADO
    assert Evento.objects.filter(accion="codigo_reportado").exists()


def test_codigo_reutilizado_rechazado(personas):
    op = cliente(personas["op"])
    primero = alta_por_vista(op, "Uno")
    segundo = alta_por_vista(op, "Dos")
    codigo = codigo_actual(personas["sup"])
    s1 = Solicitud.objects.get(titular=primero)
    s2 = Solicitud.objects.get(titular=segundo)
    op.post(reverse("solicitudes:codigo", args=[s1.pk]), {"autorizador": personas["sup"].pk, "codigo": codigo})
    respuesta = op.post(reverse("solicitudes:codigo", args=[s2.pk]), {"autorizador": personas["sup"].pk, "codigo": codigo})
    assert respuesta.status_code == 200
    assert "ya se usó" in respuesta.content.decode()
    s2.refresh_from_db()
    segundo.refresh_from_db()
    assert s2.estado == Solicitud.PENDIENTE and segundo.estado == Titular.PENDIENTE
    assert Evento.objects.filter(accion="codigo_rechazado", datos__motivo="reutilizado").exists()


def test_codigo_de_inicio_de_sesion_no_sirve_para_autorizar(personas):
    op = cliente(personas["op"])
    titular = alta_por_vista(op, "Sesion")
    codigo = codigo_actual(personas["sup"])
    entrada = cliente()
    entrada.post(reverse("entrar"), {"usuario": "supervision", "contrasena": CONTRASENA})
    assert entrada.post(reverse("entrar_codigo"), {"codigo": codigo}).url == reverse("inicio")
    solicitud = Solicitud.objects.get(titular=titular)
    op.post(reverse("solicitudes:codigo", args=[solicitud.pk]), {"autorizador": personas["sup"].pk, "codigo": codigo})
    solicitud.refresh_from_db()
    assert solicitud.estado == Solicitud.PENDIENTE


def test_codigo_erroneo_rechazado(personas):
    op = cliente(personas["op"])
    titular = alta_por_vista(op, "Erroneo")
    solicitud = Solicitud.objects.get(titular=titular)
    malo = str((int(codigo_actual(personas["sup"])) + 1) % 1_000_000).zfill(6)
    op.post(reverse("solicitudes:codigo", args=[solicitud.pk]), {"autorizador": personas["sup"].pk, "codigo": malo})
    solicitud.refresh_from_db()
    assert solicitud.estado == Solicitud.PENDIENTE


def test_autoaprobacion_rechazada(personas):
    Delegacion.objects.create(otorgante=personas["sup"], receptor=personas["op"], permiso="aprobar_solicitudes", usos_maximos=5)
    op = cliente(personas["op"])
    titular = alta_por_vista(op, "Propia")
    solicitud = Solicitud.objects.get(titular=titular)
    op.post(reverse("solicitudes:aprobar", args=[solicitud.pk]))
    solicitud.refresh_from_db()
    assert solicitud.estado == Solicitud.PENDIENTE
    with pytest.raises(motor.ErrorSolicitud):
        motor.aprobar(solicitud, personas["op"])
    with pytest.raises(motor.ErrorSolicitud):
        motor.rechazar(solicitud, personas["op"])
    assert Evento.objects.filter(accion="aprobacion_rechazada", datos__motivo="autoaprobacion").exists()
    op2 = cliente(personas["op2"])
    assert op2.post(reverse("solicitudes:aprobar", args=[solicitud.pk])).status_code == 403
    solicitud.refresh_from_db()
    assert solicitud.estado == Solicitud.PENDIENTE


def test_autorizacion_por_codigo_propio_rechazada(personas, roles):
    personas["op"].totp_secreto = personas["sup"].totp_secreto
    personas["op"].totp_confirmado = True
    personas["op"].save()
    titular = alta_por_vista(cliente(personas["op"]), "PropioCodigo")
    solicitud = Solicitud.objects.get(titular=titular)
    with pytest.raises(motor.ErrorSolicitud):
        motor.autorizar_con_codigo(solicitud, personas["op"], personas["op"], codigo_actual(personas["op"]))
    with pytest.raises(PermissionDenied):
        motor.autorizar_con_codigo(solicitud, personas["op2"], personas["sup"], codigo_actual(personas["sup"]))
    solicitud.refresh_from_db()
    assert solicitud.estado == Solicitud.PENDIENTE


def test_delegacion_de_aprobacion_permite_aprobar_ajenas(personas):
    Delegacion.objects.create(otorgante=personas["sup"], receptor=personas["op2"], permiso="aprobar_solicitudes", usos_maximos=1)
    titular = alta_por_vista(cliente(personas["op"]), "Ajena")
    solicitud = Solicitud.objects.get(titular=titular)
    cliente(personas["op2"]).post(reverse("solicitudes:aprobar", args=[solicitud.pk]))
    solicitud.refresh_from_db()
    assert solicitud.estado == Solicitud.APROBADA and solicitud.via == Solicitud.DELEGACION


def test_solicitud_caducada_no_se_aprueba(personas):
    titular = alta_por_vista(cliente(personas["op"]), "Caduca")
    solicitud = Solicitud.objects.get(titular=titular)
    Solicitud.objects.filter(pk=solicitud.pk).update(caduca_en=timezone.now() - timedelta(minutes=1))
    cliente(personas["sup"]).post(reverse("solicitudes:aprobar", args=[solicitud.pk]))
    solicitud.refresh_from_db()
    titular.refresh_from_db()
    assert solicitud.estado == Solicitud.CADUCADA and titular.estado == Titular.PENDIENTE


def test_no_se_duplica_solicitud_pendiente(personas):
    op = cliente(personas["op"])
    titular = alta_por_vista(op, "Doble")
    op.post(reverse("titulares:solicitar_alta", args=[titular.pk]), {})
    assert Solicitud.objects.filter(titular=titular).count() == 1
