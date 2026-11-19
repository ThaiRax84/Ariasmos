import re

import pytest
from django.core.cache import cache
from django.urls import reverse

from auditoria.models import Evento
from caja.models import MovimientoPiezas
from caja.servicios import abrir_turno
from caja.models import Caja
from cobros import libro
from cobros.models import Cargo, ConceptoCobro, Pago
from configuracion.models import Parametro
from cuentas.models import PermisoRol
from titulares.models import Agrupacion, Titular
from titulares.servicios import crear_titular

from .conftest import cliente
from .libro_ayudas import preparar_conceptos


def alta(personas, nombre, apellidos="Prueba", **datos):
    from solicitudes import motor

    titular = crear_titular(personas["op"], {"nombre": nombre, "apellidos": apellidos, **datos}, contacto={"nombre": "Resp", "valores": {}}, conceptos=[])
    motor.ejecutar("alta", personas["sup"], titular)
    titular.refresh_from_db()
    return titular


@pytest.fixture
def padron(personas):
    cache.clear()
    preparar_conceptos()
    grupo = Agrupacion.objects.create(nombre="Tercero B")
    ana = alta(personas, "Ana", "Zamora", agrupacion=grupo)
    beto = alta(personas, "Beto", "Alcalá")
    concepto = ConceptoCobro.objects.get(nombre="Inscripción")
    libro.crear_cargo(ana, concepto, 120000, Titular.objects.get(pk=ana.pk).creado.date(), Cargo.MANUAL, usuario=personas["sup"])
    return {"ana": ana, "beto": beto}


@pytest.fixture
def turno(personas):
    return abrir_turno(personas["op"], Caja.objects.filter(activa=True).first(), 37000, piezas={"10000": 2, "5000": 2, "2000": 5, "1000": 5, "500": 4})


def _panel(c, titular, **datos):
    return c.post(reverse("cobros:cobrar", args=[titular.pk]), {"panel": "1", "paso": "panel", **datos})


def test_el_panel_es_la_misma_pantalla_con_la_region_del_panel(personas, padron, turno):
    c = cliente(personas["op"])
    texto = c.get(reverse("cobros:cobrar", args=[padron["ana"].pk]), {"panel": "1"}).content.decode()
    assert 'id="panel-cobro-region"' in texto and "data-cobro-efectivo" in texto and 'name="r_50000"' in texto
    assert 'value="1200.00"' in texto
    lista = c.get(reverse("cobros:buscar")).content.decode()
    assert f'data-abre-panel="{reverse("cobros:cobrar", args=[padron["ana"].pk])}?panel=1"' in lista


def test_el_panel_nunca_lleva_las_existencias_de_la_caja(personas, padron, turno):
    c = cliente(personas["op"])
    respuesta = _panel(c, padron["ana"], importe="1200", r_100000="1", r_50000="1")
    texto = respuesta.content.decode()
    assert "Entrega este cambio, con estas piezas" in texto
    assert "existencia" not in texto.lower() and 'name="c_' in texto
    assert Pago.objects.count() == 0


def test_pago_exacto_en_el_panel_se_registra_con_su_recibo(personas, padron, turno):
    c = cliente(personas["op"])
    respuesta = _panel(c, padron["ana"], importe="1200", r_100000="1", r_10000="2")
    assert respuesta.status_code == 302 and "hecho=" in respuesta.url
    pago = Pago.objects.get()
    assert pago.importe == 120000 and pago.medio == Pago.EFECTIVO
    assert not MovimientoPiezas.objects.filter(pago=pago, origen=MovimientoPiezas.CAMBIO).exists()
    hecho = c.get(respuesta.url).content.decode()
    assert "data-exito" in hecho and str(pago.recibo) in hecho


def test_el_panel_rechaza_piezas_que_no_alcanzan(personas, padron, turno):
    c = cliente(personas["op"])
    texto = _panel(c, padron["ana"], importe="1200", r_50000="1").content.decode()
    assert "no alcanzan" in texto and Pago.objects.count() == 0


