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


def test_buscar_o_ir_a_con_ctrl_k_abre_el_cobro_y_los_trucos_con_signo(sesion_navegador):
    datos = preparar()
    beto = datos["titulares"][1]
    pagina = sesion_navegador.pagina(datos["op"])
    sesion_navegador.ir(pagina, reverse("inicio"))
    pagina.keyboard.press("Control+k")
    pagina.wait_for_selector("#paleta[open]")
    pagina.locator("#paleta-texto").fill("beto")
    espera(pagina.locator(".paleta-item")).to_have_count(1)
    sesion_navegador.captura(pagina, "paleta")
    pagina.keyboard.press("Enter")
    pagina.wait_for_selector("#panel-cobro [data-cobro-efectivo]")
    assert f"abrir={beto.pk}" in pagina.url
    pagina.keyboard.press("Escape")
    pagina.locator("body").click(position={"x": 5, "y": 400})
    pagina.keyboard.press("?")
    pagina.wait_for_selector("#atajos[open]")
    pagina.locator("#atajos [data-cerrar-dialogo]").click()
    sin_errores(sesion_navegador)


def test_la_transferencia_que_llega_se_ve_sola_en_el_panel_y_en_la_lista(sesion_navegador, settings):
    from banco import llegadas
    from banco.llegadas import Aviso
    from banco.models import TopeDiarioBanco
    from configuracion.models import Parametro

    from . import origen_pruebas
    from .banco_ayudas import cuenta_principal

    datos = preparar()
    ana, beto = datos["titulares"][0], datos["titulares"][1]
    settings.ORIGENES_TRANSFERENCIA = ["pruebas.origen_pruebas.OrigenDePruebas"]
    cuenta_principal()
    for dia in range(7):
        TopeDiarioBanco.objects.update_or_create(dia=dia, defaults={"importe": 10 ** 9})
    Parametro.objects.update_or_create(clave="tope_aplicado_sin_respaldo", defaults={"valor": str(10 ** 9)})
    pagina = sesion_navegador.pagina(datos["op"])
    sesion_navegador.ir(pagina, reverse("cobros:buscar"))
    pagina.locator(f".renglon-titular[data-id='{ana.pk}']").click()
    pagina.wait_for_selector("#panel-cobro [data-cobro-efectivo]")
    pagina.locator("[data-metodos] button[data-metodo='transferencia']").click()
    pagina.wait_for_selector("[data-espera-transferencia]", state="visible")
    pagina.wait_for_timeout(400)
    sesion_navegador.captura(pagina, "cobrar-transferencia")
    origen_pruebas.PENDIENTES.append(Aviso(folio="N-1", fecha=hoy_negocio(), importe=185000, referencia=ana.referencia_bancaria))
    llegadas.consultar_todos()
    pagina.wait_for_selector("#panel-cobro [data-exito]", timeout=20000)
    assert "Transferencia recibida y aplicada" in pagina.locator("#panel-cobro [data-exito]").inner_text()
    pagina.wait_for_selector("#globo:not([hidden])")
    pagina.wait_for_selector(".aviso-breve .accion-aviso")
    sesion_navegador.captura(pagina, "cobrar-transferencia-llego")
    pagina.locator("[data-accion='siguiente']").click()
    origen_pruebas.PENDIENTES.append(Aviso(folio="N-2", fecha=hoy_negocio(), importe=185000, referencia=beto.referencia_bancaria))
    llegadas.consultar_todos()
    espera(pagina.locator(f".renglon-titular[data-id='{beto.pk}'] .adeudo")).to_have_text("Al corriente", timeout=20000)
    pagina.locator("[data-campana]").click()
    pagina.wait_for_selector("#campana-panel li[data-id]")
    sesion_navegador.captura(pagina, "campana")
    sin_errores(sesion_navegador)


