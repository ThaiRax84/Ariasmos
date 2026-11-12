import pytest
from django.urls import reverse

from auditoria.models import Evento
from cuentas.models import Delegacion
from solicitudes import motor
from solicitudes.models import Solicitud
from titulares.models import CampoContacto, Contacto, Titular

from .conftest import cliente, codigo_actual
from .test_flujos import alta_por_vista


def edicion(titular, **cambios):
    datos = {"nombre": titular.nombre, "apellidos": titular.apellidos, "agrupacion": titular.agrupacion_id or "", "notas": titular.notas}
    datos.update(cambios)
    return datos


@pytest.fixture
def activo(personas):
    titular = alta_por_vista(cliente(personas["sup"]), "Original")
    assert titular.estado == Titular.ACTIVO
    return titular


def test_operacion_no_cambia_nombre_de_activo_sin_aprobacion(personas, activo):
    op = cliente(personas["op"])
    respuesta = op.post(reverse("titulares:editar", args=[activo.pk]), edicion(activo, nombre="Otra", notas="nota libre"), follow=True)
    activo.refresh_from_db()
    assert activo.nombre == "Original" and activo.notas == "nota libre"
    assert "SOLICITUD pendiente" in respuesta.content.decode()
    solicitud = Solicitud.objects.get(titular=activo, accion="correccion_nombre")
    assert solicitud.estado == Solicitud.PENDIENTE and solicitud.datos["nombre"] == "Otra"
    pagina = cliente(personas["sup"]).get(reverse("solicitudes:detalle", args=[solicitud.pk])).content.decode()
    assert "Original Prueba" in pagina and "Otra Prueba" in pagina
    cliente(personas["sup"]).post(reverse("solicitudes:aprobar", args=[solicitud.pk]))
    activo.refresh_from_db()
    assert activo.nombre == "Otra"


def test_nombre_libre_mientras_esta_pendiente(personas):
    op = cliente(personas["op"])
    titular = alta_por_vista(op, "Pendiente")
    op.post(reverse("titulares:editar", args=[titular.pk]), edicion(titular, nombre="Corregido"))
    titular.refresh_from_db()
    assert titular.nombre == "Corregido"
    assert not Solicitud.objects.filter(accion="correccion_nombre").exists()


def test_supervision_cambia_nombre_directo(personas, activo):
    cliente(personas["sup"]).post(reverse("titulares:editar", args=[activo.pk]), edicion(activo, apellidos="Nuevo"))
    activo.refresh_from_db()
    assert activo.apellidos == "Nuevo"
    assert Evento.objects.filter(accion="correccion_nombre_aplicada", titular=activo.pk, datos__via="directa").exists()


def test_correccion_por_delegacion(personas, activo):
    Delegacion.objects.create(otorgante=personas["sup"], receptor=personas["op"], permiso="alta_baja_directa", usos_maximos=1)
    cliente(personas["op"]).post(reverse("titulares:editar", args=[activo.pk]), edicion(activo, nombre="Delegado"))
    activo.refresh_from_db()
    assert activo.nombre == "Delegado"


def test_correccion_por_codigo(personas, activo):
    op = cliente(personas["op"])
    op.post(reverse("titulares:editar", args=[activo.pk]), edicion(activo, nombre="PorCodigo"))
    solicitud = Solicitud.objects.get(accion="correccion_nombre")
    op.post(reverse("solicitudes:codigo", args=[solicitud.pk]), {"autorizador": personas["sup"].pk, "codigo": codigo_actual(personas["sup"])})
    activo.refresh_from_db()
    assert activo.nombre == "PorCodigo"


def test_correccion_autoaprobacion_rechazada(personas, activo):
    Delegacion.objects.create(otorgante=personas["sup"], receptor=personas["op"], permiso="aprobar_solicitudes", usos_maximos=3)
    op = cliente(personas["op"])
    op.post(reverse("titulares:editar", args=[activo.pk]), edicion(activo, nombre="Propia"))
    solicitud = Solicitud.objects.get(accion="correccion_nombre")
    op.post(reverse("solicitudes:aprobar", args=[solicitud.pk]))
    with pytest.raises(motor.ErrorSolicitud):
        motor.aprobar(solicitud, personas["op"])
    activo.refresh_from_db()
    solicitud.refresh_from_db()
    assert activo.nombre == "Original" and solicitud.estado == Solicitud.PENDIENTE


def test_correccion_en_baja_y_rechazo(personas, activo):
    activo.estado = Titular.BAJA
    activo.save()
    op = cliente(personas["op"])
    op.post(reverse("titulares:editar", args=[activo.pk]), edicion(activo, nombre="EnBaja"))
    solicitud = Solicitud.objects.get(accion="correccion_nombre")
    cliente(personas["sup"]).post(reverse("solicitudes:rechazar", args=[solicitud.pk]), {"nota": "no procede"})
    activo.refresh_from_db()
    assert activo.nombre == "Original" and activo.estado == Titular.BAJA


def test_historial_muestra_quien_edito_nombre_y_telefono(personas):
    op = cliente(personas["op"])
    titular = alta_por_vista(op, "Ana")
    op.post(reverse("titulares:editar", args=[titular.pk]), edicion(titular, nombre="Anabel"))
    contacto = Contacto.objects.get(titular=titular)
    campo = CampoContacto.objects.get(tipo=CampoContacto.TELEFONO)
    op.post(reverse("titulares:contacto_editar", args=[titular.pk, contacto.pk]), {"contacto_nombre": "Responsable", campo.clave: "3398765432", "contacto_principal": "on"})
    cliente(personas["sup"]).post(reverse("solicitudes:aprobar", args=[Solicitud.objects.get(titular=titular).pk]))
    pagina = op.get(reverse("titulares:historial", args=[titular.pk])).content.decode()
    assert "Persona operacion" in pagina and "Persona supervision" in pagina
    assert "Nombre: Ana → Anabel" in pagina
    assert "Teléfono: +52 55 1234 5678 → +52 33 9876 5432" in pagina
    assert "Estado: Pendiente → Activo" in pagina
    assert "Capturó el registro" in pagina and "Solicitó el alta" in pagina
    assert '"cambios"' not in pagina and "{&#x27;" not in pagina


def test_operacion_ve_historial_pero_no_bitacora(personas):
    op = cliente(personas["op"])
    titular = alta_por_vista(op, "Visible")
    assert op.get(reverse("titulares:historial", args=[titular.pk])).status_code == 200
    assert op.get(reverse("auditoria:lista")).status_code == 403
    direccion = cliente(personas["dir"])
    pagina = direccion.get(reverse("auditoria:lista") + f"?titular={titular.matricula}&usuario={personas['op'].pk}").content.decode()
    assert "titular_creado" in pagina
    otra = direccion.get(reverse("auditoria:lista") + f"?usuario={personas['dir'].pk}").content.decode()
    assert "titular_creado" not in otra