def test_el_panel_confirma_con_cambio_igual_que_el_flujo_por_pasos(personas, padron, turno):
    c = cliente(personas["op"])
    texto = _panel(c, padron["ana"], importe="1200", r_100000="1", r_50000="1").content.decode()
    datos = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', texto))
    for nombre in re.findall(r'name="(c_\d+)"', texto):
        valor = re.search(rf'name="{nombre}" value="(\d+)"', texto)
        datos[nombre] = valor.group(1) if valor else "0"
    assert datos["paso"] == "confirmar" and datos["panel"] == "1"
    hecho = c.post(reverse("cobros:cobrar", args=[padron["ana"].pk]), datos)
    assert hecho.status_code == 302 and "hecho=" in hecho.url
    pago = Pago.objects.get()
    cambio = sum(m.denominacion * -m.piezas for m in MovimientoPiezas.objects.filter(pago=pago, origen=MovimientoPiezas.CAMBIO))
    assert cambio == 30000
    otra = c.post(reverse("cobros:cobrar", args=[padron["ana"].pk]), datos)
    assert otra.status_code == 302 and Pago.objects.count() == 1


def test_el_recibo_ajeno_no_se_muestra_en_otro_panel(personas, padron, turno):
    c = cliente(personas["op"])
    _panel(c, padron["ana"], importe="1200", r_100000="1", r_10000="2")
    recibo = Pago.objects.get().recibo
    respuesta = c.get(reverse("cobros:cobrar", args=[padron["beto"].pk]), {"panel": "1", "hecho": recibo.pk})
    assert respuesta.status_code == 302 and "hecho" not in respuesta.url


def test_el_flujo_por_pasos_sin_js_sigue_igual(personas, padron, turno):
    c = cliente(personas["op"])
    texto = c.post(reverse("cobros:cobrar", args=[padron["ana"].pk]), {"importe": "1200"}).content.decode()
    assert 'name="paso" value="cambio"' in texto and "panel-cobro-region" not in texto


def test_ir_exige_sesion_y_equipo_aprobado(personas, padron):
    respuesta = cliente().get(reverse("ir"), {"q": "ana"})
    assert respuesta.status_code == 302
    from cuentas.models import Dispositivo

    from .conftest import equipo_aprobado

    credencial = equipo_aprobado()
    c = cliente(personas["op"], credencial=credencial)
    assert c.get(reverse("ir"), {"q": "ana"}).status_code == 200
    Dispositivo.objects.update(estado=Dispositivo.PENDIENTE)
    respuesta = c.get(reverse("ir"), {"q": "ana"})
    assert respuesta.status_code in (302, 403) and b"Ana" not in respuesta.content


def test_ir_devuelve_personas_pantallas_y_acciones_segun_permisos(personas, padron):
    datos = cliente(personas["op"]).get(reverse("ir"), {"q": "ana"}).json()["resultados"]
    personas_encontradas = [r for r in datos if r["tipo"] == "persona"]
    assert [p["titulo"] for p in personas_encontradas] == ["Ana Zamora"]
    assert personas_encontradas[0]["url"].endswith(f"?abrir={padron['ana'].pk}")
    pantallas = cliente(personas["op"]).get(reverse("ir"), {"q": ""}).json()["resultados"]
    urls = {r["url"] for r in pantallas}
    assert reverse("configuracion:indice") not in urls and reverse("usuarios") not in urls
    assert reverse("configuracion:indice") in {r["url"] for r in cliente(personas["dir"]).get(reverse("ir"), {"q": ""}).json()["resultados"]}


