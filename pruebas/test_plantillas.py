import json

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from auditoria.models import Evento
from banco.models import Banco, CuentaBancaria
from cobros.models import ConceptoCobro, ReglaRecargo
from configuracion import esquema
from configuracion.models import Negocio
from titulares.servicios import crear_titular

from .conftest import cliente


def base():
    with open(settings.PLANTILLAS_NEGOCIO / "generico.json", encoding="utf-8") as archivo:
        return json.load(archivo)


def bytes_de(datos):
    return json.dumps(datos).encode("utf-8")


@pytest.mark.parametrize("nombre", ["generico", "escuela"])
def test_plantillas_incluidas_cumplen_el_esquema(nombre):
    with open(settings.PLANTILLAS_NEGOCIO / f"{nombre}.json", "rb") as archivo:
        datos = esquema.desde_bytes(archivo.read())
    assert {p["accion"] for p in datos["politicas"]} >= {"alta", "baja", "reactivacion", "correccion_nombre"}
    assert datos["medios_pago"] == ["Transferencia SPEI", "Depósito en ventanilla", "Efectivo en caja"]


def test_generico_sirve_tal_cual():
    datos = esquema.validar(base())
    nombres = {c["nombre"]: c for c in datos["conceptos"]}
    assert set(nombres) == {"Alta o inscripción", "Mensualidad", "Producto o servicio", "Otro cargo"}
    assert nombres["Mensualidad"]["tipo"] == "recurrente" and nombres["Mensualidad"]["recargo"]
    assert not any(c["obligatorio"] for c in datos["campos_contacto"])


def _mutada(**cambios):
    datos = base()
    datos.update(cambios)
    return datos


@pytest.mark.parametrize(
    "contenido,mensaje",
    [
        (b"{" + b" " * (300 * 1024) + b"}", "256 KB"),
        ("{\"nombre\": \"á\"}".encode("latin-1"), "UTF-8"),
        (b"{nombre: 1}", "JSON válido"),
        (b"[" * 100000 + b"]" * 100000, "JSON válido"),
        (b"[]", "objeto"),
        (bytes_de(_mutada(codigo="__import__('os')")), "claves no permitidas"),
        (bytes_de(_mutada(roles=[{"nombre": "X", "permisos": ["ser_dios"]}])), "permiso inexistente"),
        (bytes_de(_mutada(conceptos=[{"nombre": "X", "tipo": "infinito"}])), "conceptos[0].tipo"),
        (bytes_de(_mutada(conceptos=[{"nombre": f"C{i}", "tipo": "unico"} for i in range(101)])), "más de 100"),
        (bytes_de(_mutada(motivos_baja=["x"] * 101)), "más de 100"),
        (bytes_de(_mutada(rol_inicial="Operación")), "rol_inicial"),
        (bytes_de(_mutada(roles=[])), "al menos un rol"),
        (bytes_de(_mutada(nombre="x" * 61)), "entre 1 y 60"),
        (bytes_de(_mutada(conceptos=[{"nombre": "X", "tipo": "unico", "prioridad": True}])), "número entero"),
        (bytes_de(_mutada(conceptos=[{"nombre": "X", "tipo": "unico", "aplica_a": "agrupacion"}])), "aplica_a"),
        (bytes_de(_mutada(vocabulario={"titular": "A", "clave_secreta": "x"})), "claves no permitidas"),
        (bytes_de(_mutada(politicas=base()["politicas"][:1])), "faltan políticas"),
        (bytes_de(_mutada(campos_contacto=[{"etiqueta": "A", "tipo": "telefono", "extra": 1}])), "claves no permitidas"),
        (bytes_de(_mutada(motivos_baja=["Uno", "uno"])), "repetido"),
    ],
)
def test_plantillas_maliciosas_o_malformadas_rechazadas(contenido, mensaje):
    with pytest.raises(esquema.PlantillaInvalida) as error:
        esquema.desde_bytes(contenido)
    assert mensaje in str(error.value)


@pytest.mark.django_db
def test_asistente_rechaza_plantilla_invalida_con_mensaje():
    c = Client()
    for contenido, mensaje in ((bytes_de(_mutada(roles=[{"nombre": "X", "permisos": ["ser_dios"]}])), "permiso inexistente"), (b"x" * (300 * 1024), "256 KB")):
        archivo = SimpleUploadedFile("p.json", contenido, content_type="application/json")
        respuesta = c.post(reverse("asistente:inicio"), {"token": settings.TOKEN_ASISTENTE, "nombre": "N", "zona_horaria": "America/Mexico_City", "plantilla": "importar", "archivo": archivo})
        assert respuesta.status_code == 200 and mensaje in respuesta.content.decode()
        assert not Negocio.objects.exists()
    assert Evento.objects.filter(accion="plantilla_rechazada").count() == 2


@pytest.mark.django_db
def test_asistente_no_procesa_archivo_sin_token():
    archivo = SimpleUploadedFile("p.json", bytes_de(base()), content_type="application/json")
    respuesta = Client().post(reverse("asistente:inicio"), {"token": "malo", "nombre": "N", "zona_horaria": "America/Mexico_City", "plantilla": "importar", "archivo": archivo})
    assert respuesta.status_code == 200 and not Negocio.objects.exists()


def test_exportar_sin_importes_clabe_usuarios_ni_titulares(personas):
    colegiatura = ConceptoCobro.objects.get(nombre="Colegiatura")
    colegiatura.importe_centavos = 987654
    colegiatura.regla_recargo = ReglaRecargo.objects.create(nombre="Recargo", tipo="porcentaje", valor=4321, dias_gracia=5, tope_centavos=55555)
    colegiatura.save()
    CuentaBancaria.objects.create(banco=Banco.objects.get(clave="002"), clabe="002010077777777771", beneficiario="Beneficiario secreto", principal=True)
    crear_titular(personas["op"], {"nombre": "Zacarías", "apellidos": "Titularino"})
    c = cliente(personas["dir"])
    assert cliente(personas["dir"], reingreso=False).get(reverse("configuracion:exportar")).url.startswith(reverse("confirmar"))
    respuesta = c.get(reverse("configuracion:exportar"))
    assert respuesta.status_code == 200 and "attachment" in respuesta["Content-Disposition"]
    texto = respuesta.content.decode("utf-8")
    for prohibido in ("987654", "9876.54", "4321", "55555", "importe", "valor", '"tope', "002010077777777771", "Beneficiario secreto", "Zacarías", "Titularino", "operacion", "supervision", "direccion", "Persona", "clave", "Negocio de prueba", "token"):
        assert prohibido not in texto, prohibido
    datos = esquema.desde_bytes(respuesta.content)
    concepto = next(x for x in datos["conceptos"] if x["nombre"] == "Colegiatura")
    assert concepto["recargo"] == {"tipo": "porcentaje", "dias_gracia": 5, "se_repite": False}
    assert datos["rol_inicial"] == "Dirección" and datos["medios_pago"]
    assert Evento.objects.filter(accion="plantilla_exportada", usuario=personas["dir"]).exists()
    assert cliente(personas["sup"]).get(reverse("configuracion:exportar")).status_code == 403


def test_exportacion_se_puede_volver_a_importar(personas):
    contenido = cliente(personas["dir"]).get(reverse("configuracion:exportar")).content
    assert esquema.desde_bytes(contenido)["nombre"] == "Configuración exportada"