def test_inicio_con_cifras_grafica_y_solicitudes_que_se_deshacen(sesion_navegador):
    from solicitudes.models import Solicitud

    datos = preparar(con_turno=False)
    caja.abrir_turno(datos["op"], Caja.objects.filter(activa=True).first(), 37000, piezas={"10000": 2, "5000": 2, "2000": 5, "1000": 5, "500": 4})
    libro.registrar_pago(datos["titulares"][2], 50000, Pago.EFECTIVO, datos["op"], turno=turno, piezas={"recibidas": {"50000": 1}, "cambio": {}})
    solicitudes = []
    for nombre in ("Eva", "Fede"):
        nuevo = crear_titular(datos["op"], {"nombre": nombre, "apellidos": "Pendiente"}, contacto={"nombre": "Resp", "valores": {}}, conceptos=[])
        solicitudes.append(motor.ejecutar("alta", datos["op"], nuevo).solicitud)
    assert all(s is not None for s in solicitudes)
    pagina = sesion_navegador.pagina(datos["sup"])
    sesion_navegador.ir(pagina, reverse("inicio"))
    pagina.wait_for_timeout(900)
    sesion_navegador.captura(pagina, "inicio")
    assert "500.00" in pagina.locator("[data-cifra='cobrado_hoy'] .numero").inner_text()
    alto = pagina.locator(".dia.hoy .tramo.ef").evaluate("e => e.getBoundingClientRect().height")
    assert alto > 10
    primera, segunda = solicitudes
    caja_primera = pagina.locator(f"[data-solicitud][data-id='{primera.pk}']")
    caja_primera.locator("[data-abrir-solicitud]").click()
    caja_primera.locator("form[data-en-espera='aprobar'] button").click()
    pagina.wait_for_selector(".aviso-breve .accion-aviso")
    pagina.locator(".aviso-breve .accion-aviso", has_text="Deshacer").click()
    pagina.wait_for_timeout(6000)
    assert Solicitud.objects.get(pk=primera.pk).estado == Solicitud.PENDIENTE
    assert caja_primera.is_visible()
    caja_primera.locator("form[data-en-espera='aprobar'] button").click()
    pagina.wait_for_timeout(6500)
    assert Solicitud.objects.get(pk=primera.pk).estado == Solicitud.APROBADA
    caja_segunda = pagina.locator(f"[data-solicitud][data-id='{segunda.pk}']")
    caja_segunda.locator("[data-abrir-solicitud]").click()
    caja_segunda.locator("[data-rechazar]").click()
    caja_segunda.locator("textarea").fill("Faltan datos")
    caja_segunda.locator("form[data-en-espera='rechazar'] button").click()
    pagina.wait_for_timeout(300)
    sesion_navegador.ir(pagina, reverse("solicitudes:bandeja"))
    assert Solicitud.objects.get(pk=segunda.pk).estado == Solicitud.RECHAZADA
    assert Solicitud.objects.get(pk=segunda.pk).nota_resolucion == "Faltan datos"
    sin_errores(sesion_navegador)


def test_ficha_con_pestanas_historial_y_correccion_con_deshacer(sesion_navegador):
    from titulares.models import CampoContacto, Contacto
    from auditoria.models import Evento

    datos = preparar(con_turno=False)
    ana = datos["titulares"][0]
    campo = CampoContacto.objects.filter(tipo="telefono").first() or CampoContacto.objects.first()
    contacto = Contacto.objects.filter(titular=ana).first()
    valores = dict(contacto.valores)
    valores[str(campo.pk)] = "5512345678" if campo.tipo == "telefono" else "dato@ejemplo.mx"
    Contacto.objects.filter(pk=contacto.pk).update(valores=valores)
    pagina = sesion_navegador.pagina(datos["op"])
    sesion_navegador.ir(pagina, reverse("titulares:detalle", args=[ana.pk]))
    assert pagina.locator("[data-hoja='datos']").is_hidden()
    pagina.locator("[data-pestana='historial']").click()
    pagina.wait_for_selector("[data-hoja='historial'] .linea-tiempo li")
    sesion_navegador.captura(pagina, "ficha-historial")
    pagina.locator("[data-pestana='datos']").click()
    boton = pagina.locator(f"button[data-editar][data-campo='{campo.clave}']")
    boton.click()
    nuevo = "5598765432" if campo.tipo == "telefono" else "otro@ejemplo.mx"
    entrada = pagina.locator(".edicion-en-linea")
    entrada.fill(nuevo)
    entrada.press("Enter")
    pagina.wait_for_selector(".aviso-breve .accion-aviso")
    contacto.refresh_from_db()
    assert nuevo in contacto.valores[str(campo.pk)].replace(" ", "")
    sesion_navegador.captura(pagina, "ficha-datos")
    pagina.locator(".aviso-breve .accion-aviso", has_text="Deshacer").click()
    pagina.wait_for_timeout(1500)
    contacto.refresh_from_db()
    assert contacto.valores[str(campo.pk)].replace(" ", "").endswith(valores[str(campo.pk)])
    assert Evento.objects.filter(accion__icontains="contacto").count() >= 2
    sin_errores(sesion_navegador)