def test_ir_solo_da_el_adeudo_a_quien_ve_saldos(personas, padron):
    con = cliente(personas["sup"]).get(reverse("ir"), {"q": "zamora"}).json()["resultados"]
    assert con[0]["lado"] == "$1,200.00 MXN" or "1,200.00" in con[0]["lado"]
    PermisoRol.objects.filter(rol=personas["op"].rol, permiso="ver_titulares").delete()
    sin = cliente(personas["op"]).get(reverse("ir"), {"q": "zamora"}).json()["resultados"]
    assert sin and all("lado" not in r for r in sin)
    assert "1,200" not in cliente(personas["op"]).get(reverse("ir"), {"q": "zamora"}).content.decode()


def test_ir_tiene_tope_y_limite_de_frecuencia_y_no_guarda_lo_buscado(personas, padron):
    for numero in range(12):
        alta(personas, f"Zeta{numero:02d}", "Repetida")
    antes = Evento.objects.count()
    c = cliente(personas["op"])
    datos = c.get(reverse("ir"), {"q": "repetida"}).json()["resultados"]
    assert len([r for r in datos if r["tipo"] == "persona"]) == 7 and len(datos) <= 40
    assert not Evento.objects.filter(pk__gt=0).exclude(pk__lte=antes).filter(datos__icontains="repetida").exists()
    codigos = [c.get(reverse("ir"), {"q": "x"}).status_code for _ in range(130)]
    assert 429 in codigos
    assert c.get(reverse("ir"), {"q": "y" * 500}).status_code in (200, 429)


def test_pulso_solo_da_contadores_y_sube_en_la_misma_transaccion(personas, padron, turno):
    from django.db import transaction

    from vivo import pulso

    c = cliente(personas["op"])
    antes = c.get(reverse("pulso")).json()["t"]
    assert set(antes) == {"cobros", "transferencias", "titulares", "solicitudes", "caja", "banco", "inventario"}
    assert all(isinstance(v, int) for v in antes.values())
    try:
        with transaction.atomic():
            libro.registrar_pago(padron["ana"], 1000, Pago.EFECTIVO, personas["op"], turno=turno, piezas={"recibidas": {"1000": 1}, "cambio": {}})
            assert pulso.valores()["cobros"] > antes["cobros"]
            raise RuntimeError
    except RuntimeError:
        pass
    assert pulso.valores()["cobros"] == antes["cobros"]
    libro.registrar_pago(padron["ana"], 1000, Pago.EFECTIVO, personas["op"], turno=turno, piezas={"recibidas": {"1000": 1}, "cambio": {}})
    despues = c.get(reverse("pulso")).json()["t"]
    assert despues["cobros"] > antes["cobros"]
    assert b"Ana" not in c.get(reverse("pulso")).content


def test_pulso_pide_sesion_y_equipo_y_tiene_limite(personas):
    from cuentas.models import Dispositivo

    from .conftest import equipo_aprobado

    cache.clear()
    assert cliente().get(reverse("pulso")).status_code == 302
    credencial = equipo_aprobado()
    c = cliente(personas["op"], credencial=credencial)
    codigos = [c.get(reverse("pulso")).status_code for _ in range(45)]
    assert codigos[0] == 200 and 429 in codigos
    Dispositivo.objects.update(estado=Dispositivo.PENDIENTE)
    assert c.get(reverse("pulso")).status_code in (302, 403)


def test_pulso_y_las_recargas_en_vivo_no_cuentan_como_actividad(personas):
    import time

    c = cliente(personas["op"])
    c.get(reverse("inicio"))
    sesion = c.session
    sesion["ultima_actividad"] = time.time() - 60
    sesion.save()
    marca = c.session["ultima_actividad"]
    c.get(reverse("pulso"))
    c.get(reverse("inicio"), HTTP_X_ARIASMOS_VIVO="1")
    assert c.session["ultima_actividad"] == marca
    c.get(reverse("inicio"))
    assert c.session["ultima_actividad"] > marca


