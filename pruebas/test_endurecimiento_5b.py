import re
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PIL import Image
from pypdf import PdfReader

from auditoria.models import Evento
from caja import servicios as caja
from caja.models import Caja
from cobros import libro
from cobros.models import ConceptoCobro, Pago, Recibo
from configuracion import marca
from configuracion.models import Parametro
from inventario import servicios as inventario
from inventario.models import Articulo, Conteo
from proyecto.seguridad import POLITICA_CONTENIDO
from solicitudes import motor

from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo
from .test_endurecimiento_5a import rutas
from .test_interfaz import _ofensas, png


@pytest.fixture
def limpio():
    cache.clear()
    yield
    cache.clear()


def archivos():
    carpeta = Path(settings.RUTA_COMPROBANTES)
    return set(carpeta.iterdir()) if carpeta.exists() else set()


def test_logo_faltante_o_alterado_no_inunda_la_bitacora(personas, limpio):
    actual = marca.guardar_logo(png(), personas["dir"])
    Path(settings.RUTA_COMPROBANTES, actual.logo).unlink()
    c = cliente(personas["op"])
    for _ in range(25):
        assert c.get(reverse("marca_logo") + f"?v={actual.version}").status_code == 404
    assert Evento.objects.filter(accion="logo_alterado").count() == 1


def test_logo_reemplazado_o_quitado_no_deja_archivos(personas, limpio):
    antes = archivos()
    primero = marca.guardar_logo(png(), personas["dir"])
    segundo = marca.guardar_logo(png(color=(1, 2, 3)), personas["dir"])
    assert len(archivos() - antes) == 1
    assert not Path(settings.RUTA_COMPROBANTES, primero.logo).exists()
    assert marca.leer_logo(segundo)
    marca.quitar_logo(personas["dir"])
    assert archivos() == antes


@pytest.mark.parametrize("formato, tamano", [("PNG", (6000, 6000)), ("JPEG", (4000, 900)), ("PNG", (300, 2400))], ids=["png-cuadrado", "jpeg-ancho", "png-alto"])
def test_logo_enorme_se_reduce(personas, limpio, formato, tamano):
    salida = BytesIO()
    Image.new("RGB", tamano, (10, 20, 30)).save(salida, format=formato)
    actual = marca.guardar_logo(salida.getvalue(), personas["dir"])
    with Image.open(BytesIO(marca.leer_logo(actual))) as imagen:
        assert max(imagen.size) == marca.LADO_MAXIMO_LOGO
        assert abs(imagen.size[0] / imagen.size[1] - tamano[0] / tamano[1]) < 0.02
        assert not {"exif", "comment", "icc_profile"} & set(imagen.info)


def test_logo_pequeno_no_cambia_de_tamano(personas, limpio):
    actual = marca.guardar_logo(png(40, 20), personas["dir"])
    with Image.open(BytesIO(marca.leer_logo(actual))) as imagen:
        assert imagen.size == (40, 20)


@pytest.mark.parametrize("cargos", [1, 9, 10, 30, 80], ids=lambda n: f"{n}-cargos")
def test_recibo_pdf_largo_pagina_sin_perder_el_codigo(personas, limpio, cargos):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    concepto = ConceptoCobro.objects.get(nombre="Libros")
    for n in range(cargos - 1):
        libro.crear_cargo(ana, concepto, 1000, date(2026, 1, 10), "manual", descripcion=f"Cargo {n}", usuario=personas["op"])
    turno = caja.abrir_turno(personas["op"], Caja.objects.get_or_create(nombre="Caja 1")[0], 0)
    pago = libro.registrar_pago(ana, 100000 + 1000 * (cargos - 1), Pago.EFECTIVO, personas["op"], turno=turno)
    assert pago.aplicaciones.count() == cargos
    recibo = Recibo.objects.get(pago=pago)
    respuesta = cliente(personas["op"]).get(reverse("cobros:recibo_pdf", args=[recibo.pk]))
    lector = PdfReader(BytesIO(respuesta.content))
    fuera = []

    def visita(texto, cm, tm, fd, fs):
        if texto.strip() and not 30 < tm[5] < 792:
            fuera.append((texto, tm[5]))

    paginas = [pagina.extract_text(visitor_text=visita) for pagina in lector.pages]
    assert fuera == []
    assert recibo.codigo in paginas[-1] and "Importe recibido" in paginas[-1]
    assert sum(texto.count("Cargo ") for texto in paginas) == cargos - 1
    assert len(paginas) == 1 if cargos <= 9 else cargos < 30 or len(paginas) > 1


