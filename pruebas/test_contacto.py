import pytest
from django.urls import reverse

from auditoria.models import Evento
from titulares.models import CampoContacto, Contacto, Titular

from .conftest import cliente, configurar, nuevo_usuario


def formulario(telefono=None, **extra):
    datos = {"nombre": "Ana", "apellidos": "Prueba", "contacto_nombre": "Responsable", "constancia_consentimiento": "on"}
    campo = CampoContacto.objects.get(tipo=CampoContacto.TELEFONO)
    if telefono is not None:
        datos[campo.clave] = telefono
    datos.update(extra)
    return datos


def test_escuela_exige_telefono_en_el_alta(personas):
    c = cliente(personas["op"])
    respuesta = c.post(reverse("titulares:nuevo"), formulario())
    assert respuesta.status_code == 200
    assert not Titular.objects.exists()
    respuesta = c.post(reverse("titulares:nuevo"), formulario("12345"))
    assert respuesta.status_code == 200 and "Teléfono no válido" in respuesta.content.decode()
    assert not Titular.objects.exists()
    respuesta = c.post(reverse("titulares:nuevo"), formulario("(55) 1234-5678"))
    assert respuesta.status_code == 302
    contacto = Contacto.objects.get()
    campo = CampoContacto.objects.get(tipo=CampoContacto.TELEFONO)
    assert contacto.principal and contacto.valor(campo) == "525512345678"


def test_correo_invalido_rechazado(personas):
    campo = CampoContacto.objects.get(tipo=CampoContacto.CORREO)
    respuesta = cliente(personas["op"]).post(reverse("titulares:nuevo"), formulario("5512345678", **{campo.clave: "no-es-correo"}))
    assert respuesta.status_code == 200 and not Titular.objects.exists()


@pytest.mark.django_db
def test_generico_no_exige_telefono():
    roles = configurar("generico")
    c = cliente(nuevo_usuario("op", roles["Operación"]))
    assert c.post(reverse("titulares:nuevo"), formulario("")).status_code == 302
    assert Titular.objects.count() == 1


def test_ficha_y_detalle_muestran_contacto_principal(personas):
    c = cliente(personas["op"])
    c.post(reverse("titulares:nuevo"), formulario("5512345678"))
    titular = Titular.objects.get()
    ficha = c.get(reverse("titulares:ficha_pago", args=[titular.pk])).content.decode()
    assert "+52 55 1234 5678" in ficha and "Responsable" in ficha and titular.matricula_formateada in ficha
    assert "Instrucciones de prueba" in ficha
    detalle = c.get(reverse("titulares:detalle", args=[titular.pk])).content.decode()
    assert "+52 55 1234 5678" in detalle


def test_edicion_de_contacto_auditada(personas):
    c = cliente(personas["op"])
    c.post(reverse("titulares:nuevo"), formulario("5512345678"))
    titular = Titular.objects.get()
    contacto = Contacto.objects.get()
    campo = CampoContacto.objects.get(tipo=CampoContacto.TELEFONO)
    url = reverse("titulares:contacto_editar", args=[titular.pk, contacto.pk])
    assert c.post(url, {"contacto_nombre": "Otra persona", campo.clave: "abc", "contacto_principal": "on"}).status_code == 200
    respuesta = c.post(url, {"contacto_nombre": "Otra persona", campo.clave: "+52 33 9876 5432", "contacto_principal": "on"})
    assert respuesta.status_code == 302
    contacto.refresh_from_db()
    assert contacto.nombre == "Otra persona" and contacto.valor(campo) == "523398765432"
    evento = Evento.objects.filter(accion="contacto_editado").latest("id")
    assert evento.usuario == personas["op"]
    assert evento.datos["antes"]["valores"][str(campo.pk)] == "525512345678"
    assert evento.datos["despues"]["valores"][str(campo.pk)] == "523398765432"


def test_segundo_contacto_principal_desplaza_al_primero(personas):
    c = cliente(personas["op"])
    c.post(reverse("titulares:nuevo"), formulario("5512345678"))
    titular = Titular.objects.get()
    campo = CampoContacto.objects.get(tipo=CampoContacto.TELEFONO)
    c.post(reverse("titulares:contacto_nuevo", args=[titular.pk]), {"contacto_nombre": "Segundo", campo.clave: "5511112222", "contacto_principal": "on"})
    assert Contacto.objects.get(principal=True).nombre == "Segundo"
    assert Contacto.objects.filter(titular=titular).count() == 2


def test_configurar_campos_de_contacto(personas):
    c = cliente(personas["dir"])
    respuesta = c.post(reverse("configuracion:catalogo_nuevo", args=["campos"]), {"etiqueta": "Teléfono alterno", "tipo": "telefono", "orden": 30, "activo": "on"})
    assert respuesta.status_code == 302
    assert CampoContacto.objects.filter(etiqueta="Teléfono alterno").exists()
    assert Evento.objects.filter(accion="campo_contacto_creado").exists()
    assert cliente(personas["sup"]).get(reverse("configuracion:catalogo", args=["campos"])).status_code == 403