def test_configuracion_con_vista_previa_orden_arrastrable_y_cambios_sin_guardar(sesion_navegador):
    from configuracion.models import parametro

    correr_asistente("escuela")
    director = nuevo_usuario("director", Rol.objects.get(nombre="Dirección"))
    pagina = sesion_navegador.pagina(director)
    sesion_navegador.ir(pagina, reverse("configuracion:marca"))
    pagina.locator("input[name='color_principal']").fill("#1F3A8A")
    pagina.locator("input[name='color_acento']").fill("#2F9E8F")
    pagina.wait_for_selector(".sin-guardar:not([hidden])")
    assert pagina.evaluate("() => document.documentElement.style.getPropertyValue('--primario')") == "#1F3A8A"
    sesion_navegador.captura(pagina, "configuracion-marca")
    pagina.locator(".sin-guardar button", has_text="Descartar").click()
    assert pagina.evaluate("() => document.documentElement.style.getPropertyValue('--primario')") == ""
    sesion_navegador.ir(pagina, reverse("configuracion:parametros"))
    if "confirmar" in pagina.url:
        pagina.locator("input[type='password']").fill("Contrasena-de-prueba-2026")
        pagina.locator("form button[type='submit']").first.click()
        pagina.wait_for_load_state("networkidle")
    antes = parametro("orden_reparto").split(",")
    pagina.locator(f".orden-item[data-id='{antes[0]}'] [data-orden-mover='bajar']").click()
    pagina.wait_for_selector(".sin-guardar:not([hidden])")
    sesion_navegador.captura(pagina, "configuracion-orden")
    pagina.locator(".sin-guardar button", has_text="Guardar").click()
    pagina.wait_for_load_state("networkidle")
    assert parametro("orden_reparto").split(",")[:2] == [antes[1], antes[0]]
    sin_errores(sesion_navegador)


def test_abrir_turno_de_fabrica_con_mosaicos_dependencias_y_movimiento_reducido(sesion_navegador):
    datos = preparar(con_turno=False)
    pagina = sesion_navegador.pagina(datos["op"], movimiento="reduce")
    sesion_navegador.ir(pagina, reverse("caja:inicio"))
    pagina.locator("input[name='apertura'][value='cero']").check()
    assert pagina.locator("[data-depende-de='apertura']").is_hidden()
    pagina.locator("input[name='apertura'][value='efectivo']").check()
    assert pagina.locator("[data-depende-de='apertura']").is_visible()
    pagina.evaluate("() => { const b = document.querySelector('.pieza[data-centavos=\"10000\"] .mosaico'); b.click(); b.click(); }")
    pagina.locator(".pieza[data-centavos='5000'] .mosaico").click()
    assert "250.00" in pagina.locator("#fondo-total").inner_text()
    sesion_navegador.captura(pagina, "abrir-turno")
    with pagina.expect_navigation():
        pagina.evaluate("() => { const b = document.querySelector('form[action$=\"/caja/abrir/\"] button[type=submit]'); b.click(); b.click(); b.click(); }")
    pagina.wait_for_load_state("networkidle")
    assert Turno.objects.filter(usuario=datos["op"], estado=Turno.ABIERTO).count() == 1
    assert Turno.objects.get(usuario=datos["op"]).fondo_inicial == 25000
    sesion_navegador.ir(pagina, reverse("cobros:buscar"))
    pagina.locator(".renglon-titular").first.click()
    pagina.wait_for_selector("#panel-cobro [data-cobro-efectivo]")
    pagina.locator(".pieza[data-centavos='100000'] .mosaico").click()
    assert pagina.locator("[data-recibido-cobro]").inner_text().startswith("$1,000.00")
    assert pagina.locator(".vuela").count() == 0
    sin_errores(sesion_navegador)