def test_niveles_de_referencia_sin_una_consulta_por_articulo(personas, limpio):
    preparar_conceptos()
    Parametro.objects.update_or_create(clave="modulo_inventario", defaults={"valor": "1"})
    libros = ConceptoCobro.objects.get(nombre="Libros")
    articulos = [Articulo.objects.create(clave=f"A-{n}", nombre=f"Articulo {n}", precio=1000, concepto=libros) for n in range(60)]
    conteo = inventario.subir_conteo({a.pk: 10 for a in articulos}, personas["op"], Conteo.PANTALLA)
    motor.aprobar(conteo.solicitud, personas["sup"])
    inventario.registrar_movimiento("entrada", articulos[0], 5, "Compra", "", personas["op"])
    sin_nada = Articulo.objects.create(clave="B-1", nombre="Sin movimientos", precio=1000, concepto=libros)
    with CaptureQueriesContext(connection) as consultas:
        niveles = inventario.niveles_referencia(articulos + [sin_nada])
    assert len(consultas) <= 2
    assert niveles[articulos[0].pk] == 15 and niveles[articulos[1].pk] == 10 and niveles[sin_nada.pk] == 0
    assert inventario.niveles_referencia([]) == {}
    with CaptureQueriesContext(connection) as consultas:
        inventario.para_vender()
    assert len(consultas) <= 8


def test_ninguna_pantalla_lleva_estilos_en_linea_ni_pierde_la_politica(personas, limpio):
    preparar_conceptos()
    Parametro.objects.update_or_create(clave="modulo_inventario", defaults={"valor": "1"})
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    marca.guardar_colores("#1F1A4E", "#F58634", personas["dir"])
    marca.guardar_logo(png(), personas["dir"])
    turno = caja.abrir_turno(personas["op"], Caja.objects.get_or_create(nombre="Caja 1")[0], 10000)
    pago = libro.registrar_pago(ana, 5000, Pago.EFECTIVO, personas["op"], turno=turno)
    claves = list(dict.fromkeys([1, ana.pk, pago.pk, turno.pk]))
    revisadas = 0
    for clave in ("op", "sup", "dir"):
        c = cliente(personas[clave])
        for nombre, patron in rutas():
            url = "/" + patron.replace("^", "").replace("$", "")
            if "salir" in url or "admin" in url:
                continue
            for destino in dict.fromkeys([re.sub(r"<[^>]+>", str(pk), url) for pk in claves] if "<" in url else [url]):
                respuesta = c.get(destino)
                if respuesta.status_code != 200 or not respuesta.get("Content-Type", "").startswith("text/html"):
                    continue
                revisadas += 1
                assert respuesta["Content-Security-Policy"] == POLITICA_CONTENIDO, (clave, destino)
                assert _ofensas(respuesta.content.decode()) == [], (clave, destino)
    assert revisadas > 120


def test_el_menu_nunca_enlaza_a_algo_prohibido(personas, limpio):
    Parametro.objects.update_or_create(clave="modulo_inventario", defaults={"valor": "1"})
    for clave in ("op", "sup", "dir"):
        c = cliente(personas[clave])
        pagina = c.get(reverse("inicio")).content.decode()
        nav = re.search(r'(?s)<nav class="menu"[^>]*>(.*?)</nav>', pagina).group(1)
        enlaces = re.findall(r'href="([^"]+)"', nav)
        assert enlaces
        for url in enlaces:
            assert c.get(url).status_code == 200, (clave, url)
