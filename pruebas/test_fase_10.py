import importlib

import pytest
from django.apps import apps as registro
from django.db import OperationalError, connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from auditoria.models import Evento
from caja.models import Denominacion, Traslado
from caja.servicios import abrir_turno, cerrar_turno, entregar
from cobros import libro
from cobros.models import Cargo, ConceptoCobro, Pago
from configuracion.models import Negocio, Parametro, Vocabulario, parametro
from cuentas.models import PreferenciaOrden
from envios import middleware
from titulares.models import Agrupacion, Familia, Titular
from titulares.servicios import crear_titular

from .conftest import cliente
from .libro_ayudas import piezas_de, preparar_conceptos, titular_activo, turno_de


def alta(personas, nombre, apellidos="Prueba", **datos):
    titular = crear_titular(personas["op"], {"nombre": nombre, "apellidos": apellidos, **datos}, contacto={"nombre": "Resp", "valores": {}}, conceptos=[])
    from solicitudes import motor

    motor.ejecutar("alta", personas["sup"], titular)
    titular.refresh_from_db()
    return titular


def test_control_de_piezas_viene_encendido_de_fabrica(roles):
    assert parametro("control_denominaciones") == 1
    assert Parametro.objects.get(clave="control_denominaciones").valor == "1"


def _migracion():
    return importlib.import_module("configuracion.migrations.0017_control_denominaciones_de_fabrica")


def test_la_actualizacion_enciende_el_control_y_avisa_a_quien_configura(personas):
    Parametro.objects.update_or_create(clave="control_denominaciones", defaults={"valor": "0"})
    _migracion().encender(registro, None)
    assert parametro("control_denominaciones") == 1 and parametro("aviso_control_denominaciones") == 1
    texto = cliente(personas["dir"]).get(reverse("inicio")).content.decode()
    assert "El efectivo ahora se cuenta por billetes y monedas" in texto and reverse("configuracion:caja") in texto and reverse("configuracion:aviso_piezas") in texto
    assert "El efectivo ahora se cuenta" not in cliente(personas["op"]).get(reverse("inicio")).content.decode()
    assert cliente(personas["op"]).post(reverse("configuracion:aviso_piezas")).status_code == 403
    assert cliente(personas["dir"]).post(reverse("configuracion:aviso_piezas")).status_code == 302
    assert parametro("aviso_control_denominaciones") == 0 and parametro("control_denominaciones") == 1
    assert Evento.objects.filter(accion="aviso_control_denominaciones_descartado").count() == 1
    assert "El efectivo ahora se cuenta" not in cliente(personas["dir"]).get(reverse("inicio")).content.decode()


def test_la_actualizacion_respeta_lo_encendido_y_las_instalaciones_nuevas(personas):
    Parametro.objects.update_or_create(clave="control_denominaciones", defaults={"valor": "1"})
    _migracion().encender(registro, None)
    assert parametro("aviso_control_denominaciones") == 0
    Parametro.objects.filter(clave="control_denominaciones").delete()
    Negocio.objects.filter(pk=1).update(configurado=False)
    _migracion().encender(registro, None)
    assert not Parametro.objects.filter(clave="control_denominaciones").exists() and parametro("aviso_control_denominaciones") == 0
    Negocio.objects.filter(pk=1).update(configurado=True)
    _migracion().encender(registro, None)
    assert Parametro.objects.get(clave="control_denominaciones").valor == "1" and parametro("aviso_control_denominaciones") == 1