def test_lo_ultimo_que_entro_respeta_permisos_e_importes(personas, padron, turno):
    _panel(cliente(personas["op"]), padron["ana"], importe="1200", r_100000="1", r_10000="2")
    con = cliente(personas["sup"]).get(reverse("ultimo")).content.decode()
    assert "Ana Zamora" in con and "$1,200.00" in con
    PermisoRol.objects.filter(rol=personas["op"].rol, permiso="ver_titulares").delete()
    propio = cliente(personas["op"]).get(reverse("ultimo")).content.decode()
    assert "Ana Zamora" in propio
    nadie = cliente(personas["op2"]).get(reverse("ultimo")).content.decode()
    assert "Ana Zamora" not in nadie and "1,200" not in nadie


@pytest.fixture
def con_origen(settings):
    from banco.models import TopeDiarioBanco

    from . import origen_pruebas
    from .banco_ayudas import cuenta_principal

    settings.ORIGENES_TRANSFERENCIA = ["pruebas.origen_pruebas.OrigenDePruebas"]
    cuenta_principal()
    for dia in range(7):
        TopeDiarioBanco.objects.update_or_create(dia=dia, defaults={"importe": 10 ** 9})
    Parametro.objects.update_or_create(clave="tope_aplicado_sin_respaldo", defaults={"valor": str(10 ** 9)})
    origen_pruebas.PENDIENTES.clear()
    return origen_pruebas.PENDIENTES


def _aviso(titular, folio, importe=120000):
    from banco.llegadas import Aviso
    from configuracion.models import hoy_negocio

    return Aviso(folio=folio, fecha=hoy_negocio(), importe=importe, referencia=titular.referencia_bancaria, concepto="PAGO")


def test_la_puerta_de_llegada_aplica_con_las_reglas_del_banco_y_avisa(personas, padron, con_origen):
    from banco import llegadas
    from banco.models import Importacion, MovimientoBancario
    from vivo import pulso

    antes = pulso.valores()["transferencias"]
    c = cliente(personas["op"])
    espera = c.get(reverse("cobros:cobrar", args=[padron["ana"].pk]), {"panel": "1", "metodo": "transferencia", "desde": "0"}).content.decode()
    assert "Esperando la transferencia" in espera and "data-exito" not in espera
    con_origen.append(_aviso(padron["ana"], "F-1"))
    llegadas.consultar_todos()
    pago = Pago.objects.get(medio=Pago.BANCO)
    assert pago.titular_id == padron["ana"].pk and pago.importe == 120000
    assert Importacion.objects.get().origen == Importacion.AVISO
    assert pulso.valores()["transferencias"] == antes + 1
    assert Evento.objects.filter(accion="importacion_bancaria").exists()
    hecho = c.get(reverse("cobros:cobrar", args=[padron["ana"].pk]), {"panel": "1", "metodo": "transferencia", "desde": "0"})
    assert hecho.status_code == 200 and "Transferencia recibida y aplicada" in hecho.content.decode()
    con_origen.append(_aviso(padron["ana"], "F-1"))
    llegadas.consultar_todos()
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 1


def test_la_puerta_de_llegada_respeta_topes_y_retenciones(personas, padron, con_origen):
    from banco import llegadas
    from banco.models import MovimientoBancario, TopeDiarioBanco

    Parametro.objects.update_or_create(clave="tope_aplicado_sin_respaldo", defaults={"valor": "1000"})
    con_origen.append(_aviso(padron["ana"], "F-0"))
    llegadas.consultar_todos()
    assert "tope_exposicion" in MovimientoBancario.objects.get(folio="F-0").retencion
    Parametro.objects.update_or_create(clave="tope_aplicado_sin_respaldo", defaults={"valor": str(10 ** 9)})
    TopeDiarioBanco.objects.update(importe=1000)
    con_origen.append(_aviso(padron["ana"], "F-2"))
    llegadas.consultar_todos()
    assert not Pago.objects.filter(medio=Pago.BANCO).exists()
    assert "tope_dia" in MovimientoBancario.objects.get(folio="F-2").retencion
    con_origen.append(_aviso(padron["beto"], "F-3", importe=5000))
    TopeDiarioBanco.objects.update(importe=10 ** 9)
    llegadas.consultar_todos()
    assert not Pago.objects.filter(medio=Pago.BANCO, titular=padron["beto"]).exists()
    assert "excede_adeudo" in MovimientoBancario.objects.get(folio="F-3").retencion


