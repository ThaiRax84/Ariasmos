import re

import pytest
from django.urls import reverse

from caja import servicios as caja
from caja.models import Caja, MovimientoPiezas, Turno
from cobros import libro
from cobros.models import Cargo, ConceptoCobro, Pago
from configuracion.models import hoy_negocio
from cuentas.models import Rol
from solicitudes import motor
from titulares.models import Titular
from titulares.servicios import crear_titular

from .ayudas_navegador import sesion_navegador
from .conftest import nuevo_usuario
from .test_fabrica import correr_asistente

pytestmark = pytest.mark.django_db(transaction=True)

NOMBRES = (("Ana", "Prueba Uno"), ("Beto", "Prueba Dos"), ("Carla", "Prueba Tres"), ("Dario", "Prueba Cuatro"))


def preparar(con_turno=True):
    correr_asistente("escuela")
    op = nuevo_usuario("cajero", Rol.objects.get(nombre="Operación"))
    sup = nuevo_usuario("supervisor", Rol.objects.get(nombre="Supervisión"))
    concepto = ConceptoCobro.objects.filter(activo=True).first()
    titulares = []
    for nombre, apellidos in NOMBRES:
        titular = crear_titular(op, {"nombre": nombre, "apellidos": apellidos}, contacto={"nombre": "Resp", "valores": {}}, conceptos=[])
        motor.ejecutar("alta", sup, titular)
        titular.refresh_from_db()
        assert titular.estado == Titular.ACTIVO
        libro.crear_cargo(titular, concepto, 185000, hoy_negocio(), Cargo.MANUAL, descripcion="Cargo de prueba")
        titulares.append(titular)
    if con_turno:
        caja.abrir_turno(op, Caja.objects.filter(activa=True).first(), 37000, piezas={"10000": 2, "5000": 2, "2000": 5, "1000": 5, "500": 4})
    return {"op": op, "sup": sup, "titulares": titulares}


def espera(localizador):
    from playwright.sync_api import expect

    return expect(localizador)


def sin_errores(sesion):
    errores = [e for e in sesion.errores if "favicon" not in e]
    assert not errores, errores


def test_cobrar_en_el_panel_con_cambio_propuesto_por_el_servidor(sesion_navegador):
    datos = preparar()
    ana = datos["titulares"][0]
    pagina = sesion_navegador.pagina(datos["op"])
    sesion_navegador.ir(pagina, reverse("cobros:buscar"))
    sesion_navegador.captura(pagina, "cobrar-lista")
    filtro = pagina.locator("[data-filtro-lista]")
    filtro.fill("ana")
    espera(pagina.locator(".lista-titulares .renglon-titular")).to_have_count(1)
    assert pagina.locator(".lista-titulares mark").first.inner_text().lower() == "ana"
    filtro.press("Enter")
    pagina.wait_for_selector("#panel-cobro [data-cobro-efectivo]")
    assert pagina.locator("[data-cobro-rejilla]").get_attribute("class").count("abierta") == 1
    pagina.wait_for_timeout(400)
    sesion_navegador.captura(pagina, "cobrar-panel")
    assert pagina.locator("[data-importe-cobro]").input_value() == "1850.00"
    pagina.evaluate("() => { const b = document.querySelector('.pieza[data-centavos=\"100000\"] .mosaico'); b.click(); b.click(); b.click(); }")
    assert pagina.locator(".pieza[data-centavos='100000'] input").input_value() == "3"
    pagina.locator(".pieza[data-centavos='100000'] .mosaico-quitar").click()
    assert pagina.locator(".pieza[data-centavos='100000'] input").input_value() == "2"
    assert pagina.locator("[data-boton-cobro]").inner_text() == "Ver el cambio"
    pagina.wait_for_timeout(600)
    assert "150.00" in pagina.locator("[data-falta-valor]").inner_text()
    pagina.locator("[data-boton-cobro]").click()
    pagina.wait_for_selector("#panel-cobro .piezas-entrega")
    sesion_navegador.captura(pagina, "cobrar-cambio")
    assert Pago.objects.count() == 0
    pagina.evaluate("() => { const b = document.querySelector('#panel-cobro form button[type=submit]'); b.click(); b.click(); b.click(); }")
    pagina.wait_for_selector("#panel-cobro [data-exito]")
    sesion_navegador.captura(pagina, "cobrar-exito")
    assert Pago.objects.count() == 1
    pago = Pago.objects.get()
    assert pago.titular_id == ana.pk and pago.importe == 185000
    cambio = {m.denominacion: -m.piezas for m in MovimientoPiezas.objects.filter(pago=pago, origen=MovimientoPiezas.CAMBIO)}
    assert sum(v * c for v, c in cambio.items()) == 15000
    pagina.locator("[data-accion='siguiente']").click()
    assert "abierta" not in pagina.locator("[data-cobro-rejilla]").get_attribute("class")
    sin_errores(sesion_navegador)


def test_pago_exacto_se_registra_con_un_toque_y_esc_cierra(sesion_navegador):
    datos = preparar()
    beto = datos["titulares"][1]
    pagina = sesion_navegador.pagina(datos["op"])
    sesion_navegador.ir(pagina, reverse("cobros:buscar"))
    pagina.locator(f".renglon-titular[data-id='{beto.pk}']").click()
    pagina.wait_for_selector("#panel-cobro [data-cobro-efectivo]")
    pagina.keyboard.press("Escape")
    assert "abierta" not in pagina.locator("[data-cobro-rejilla]").get_attribute("class")
    pagina.locator(f".renglon-titular[data-id='{beto.pk}']").click()
    pagina.wait_for_selector("#panel-cobro [data-cobro-efectivo]")
    pagina.locator("[data-importe-cobro]").fill("100")
    mosaico = pagina.locator(".pieza[data-centavos='5000'] .mosaico")
    mosaico.focus()
    pagina.keyboard.press("2")
    assert pagina.locator(".pieza[data-centavos='5000'] input").input_value() == "2"
    assert pagina.locator("[data-boton-cobro]").inner_text() == "Confirmar y dar recibo"
    pagina.locator("[data-boton-cobro]").click()
    pagina.wait_for_selector("#panel-cobro [data-exito]")
    assert Pago.objects.get().importe == 10000
    sin_errores(sesion_navegador)