def test_apagarlo_a_proposito_sigue_pidiendo_importes(personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    Parametro.objects.update_or_create(clave="control_denominaciones", defaults={"valor": "0"})
    op = cliente(personas["op"])
    pagina = op.get(reverse("caja:inicio")).content.decode()
    assert 'name="fondo_inicial"' in pagina and "data-mosaicos" not in pagina
    turno = turno_de(personas["op"])
    respuesta = op.post(reverse("cobros:cobrar", args=[ana.pk]), {"importe": "100"})
    ficha = respuesta.context["ficha"]
    assert 'name="r_' not in respuesta.content.decode()
    assert op.post(reverse("cobros:cobrar", args=[ana.pk]), {"paso": "confirmar", "ficha": ficha, "importe": "10000"}).status_code == 302
    assert Pago.objects.get().turno == turno


def test_sin_denominaciones_se_dice_y_se_lleva_a_capturarlas(personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    Denominacion.objects.update(activa=False)
    op, direccion = cliente(personas["op"]), cliente(personas["dir"])
    for ruta in (reverse("caja:inicio"), reverse("cobros:cobrar", args=[ana.pk]), reverse("caja:entrega"), reverse("caja:deposito"), reverse("caja:retiro_nuevo")):
        texto = op.get(ruta).content.decode()
        assert "Faltan los billetes y monedas" in texto and "Pide a" in texto, ruta
        assert 'name="importe"' not in texto and 'name="fondo_inicial"' not in texto, ruta
    assert "Capturar billetes y monedas" in direccion.get(reverse("caja:inicio")).content.decode()
    assert op.post(reverse("caja:abrir"), {"caja": 1, "apertura": "efectivo", "fondo_inicial": "100"}).status_code == 200
    from caja.models import Turno

    assert not Turno.objects.exists()


def test_recibir_una_entrega_pide_contar_las_piezas(personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 150000, Pago.EFECTIVO, personas["op"], turno=turno, piezas={"recibidas": {"100000": 1, "50000": 1}, "cambio": {}})
    cerrar_turno(turno, personas["op"], {"100000": 1, "50000": 1})
    entrega = entregar(personas["op"], personas["sup"], 150000, piezas={"100000": 1, "50000": 1})
    sup = cliente(personas["sup"])
    pagina = sup.get(reverse("caja:confirmar", args=[entrega.pk])).content.decode()
    assert "data-mosaicos" in pagina and "Billetes y monedas que recibiste" in pagina
    assert sup.post(reverse("caja:confirmar", args=[entrega.pk]), {"importe": "1500"}).status_code == 200
    assert Traslado.objects.get(pk=entrega.pk).estado == Traslado.PENDIENTE
    assert sup.post(reverse("caja:confirmar", args=[entrega.pk]), {"p_50000": "3"}).status_code == 302
    assert Traslado.objects.get(pk=entrega.pk).estado == Traslado.CONFIRMADO
    assert Evento.objects.filter(accion="entrega_piezas_distintas").exists()


@pytest.fixture
def padron(personas):
    preparar_conceptos()
    grupo = Agrupacion.objects.create(nombre="Tercero B")
    familia = Familia.objects.create(nombre="Casa Robles")
    ana = alta(personas, "Ana", "Zamora", agrupacion=grupo)
    beto = alta(personas, "Beto", "Alcalá", familia=familia)
    pendiente = crear_titular(personas["op"], {"nombre": "Ciro", "apellidos": "Pendiente"}, contacto={"nombre": "R", "valores": {}}, conceptos=[])
    concepto = ConceptoCobro.objects.get(nombre="Inscripción")
    libro.crear_cargo(ana, concepto, 120000, ana.activo_desde or Titular.objects.get(pk=ana.pk).creado.date(), Cargo.MANUAL, usuario=personas["sup"])
    return {"ana": ana, "beto": beto, "pendiente": pendiente, "grupo": grupo, "familia": familia}


def test_cobrar_muestra_la_lista_de_activos_sin_buscar(personas, padron):
    texto = cliente(personas["op"]).get(reverse("cobros:buscar")).content.decode()
    assert "Ana Zamora" in texto and "Beto Alcalá" in texto and "Ciro Pendiente" not in texto
    assert reverse("cobros:cobrar", args=[padron["ana"].pk]) in texto and "Tercero B" in texto and "Casa Robles" in texto
    assert "data-filtro-vivo" in texto and "data-lista-viva" in texto


def test_el_adeudo_solo_lo_ve_quien_puede_ver_saldos(personas, padron):
    Parametro.objects.update_or_create(clave="tope_pago_individual", defaults={"valor": "9999999"})
    from cuentas.models import PermisoRol

    con_saldos = cliente(personas["sup"]).get(reverse("cobros:buscar")).content.decode()
    assert "Debe $1,200.00" in con_saldos
    PermisoRol.objects.filter(rol=personas["op"].rol, permiso="ver_titulares").delete()
    sin_saldos = cliente(personas["op"]).get(reverse("cobros:buscar")).content.decode()
    assert "Ana Zamora" in sin_saldos and "1,200.00" not in sin_saldos and "Al corriente" not in sin_saldos


@pytest.mark.parametrize("texto, esperados", [("zamo", {"Ana Zamora"}), ("tercero", {"Ana Zamora"}), ("robles", {"Beto Alcalá"}), ("beto alc", {"Beto Alcalá"})])
def test_el_filtro_reduce_por_nombre_apellidos_agrupacion_y_familia(personas, padron, texto, esperados):
    respuesta = cliente(personas["op"]).get(reverse("cobros:buscar"), {"q": texto})
    assert {t.nombre_completo for t in respuesta.context["filas"]} == esperados


def test_el_filtro_por_matricula_y_la_busqueda_completa(personas, padron):
    op = cliente(personas["op"])
    matricula = padron["beto"].matricula
    assert [t.pk for t in op.get(reverse("cobros:buscar"), {"q": matricula[:5]}).context["filas"]] == [padron["beto"].pk]
    respuesta = op.get(reverse("cobros:buscar"), {"q": "ciro"})
    assert not respuesta.context["filas"] and [t.pk for t in respuesta.context["completos"]] == [padron["pendiente"].pk]
    assert "Fuera de la lista" in respuesta.content.decode()


def test_la_lista_respeta_el_orden_elegido_y_lo_recuerda(personas, padron):
    op = cliente(personas["op"])
    respuesta = op.get(reverse("cobros:buscar"), {"orden": "nombre", "sentido": "desc"})
    assert [t.nombre for t in respuesta.context["filas"]] == ["Beto", "Ana"]
    assert PreferenciaOrden.objects.get(usuario=personas["op"], lista="cobrar").clave == "nombre"
    assert [t.nombre for t in op.get(reverse("cobros:buscar")).context["filas"]] == ["Beto", "Ana"]


def test_vender_a_un_titular_tambien_muestra_la_lista(personas, padron):
    Parametro.objects.update_or_create(clave="modulo_inventario", defaults={"valor": "1"})
    texto = cliente(personas["op"]).get(reverse("inventario:vender")).content.decode()
    assert reverse("inventario:vender_titular", args=[padron["ana"].pk]) in texto and "Beto Alcalá" in texto


def test_la_lista_usa_el_vocabulario(personas, padron):
    Vocabulario.objects.update_or_create(clave="titulares", defaults={"texto": "Socios"})
    Vocabulario.objects.update_or_create(clave="matricula", defaults={"texto": "Número de socio"})
    texto = cliente(personas["op"]).get(reverse("cobros:buscar"), {"q": "nadie-zz"}).content.decode()
    assert "número de socio" in texto and "Nadie de la lista coincide" in texto
    assert "alumno" not in texto.lower() and "matrícula" not in texto.lower().split("<main", 1)[-1].split("</main>")[0]


def test_la_lista_pagina_de_cincuenta_sin_una_consulta_por_renglon(personas):
    preparar_conceptos()
    concepto = ConceptoCobro.objects.get(nombre="Inscripción")

    def crear(cuantos, desde):
        for numero in range(desde, desde + cuantos):
            titular = alta(personas, f"Persona{numero:03d}")
            libro.crear_cargo(titular, concepto, 1000 + numero, titular.creado.date(), Cargo.MANUAL, usuario=personas["sup"])

    crear(3, 0)
    sup = cliente(personas["sup"])
    sup.get(reverse("cobros:buscar"))
    with CaptureQueriesContext(connection) as pocos:
        sup.get(reverse("cobros:buscar"))
    crear(57, 3)
    with CaptureQueriesContext(connection) as muchos:
        respuesta = sup.get(reverse("cobros:buscar"))
    assert len(muchos.captured_queries) == len(pocos.captured_queries)
    assert len(respuesta.context["filas"]) == 50 and respuesta.context["pagina"].paginator.num_pages == 2
    segunda = sup.get(reverse("cobros:buscar"), {"pagina": "2"})
    assert len(segunda.context["filas"]) == 10 and "Página 2 de 2" in segunda.content.decode()


def _peticion():
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.test import RequestFactory

    peticion = RequestFactory().post("/x/", {}, HTTP_REFERER="http://testserver/caja/")
    peticion.user = None
    peticion.session = {}
    peticion._messages = FallbackStorage(peticion)
    return peticion


def test_base_ocupada_se_reintenta_en_lugar_de_fallar(transactional_db, monkeypatch):
    from django.http import HttpResponse

    llamadas = []

    def vista(request):
        llamadas.append(1)
        if len(llamadas) < 3:
            raise OperationalError("database is locked")
        return HttpResponse("listo")

    monkeypatch.setattr(middleware, "PAUSA", 0)
    capa = middleware.BaseOcupada(lambda request: None)
    peticion = _peticion()
    capa.process_view(peticion, vista, (), {})
    try:
        vista(peticion)
    except OperationalError as error:
        respuesta = capa.process_exception(peticion, error)
    assert respuesta.status_code == 200 and respuesta.content == b"listo" and len(llamadas) == 3
    assert capa.process_exception(peticion, OperationalError("no such table")) is None


def test_base_siempre_ocupada_regresa_sin_error(transactional_db, monkeypatch):
    def vista(request):
        raise OperationalError("database is locked")

    monkeypatch.setattr(middleware, "PAUSA", 0)
    capa = middleware.BaseOcupada(lambda request: None)
    peticion = _peticion()
    capa.process_view(peticion, vista, (), {})
    respuesta = capa.process_exception(peticion, OperationalError("database is locked"))
    assert respuesta.status_code == 302 and respuesta.url == "http://testserver/caja/"


def test_los_botones_se_bloquean_al_enviar_y_se_liberan_al_volver():
    from pathlib import Path

    from django.conf import settings

    codigo = (Path(settings.SISTEMA) / "estaticos" / "js" / "sistema.js").read_text(encoding="utf-8")
    assert 'addEventListener("submit"' in codigo and "dataset.enviando" in codigo
    assert 'addEventListener("pageshow", liberarTodo)' in codigo and "trabajando" in codigo
    assert "data-depende-de" in codigo and "data-mostrar-si" in codigo
    assert ".disabled = true" not in codigo
    estilos = (Path(settings.SISTEMA) / "estaticos" / "css" / "sistema.css").read_text(encoding="utf-8")
    assert ".boton.trabajando" in estilos


def test_abrir_turno_sin_piezas_no_abre(personas):
    from caja.models import Caja, Turno

    caja = Caja.objects.get_or_create(nombre="Caja 1")[0]
    assert cliente(personas["op"]).post(reverse("caja:abrir"), {"caja": caja.pk, "apertura": "efectivo", "fondo_inicial": "500"}).status_code == 200
    assert not Turno.objects.exists()
    abrir_turno(personas["op"], caja, 0, piezas=piezas_de(50000))
    assert Turno.objects.get().fondo_inicial == 50000