def test_la_puerta_de_llegada_rechaza_avisos_mal_formados(personas, padron, con_origen):
    from banco import llegadas
    from banco.llegadas import Aviso, ErrorLlegada
    from configuracion.models import hoy_negocio

    con_origen.append(Aviso(folio="", fecha=hoy_negocio(), importe=100))
    with pytest.raises(ErrorLlegada):
        llegadas.consultar_todos()
    con_origen.clear()
    con_origen.append(Aviso(folio="Z", fecha=hoy_negocio(), importe=-5))
    with pytest.raises(ErrorLlegada):
        llegadas.consultar_todos()
    assert not Pago.objects.filter(medio=Pago.BANCO).exists()


def test_sin_cuenta_del_negocio_el_panel_lo_dice_en_palabras_llanas(personas, padron, turno):
    texto = cliente(personas["op"]).get(reverse("cobros:cobrar", args=[padron["ana"].pk]), {"panel": "1"}).content.decode()
    assert "Todavía no hay una cuenta del negocio para recibir transferencias" in texto
    assert reverse("banco:nueva") not in texto
    assert reverse("banco:nueva") in cliente(personas["dir"]).get(reverse("cobros:cobrar", args=[padron["ana"].pk]), {"panel": "1"}).content.decode()


def test_aplicar_varios_depositos_con_las_mismas_reglas_que_uno(personas, padron, con_origen):
    from banco import llegadas
    from banco.models import MovimientoBancario

    Parametro.objects.update_or_create(clave="tope_aplicado_sin_respaldo", defaults={"valor": "1"})
    con_origen.extend([_aviso(padron["ana"], "V-1"), _aviso(padron["beto"], "V-2", importe=5000)])
    llegadas.consultar_todos()
    assert MovimientoBancario.objects.filter(estado=MovimientoBancario.POR_IDENTIFICAR).count() == 2
    texto = cliente(personas["sup"]).get(reverse("conciliacion:cola")).content.decode()
    assert "¿De quién es?" in texto and "¿Qué tan seguro?" in texto and "Ana Zamora" in texto
    ids = list(MovimientoBancario.objects.values_list("pk", flat=True))
    assert cliente(personas["op"]).post(reverse("conciliacion:aplicar_varios"), {"movimiento": ids}).status_code == 403
    respuesta = cliente(personas["dir"]).post(reverse("conciliacion:aplicar_varios"), {"movimiento": ids})
    assert respuesta.status_code == 302
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 2
    assert Evento.objects.filter(accion="movimiento_confirmado").count() == 2


@pytest.fixture
def con_rezago(personas, padron):
    from datetime import timedelta

    from configuracion.models import hoy_negocio
    from rezagos.models import ReglaRezago

    if not ReglaRezago.objects.filter(activa=True).exists():
        ReglaRezago.objects.create(nombre="Atraso general", texto="Pago atrasado", dias_minimos=5, aviso_inicio=True, marca=True, cobranza=True)
    carla = alta(personas, "Carla", "Atrasada")
    concepto = ConceptoCobro.objects.get(nombre="Inscripción")
    libro.crear_cargo(carla, concepto, 90000, hoy_negocio() - timedelta(days=45), Cargo.MANUAL, usuario=personas["sup"])
    return carla