def test_ventana_angosta_cajon_con_velo_y_filtros_que_reacomodan(sesion_navegador):
    from datetime import timedelta

    from rezagos.models import ReglaRezago

    datos = preparar()
    if not ReglaRezago.objects.filter(activa=True).exists():
        ReglaRezago.objects.create(nombre="Atraso general", texto="Pago atrasado", dias_minimos=5, aviso_inicio=True, marca=True, cobranza=True)
    dario = datos["titulares"][3]
    libro.crear_cargo(dario, ConceptoCobro.objects.filter(activo=True).first(), 50000, hoy_negocio() - timedelta(days=40), Cargo.MANUAL, descripcion="Atrasado")
    pagina = sesion_navegador.pagina(datos["op"], ancho=820, alto=900)
    sesion_navegador.ir(pagina, reverse("cobros:buscar"))
    espera(pagina.locator(".lista-titulares .renglon-titular")).to_have_count(4)
    pagina.locator("a.filtro[data-estado='rezago']").click()
    espera(pagina.locator(".lista-titulares .renglon-titular")).to_have_count(1)
    assert pagina.locator("a.filtro[data-estado='rezago']").get_attribute("aria-pressed") == "true"
    assert "estado=rezago" in pagina.url
    pagina.locator("a.filtro[data-estado='']").click()
    espera(pagina.locator(".lista-titulares .renglon-titular")).to_have_count(4)
    pagina.locator(".renglon-titular").first.click()
    pagina.wait_for_selector("#panel-cobro [data-cobro-efectivo]")
    pagina.wait_for_timeout(400)
    sesion_navegador.captura(pagina, "cajon-angosto")
    caja_panel = pagina.locator("#panel-cobro > .panel").bounding_box()
    assert caja_panel["x"] + caja_panel["width"] <= 821 and caja_panel["x"] >= 300
    assert pagina.locator("#panel-cobro .velo").is_visible()
    pagina.keyboard.press("Escape")
    pagina.wait_for_timeout(400)
    assert "abierta" not in pagina.locator("[data-cobro-rejilla]").get_attribute("class")
    pagina.locator(".renglon-titular").first.click()
    pagina.wait_for_selector("#panel-cobro [data-cobro-efectivo]")
    pagina.mouse.click(40, 600)
    pagina.wait_for_timeout(400)
    assert "abierta" not in pagina.locator("[data-cobro-rejilla]").get_attribute("class")
    sin_errores(sesion_navegador)


def test_soltar_el_archivo_del_banco_en_la_zona(sesion_navegador):
    from .banco_ayudas import cuenta_principal

    correr_asistente("escuela")
    director = nuevo_usuario("director", Rol.objects.get(nombre="Dirección"))
    cuenta_principal()
    pagina = sesion_navegador.pagina(director)
    sesion_navegador.ir(pagina, reverse("conciliacion:importar"))
    if "confirmar" in pagina.url:
        pagina.locator("input[type='password']").fill("Contrasena-de-prueba-2026")
        pagina.locator("form button[type='submit']").first.click()
        pagina.wait_for_load_state("networkidle")
    zona = pagina.locator("[data-zona-soltar]")
    assert zona.is_visible()
    pagina.locator("select[name='cuenta']").select_option(index=1)
    sesion_navegador.captura(pagina, "banco-soltar")
    with pagina.expect_navigation():
        pagina.evaluate("""() => {
            const dt = new DataTransfer();
            dt.items.add(new File(["Fecha,Concepto,Abono,Cargo\\n10/11/2026,PAGO,1850.00,\\n"], "movimientos.csv", { type: "text/csv" }));
            const zona = document.querySelector("[data-zona-soltar]");
            zona.dispatchEvent(new DragEvent("dragover", { dataTransfer: dt, bubbles: true, cancelable: true }));
            zona.dispatchEvent(new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true }));
        }""")
    pagina.wait_for_load_state("networkidle")
    sesion_navegador.captura(pagina, "banco-soltado")
    assert "/banco/importar/" in pagina.url and pagina.url.rstrip("/") != (sesion_navegador.servidor + reverse("conciliacion:importar")).rstrip("/")
    sin_errores(sesion_navegador)
