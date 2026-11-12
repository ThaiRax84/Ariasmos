import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from cobros.models import ConceptoCobro
from configuracion.models import Negocio, vocabulario
from cuentas.models import Dispositivo, Usuario
from nucleo import totp

from .conftest import CONTRASENA


def paso_negocio(token):
    return {
        "token": token,
        "nombre": "Mi negocio",
        "plantilla": "escuela",
        "instrucciones_pago": "Banco X, cuenta 000",
        "zona_horaria": "America/Mexico_City",
        "sede": 0,
        "ranuras": 10,
        "longitud_matricula": 7,
    }


@pytest.mark.django_db
def test_asistente_completo_deja_instalacion_usable():
    c = Client()
    assert c.get(reverse("titulares:lista")).url == reverse("asistente:inicio")
    assert c.get(reverse("asistente:inicio")).status_code == 200
    respuesta = c.post(reverse("asistente:inicio"), paso_negocio("token-equivocado"))
    assert respuesta.status_code == 200 and not Negocio.objects.exists()
    assert c.get(reverse("asistente:conceptos")).url == reverse("asistente:inicio")
    assert c.post(reverse("asistente:inicio"), paso_negocio(settings.TOKEN_ASISTENTE)).url == reverse("asistente:conceptos")
    colegiatura = ConceptoCobro.objects.get(tipo="recurrente")
    datos = {f"importe_{c_.pk}": "100" for c_ in ConceptoCobro.objects.all()}
    datos.update({f"importe_{colegiatura.pk}": "1500.50", f"dia_{colegiatura.pk}": 10, f"recargo_tipo_{colegiatura.pk}": "porcentaje", f"recargo_valor_{colegiatura.pk}": "10", f"recargo_gracia_{colegiatura.pk}": 3})
    assert c.post(reverse("asistente:conceptos"), datos).url == reverse("asistente:usuario")
    colegiatura.refresh_from_db()
    assert colegiatura.importe_centavos == 150050 and colegiatura.dia_vencimiento == 10 and colegiatura.regla_recargo.valor == 1000
    respuesta = c.post(reverse("asistente:usuario"), {"usuario": "jefa", "nombre": "Jefa", "contrasena1": CONTRASENA, "contrasena2": CONTRASENA})
    assert respuesta.url == reverse("asistente:codigo")
    secreto = c.session["asistente"]["secreto"]
    assert secreto in c.get(reverse("asistente:codigo")).content.decode()
    respuesta = c.post(reverse("asistente:codigo"), {"codigo": totp.codigo(secreto, totp.paso_actual())})
    assert respuesta.url == reverse("inicio")
    negocio = Negocio.objects.get()
    assert negocio.configurado
    jefa = Usuario.objects.get(usuario="jefa")
    assert jefa.totp_confirmado and jefa.tiene_permiso("administrar_usuarios")
    assert Dispositivo.objects.get(estado=Dispositivo.APROBADO).aprobado_por == jefa
    assert vocabulario()["titular"] == "Alumno"
    assert c.get(reverse("inicio")).status_code == 200
    assert c.get(reverse("asistente:inicio")).status_code == 404
    otro = Client()
    assert otro.get(reverse("entrar")).url == reverse("dispositivo_pendiente")