def test_filtros_de_cobrar_con_cuenta_y_permisos(personas, padron, con_rezago):
    c = cliente(personas["sup"])
    texto = c.get(reverse("cobros:buscar")).content.decode()
    assert 'data-estado=""' in texto and 'data-estado="adeudo"' in texto and 'data-estado="rezago"' in texto
    adeudo = c.get(reverse("cobros:buscar"), {"estado": "adeudo"}).content.decode()
    assert "Ana Zamora" in adeudo and "Carla Atrasada" in adeudo and "Beto Alcalá" not in adeudo
    rezago = c.get(reverse("cobros:buscar"), {"estado": "rezago"}).content.decode()
    assert "Carla Atrasada" in rezago and "Ana Zamora" not in rezago
    PermisoRol.objects.filter(rol=personas["op"].rol, permiso="ver_titulares").delete()
    sin = cliente(personas["op"])
    texto = sin.get(reverse("cobros:buscar")).content.decode()
    assert 'data-estado="adeudo"' not in texto and 'data-estado="rezago"' in texto
    ignorado = sin.get(reverse("cobros:buscar"), {"estado": "adeudo"}).content.decode()
    assert "Beto Alcalá" in ignorado and "Ana Zamora" in ignorado


def test_filtros_de_cobrar_sin_una_consulta_por_renglon(personas, padron, con_rezago):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    c = cliente(personas["sup"])
    c.get(reverse("cobros:buscar"), {"estado": "adeudo"})
    with CaptureQueriesContext(connection) as pocas:
        c.get(reverse("cobros:buscar"), {"estado": "adeudo"})
    for numero in range(15):
        titular = alta(personas, f"Extra{numero:02d}", "Deudor")
        libro.crear_cargo(titular, ConceptoCobro.objects.get(nombre="Inscripción"), 1000, Titular.objects.get(pk=titular.pk).creado.date(), Cargo.MANUAL, usuario=personas["sup"])
    with CaptureQueriesContext(connection) as muchas:
        c.get(reverse("cobros:buscar"), {"estado": "adeudo"})
    assert len(muchas.captured_queries) <= len(pocas.captured_queries) + 2


def test_paleta_vacia_muestra_tres_rezagados_con_adeudo_segun_permiso(personas, padron, con_rezago):
    datos = cliente(personas["sup"]).get(reverse("ir"), {"q": ""}).json()["resultados"]
    rezagados = [r for r in datos if r["grupo"] == "Rezagados"]
    assert [r["titulo"] for r in rezagados] == ["Carla Atrasada"] and "900.00" in rezagados[0]["lado"]
    PermisoRol.objects.filter(rol=personas["op"].rol, permiso="ver_titulares").delete()
    sin = cliente(personas["op"]).get(reverse("ir"), {"q": ""}).json()["resultados"]
    assert [r["titulo"] for r in sin if r["grupo"] == "Rezagados"] == ["Carla Atrasada"]
    assert all("lado" not in r for r in sin)


def test_billete_o_moneda_es_dato_de_cada_denominacion(personas, turno, padron):
    from caja.models import Denominacion

    from configuracion import plantillas

    for nombre in ("escuela", "academia", "gimnasio", "rentas", "servicios", "generico"):
        tipos = {d["centavos"]: d["tipo"] for d in plantillas.leer(nombre)["denominaciones"]}
        assert "moneda" in tipos.values() and "billete" in tipos.values()
    Denominacion.objects.filter(valor=1000).update(tipo=Denominacion.MONEDA)
    texto = cliente(personas["op"]).get(reverse("cobros:cobrar", args=[padron["ana"].pk]), {"panel": "1"}).content.decode()
    assert 'data-centavos="1000" data-tipo="moneda" data-rotulo="moneda"' in texto
    assert 'data-centavos="50000" data-tipo="billete" data-rotulo="billete"' in texto
    d = cliente(personas["dir"])
    pk = Denominacion.objects.get(valor=1000).pk
    pagina = d.get(reverse("configuracion:catalogo_editar", args=["denominaciones", pk])).content.decode()
    assert "¿Es billete o moneda?" in pagina


def test_la_migracion_deja_billete_en_lo_que_ya_existe():
    import importlib

    from caja.models import Denominacion

    campo = Denominacion._meta.get_field("tipo")
    assert campo.default == Denominacion.BILLETE
    migracion = importlib.import_module("caja.migrations.0006_tipo_denominacion")
    assert migracion.Migration.operations[0].field.default == "billete"
