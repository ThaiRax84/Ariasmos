import json
from datetime import date

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from auditoria.models import Verificacion
from cobros.models import Cargo
from configuracion.models import Negocio, Tarea, vocabulario
from configuracion.trabajador import ejecutar_ciclo
from solicitudes.models import Solicitud
from titulares.models import Contacto, Familia, Titular

from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo
from .test_flujos import datos_alta


def test_trabajador_se_pone_al_dia_sin_duplicar(personas, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        preparar_conceptos()
        ana = titular_activo(personas["op"], personas["sup"], "Ana")
    with django_capture_on_commit_callbacks(execute=True):
        ejecutar_ciclo(date(2026, 1, 5))
    assert Cargo.objects.filter(titular=ana, origen=Cargo.AUTOMATICO).exclude(periodo="").count() == 1
    with django_capture_on_commit_callbacks(execute=True):
        informe = ejecutar_ciclo(date(2026, 4, 20))
    assert all(exito for _, exito, _ in informe), informe
    periodos = sorted(Cargo.objects.filter(titular=ana, origen=Cargo.AUTOMATICO).exclude(periodo="").values_list("periodo", flat=True))
    assert periodos == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert Cargo.objects.filter(titular=ana, origen=Cargo.RECARGO).count() == 4
    antes = Cargo.objects.count()
    segundo = ejecutar_ciclo(date(2026, 4, 20))
    assert Cargo.objects.count() == antes
    assert dict((n, t) for n, _, t in segundo)["verificar_bitacora"] == "ya se hizo hoy"
    assert Verificacion.objects.count() == 2
    call_command("trabajador", "--una-vez", "--fecha", "2026-04-21")
    assert Cargo.objects.count() == antes
    assert Tarea.objects.get(nombre="generar_cargos").ultima_fecha == date(2026, 4, 21)


def test_baja_detiene_cargos_futuros(personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    ejecutar_ciclo(date(2026, 1, 5))
    Titular.objects.filter(pk=ana.pk).update(estado=Titular.BAJA)
    ejecutar_ciclo(date(2026, 3, 5))
    assert not Cargo.objects.filter(titular=ana, periodo="2026-03").exists()


def test_alta_con_familia_nueva_y_contacto_compartido(personas):
    preparar_conceptos()
    op = cliente(personas["op"])
    datos = datos_alta("Ana")
    datos["familia_nueva"] = "Familia Ejemplo"
    op.post(reverse("titulares:nuevo"), datos)
    ana = Titular.objects.get(nombre="Ana")
    familia = Familia.objects.get()
    assert ana.familia == familia and Contacto.objects.filter(familia=familia, principal=True).exists()
    datos = datos_alta("Beto")
    datos["familia"] = familia.pk
    op.post(reverse("titulares:nuevo"), datos)
    beto = Titular.objects.get(nombre="Beto")
    assert beto.familia == familia
    ficha = op.get(reverse("titulares:ficha_pago", args=[beto.pk])).content.decode()
    assert "Responsable" in ficha
    vista = op.get(reverse("titulares:familia", args=[familia.pk])).content.decode()
    assert "Ana" in vista and "Beto" in vista and "Estado de cuenta" in vista


def test_cambio_de_familia_por_el_motor(personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana", iniciales=())
    familia = Familia.objects.create(nombre="Otra")
    op = cliente(personas["op"])
    op.post(reverse("titulares:cambiar_familia", args=[ana.pk]), {"modo": "ligar", "familia": familia.pk})
    ana.refresh_from_db()
    assert ana.familia is None
    solicitud = Solicitud.objects.get(accion="cambio_familia")
    cliente(personas["sup"]).post(reverse("solicitudes:aprobar", args=[solicitud.pk]))
    ana.refresh_from_db()
    assert ana.familia == familia
    cliente(personas["sup"]).post(reverse("titulares:cambiar_familia", args=[ana.pk]), {"modo": "desligar"})
    ana.refresh_from_db()
    assert ana.familia is None
    cliente(personas["sup"]).post(reverse("titulares:cambiar_familia", args=[ana.pk]), {"modo": "crear", "nombre": "Nueva"})
    ana.refresh_from_db()
    assert ana.familia.nombre == "Nueva"
    historial = op.get(reverse("titulares:historial", args=[ana.pk])).content.decode()
    assert "Otra" in historial and "Nueva" in historial


def test_resumen_de_plantilla_importada_con_advertencias(db):
    with open(settings.PLANTILLAS_NEGOCIO / "generico.json", encoding="utf-8") as archivo:
        datos = json.load(archivo)
    datos["roles"][0]["permisos"].append("administrar_usuarios")
    for politica in datos["politicas"]:
        if politica["accion"] == "beca":
            politica["permiso_directo"] = politica["permiso_solicitar"]
    c = Client()
    archivo = SimpleUploadedFile("p.json", json.dumps(datos).encode(), content_type="application/json")
    c.post(reverse("asistente:inicio"), {"token": settings.TOKEN_ASISTENTE, "nombre": "N", "zona_horaria": "America/Mexico_City", "plantilla": "importar", "archivo": archivo})
    pagina = c.get(reverse("asistente:revisar")).content.decode()
    assert "Advertencias" in pagina and "puede administrar usuarios" in pagina and "sin aprobación de nadie" in pagina
    assert c.post(reverse("asistente:revisar"), {}).status_code == 200
    assert vocabulario()["titular"] == "Titular" and Negocio.objects.get().plantilla == "importada"
    assert c.post(reverse("asistente:revisar"), {"confirmo": "on"}).url == reverse("asistente:personalizar")
    assert vocabulario()["titular"] == "Cliente"
