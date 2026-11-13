import json

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from banco.models import CuentaBancaria
from cobros.models import ConceptoCobro
from configuracion.models import Negocio, vocabulario
from cuentas.models import Dispositivo, Usuario
from nucleo import totp

from .conftest import CONTRASENA

CLABE_PRUEBA = "002010077777777771"


def paso_inicio(token, plantilla="escuela", archivo=None):
    datos = {"token": token, "nombre": "Mi negocio", "plantilla": plantilla, "zona_horaria": "America/Mexico_City"}
    if archivo is not None:
        datos["archivo"] = archivo
    return datos


def terminar(c, usuario="jefa"):
    respuesta = c.post(reverse("asistente:usuario"), {"usuario": usuario, "nombre": "Jefa", "contrasena1": CONTRASENA, "contrasena2": CONTRASENA})
    assert respuesta.url == reverse("asistente:codigo")
    secreto = c.session["asistente"]["secreto"]
    assert secreto in c.get(reverse("asistente:codigo")).content.decode()
    return c.post(reverse("asistente:codigo"), {"codigo": totp.codigo(secreto, totp.paso_actual())})


@pytest.mark.django_db
def test_asistente_completo_deja_instalacion_usable():
    c = Client()
    assert c.get(reverse("titulares:lista")).url == reverse("asistente:inicio")
    pagina = c.get(reverse("asistente:inicio")).content.decode()
    for campo in ("longitud_matricula", "sede", "ranuras", "instrucciones_pago"):
        assert f'name="{campo}"' not in pagina
    assert "Importar un archivo de plantilla" in pagina
    respuesta = c.post(reverse("asistente:inicio"), paso_inicio("token-equivocado"))
    assert respuesta.status_code == 200 and not Negocio.objects.exists()
    assert c.get(reverse("asistente:conceptos")).url == reverse("asistente:inicio")
    assert c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE)).url == reverse("asistente:personalizar")
    negocio = Negocio.objects.get()
    assert (negocio.longitud_matricula, negocio.sede, negocio.ranuras) == (7, 0, 10)
    assert "Usar tal cual" in c.get(reverse("asistente:personalizar")).content.decode()
    colegiatura = ConceptoCobro.objects.get(tipo="recurrente")
    datos = {f"importe_{c_.pk}": "100" for c_ in ConceptoCobro.objects.all()}
    datos.update({f"importe_{colegiatura.pk}": "1500.50", f"dia_{colegiatura.pk}": 10, f"recargo_tipo_{colegiatura.pk}": "porcentaje", f"recargo_valor_{colegiatura.pk}": "10", f"recargo_gracia_{colegiatura.pk}": 3})
    assert c.post(reverse("asistente:conceptos"), datos).url == reverse("asistente:pago")
    colegiatura.refresh_from_db()
    assert colegiatura.importe_centavos == 150050 and colegiatura.dia_vencimiento == 10 and colegiatura.regla_recargo.valor == 1000
    respuesta = c.post(reverse("asistente:pago"), {"clabe": "002 010 07777777777 1", "beneficiario": "Mi negocio SA", "medios": [], "referencia_en": "ambos", "contacto_dudas": "55 1234 5678"})
    assert respuesta.url == reverse("asistente:usuario")
    cuenta = CuentaBancaria.objects.get()
    assert cuenta.principal and cuenta.clabe == CLABE_PRUEBA and cuenta.banco.clave == "002"
    assert terminar(c).url == reverse("inicio")
    negocio.refresh_from_db()
    assert negocio.configurado
    jefa = Usuario.objects.get(usuario="jefa")
    assert jefa.totp_confirmado and jefa.tiene_permiso("administrar_usuarios")
    assert Dispositivo.objects.get(estado=Dispositivo.APROBADO).aprobado_por == jefa
    assert vocabulario()["titular"] == "Alumno"
    assert "Faltan los datos de pago" not in c.get(reverse("inicio")).content.decode()
    assert c.get(reverse("asistente:inicio")).status_code == 404
    otro = Client()
    assert otro.get(reverse("entrar")).url == reverse("dispositivo_pendiente")


@pytest.mark.django_db
def test_pago_omitido_avisa_en_inicio():
    c = Client()
    c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE, "generico"))
    assert c.get(reverse("asistente:pago")).status_code == 200
    assert terminar(c).url == reverse("inicio")
    assert not CuentaBancaria.objects.exists()
    assert "Faltan los datos de pago" in c.get(reverse("inicio")).content.decode()


@pytest.mark.django_db
def test_personalizar_vocabulario_y_conceptos():
    c = Client()
    c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE, "generico"))
    quitar = ConceptoCobro.objects.get(nombre="Otro cargo")
    datos = {"titular": "Socio", "titulares": "Socios", "matricula": "Número de socio", "agrupacion": "Grupo", "agrupaciones": "Grupos", "familia": "Cuenta", "familias": "Cuentas", f"quitar_{quitar.pk}": "on", "nuevo_nombre": "Cuota anual", "nuevo_tipo": "recurrente", "nuevo_periodicidad": "anual", "nuevo_aplica_a": "todos", "nuevo_recargo": "on", "seguir": "continuar"}
    assert c.post(reverse("asistente:personalizar"), datos).url == reverse("asistente:conceptos")
    assert vocabulario()["titular"] == "Socio"
    assert not ConceptoCobro.objects.filter(nombre="Otro cargo").exists()
    nuevo = ConceptoCobro.objects.get(nombre="Cuota anual")
    assert nuevo.periodicidad == "anual"
    assert f'name="recargo_valor_{nuevo.pk}"' in c.get(reverse("asistente:conceptos")).content.decode()


@pytest.mark.django_db
def test_importar_plantilla_de_punta_a_punta():
    with open(settings.PLANTILLAS_NEGOCIO / "generico.json", encoding="utf-8") as archivo:
        datos = json.load(archivo)
    datos["nombre"] = "Gimnasio de ejemplo"
    datos["vocabulario"] = dict(datos["vocabulario"], titular="Miembro", titulares="Miembros")
    datos["conceptos"] = [{"nombre": "Membresía", "tipo": "recurrente", "periodicidad": "mensual", "aplica_a": "todos", "recargo": {"tipo": "porcentaje", "dias_gracia": 5, "se_repite": False}}]
    archivo = SimpleUploadedFile("mia.json", json.dumps(datos).encode("utf-8"), content_type="application/json")
    c = Client()
    respuesta = c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE, "importar", archivo))
    assert respuesta.url == reverse("asistente:revisar")
    assert not ConceptoCobro.objects.filter(nombre="Membresía").exists()
    resumen = c.get(reverse("asistente:revisar")).content.decode()
    assert "Gimnasio de ejemplo" in resumen and "Quién hace cada cosa" in resumen
    assert c.post(reverse("asistente:revisar"), {}).url == reverse("asistente:personalizar")
    assert Negocio.objects.get().plantilla == "importada"
    assert vocabulario()["titular"] == "Miembro"
    membresia = ConceptoCobro.objects.get(nombre="Membresía")
    pagina = c.get(reverse("asistente:conceptos")).content.decode()
    assert f'name="recargo_valor_{membresia.pk}"' in pagina
    assert terminar(c).url == reverse("inicio")
    assert Negocio.objects.get().configurado
