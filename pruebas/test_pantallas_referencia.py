import re
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.db import connection
from django.db.models import QuerySet
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from caja import retiros
from caja import servicios as caja
from caja.models import MotivoRetiro, RetiroCaja, Traslado
from cobros import libro
from cobros.models import Cargo, ConceptoCobro, Pago
from configuracion.models import Negocio, Parametro
from cuentas.models import Usuario
from inventario import servicios as inventario
from inventario.models import MAXIMO_CANTIDAD, Articulo, Conteo, Venta
from proyecto import tablero
from solicitudes import motor

from .conftest import cliente, nuevo_usuario
from .libro_ayudas import preparar_conceptos, titular_activo, turno_de

CSS_EN_LINEA = re.compile(r"<style|\sstyle=|\son[a-z]+=|<script(?![^>]*\ssrc=)", re.I)


def fijar(clave, valor):
    Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})


@pytest.fixture
def tienda(personas):
    cache.clear()
    preparar_conceptos()
    fijar("modulo_inventario", 1)
    libros = ConceptoCobro.objects.get(nombre="Libros")
    libro_a = Articulo.objects.create(clave="LIB-A", nombre="Libro A", precio=35000, concepto=libros)
    cuaderno = Articulo.objects.create(clave="CUA-1", nombre="Cuaderno", precio=5000, concepto=libros)
    viejo = Articulo.objects.create(clave="VIE-1", nombre="Viejo", precio=100, concepto=libros, activo=False)
    conteo = inventario.subir_conteo({libro_a.pk: 2, cuaderno.pk: 20}, personas["op"], Conteo.PANTALLA)
    motor.aprobar(conteo.solicitud, personas["sup"])
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    return personas, ana, libro_a, cuaderno, viejo


def test_venta_con_una_cantidad_por_articulo_y_control(tienda):
    personas, ana, libro_a, cuaderno, viejo = tienda
    pagina = cliente(personas["op"]).get(reverse("inventario:vender_titular", args=[ana.pk])).content.decode()
    assert "Inventario · Vender" in pagina and ana.nombre_completo in pagina and ana.matricula_formateada in pagina
    assert f'name="cantidad_{libro_a.pk}"' in pagina and f'name="cantidad_{cuaderno.pk}"' in pagina and f"cantidad_{viejo.pk}" not in pagina
    assert f'max="{MAXIMO_CANTIDAD}"' in pagina and 'max="2"' not in pagina
    assert re.search(r'<button[^>]*data-agregar[^>]*hidden', pagina) and re.search(r'<div[^>]*data-buscar-articulo[^>]*hidden', pagina)
    assert "El total se calcula al continuar" in pagina and "js/venta.js" in pagina
    assert "Sigue al cobro y se da recibo" in pagina and "Se cobra después, junto con lo demás" in pagina
    assert 'data-boton="Continuar al cobro"' in pagina and 'data-boton="Registrar la venta"' in pagina
    assert reverse("inventario:vender") in pagina and reverse("inventario:vender_publico") in pagina and "Sin matrícula" in pagina
    assert f'data-precio="{libro_a.precio}"' in pagina
    assert not CSS_EN_LINEA.search(pagina)


def test_venta_arma_renglones_con_cantidades_mayores_a_cero(tienda):
    personas, ana, libro_a, cuaderno, viejo = tienda
    respuesta = cliente(personas["op"]).post(reverse("inventario:vender_titular", args=[ana.pk]), {f"cantidad_{libro_a.pk}": "5", f"cantidad_{cuaderno.pk}": "0", "modo": "adeudo"})
    venta = Venta.objects.get()
    assert respuesta.url == reverse("inventario:venta", args=[venta.pk])
    assert list(venta.renglones.values_list("articulo__clave", "cantidad", "sin_existencia")) == [("LIB-A", 5, True)]


@pytest.mark.parametrize("extra", ["desconocido", "inactivo", "texto"])
def test_venta_rechaza_articulos_desconocidos_o_inactivos(tienda, extra):
    personas, ana, libro_a, cuaderno, viejo = tienda
    nombre = {"desconocido": "cantidad_999999", "inactivo": f"cantidad_{viejo.pk}", "texto": "cantidad_x"}[extra]
    respuesta = cliente(personas["op"]).post(reverse("inventario:vender_titular", args=[ana.pk]), {f"cantidad_{cuaderno.pk}": "3", nombre: "1", "modo": "adeudo"})
    assert respuesta.status_code == 200 and not Venta.objects.exists()
    texto = respuesta.content.decode()
    assert "no existe o no está activo" in texto
    assert re.search(rf'name="cantidad_{cuaderno.pk}"[^>]*value="3"|value="3"[^>]*name="cantidad_{cuaderno.pk}"', texto)


def test_venta_con_error_conserva_las_cantidades(tienda):
    personas, ana, libro_a, cuaderno, viejo = tienda
    respuesta = cliente(personas["op"]).post(reverse("inventario:vender_titular", args=[ana.pk]), {f"cantidad_{libro_a.pk}": "4", f"cantidad_{cuaderno.pk}": "-2", "modo": "ahora"})
    texto = respuesta.content.decode()
    assert respuesta.status_code == 200 and not Venta.objects.exists()
    assert re.search(rf'value="4"[^>]*name="cantidad_{libro_a.pk}"|name="cantidad_{libro_a.pk}"[^>]*value="4"', texto)
    assert re.search(rf'value="-2"[^>]*name="cantidad_{cuaderno.pk}"|name="cantidad_{cuaderno.pk}"[^>]*value="-2"', texto)
    vacia = cliente(personas["op"]).post(reverse("inventario:vender_titular", args=[ana.pk]), {f"cantidad_{libro_a.pk}": "", "modo": "ahora"})
    assert "Agrega al menos un artículo" in vacia.content.decode()


def test_venta_publico_con_el_mismo_catalogo(tienda):
    personas, ana, libro_a, cuaderno, viejo = tienda
    c = cliente(personas["op"])
    turno = turno_de(personas["op"])
    pantalla = c.get(reverse("inventario:vender_publico")).content.decode()
    assert f'name="cantidad_{cuaderno.pk}"' in pantalla and 'name="modo"' not in pantalla and 'data-texto="Continuar al cobro"' in pantalla
    assert 'aria-current="page">Sin matrícula' in pantalla
    previa = c.post(reverse("inventario:vender_publico"), {f"cantidad_{cuaderno.pk}": "3", f"cantidad_{libro_a.pk}": "0"})
    texto = previa.content.decode()
    assert previa.context["total"] == 15000 and f'name="cantidad_{cuaderno.pk}" value="3"' in texto and f'name="cantidad_{libro_a.pk}"' not in texto
    respuesta = c.post(reverse("inventario:vender_publico"), {f"cantidad_{cuaderno.pk}": "3", "paso": "confirmar", "ficha": previa.context["ficha"]})
    venta = Venta.objects.get()
    assert venta.pago.importe == 15000 and venta.pago.turno == turno and respuesta.url == reverse("cobros:recibo", args=[venta.pago.recibo.pk])
    ajeno = c.post(reverse("inventario:vender_publico"), {f"cantidad_{viejo.pk}": "1", "paso": "confirmar", "ficha": "f" * 30})
    assert ajeno.status_code == 200 and Venta.objects.count() == 1


@pytest.fixture
def movimientos(personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    beto = titular_activo(personas["op"], personas["sup"], "Beto")
    return personas, ana, beto


def test_cobrado_del_mes_solo_dinero_que_entro(movimientos):
    personas, ana, beto = movimientos
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 30000, Pago.EFECTIVO, personas["op"], turno=turno)
    libro.registrar_pago(beto, 70000, Pago.BANCO, personas["sup"])
    revertido = libro.registrar_pago(beto, 99900, Pago.BANCO, personas["sup"])
    libro.revertir_pago(revertido, "error de captura", personas["dir"])
    libro.registrar_pago(ana, 5000, Pago.EFECTIVO, personas["op"], turno=turno, fecha=tablero.mes_en_curso()[0] - timedelta(minutes=1))
    libro.registrar_pago(ana, 4000, Pago.DEVOLUCION, personas["op"])
    datos = tablero.cobrado_mes()
    assert (datos["total"], datos["efectivo"], datos["banco"]) == (100000, 30000, 70000)
    assert (datos["porcentaje_efectivo"], datos["porcentaje_banco"]) == (30, 70)


def test_por_cobrar_vencido_sin_la_cuenta_interna(movimientos):
    personas, ana, beto = movimientos
    hoy = timezone.localdate()
    libros = ConceptoCobro.objects.get(nombre="Libros")
    libro.crear_cargo(ana, libros, 40000, hoy - timedelta(days=3), Cargo.MANUAL, usuario=personas["sup"])
    libro.crear_cargo(beto, libros, 25000, hoy - timedelta(days=1), Cargo.MANUAL, usuario=personas["sup"])
    libro.crear_cargo(beto, libros, 99000, hoy, Cargo.MANUAL, usuario=personas["sup"])
    vencidos = list(libro.con_saldo(Cargo.objects.filter(vencimiento__lt=hoy, titular__interno=False)).filter(saldo__gt=0))
    esperado = sum(c.saldo for c in vencidos)
    datos = tablero.por_cobrar_vencido(hoy)
    assert esperado >= 65000 and datos["titulares"] == 2
    assert datos["total"] == esperado and datos["titulares"] == len({c.titular_id for c in vencidos})
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 10000, Pago.EFECTIVO, personas["op"], turno=turno)
    assert tablero.por_cobrar_vencido(hoy)["total"] == esperado - 10000
    publico = inventario.cuenta_publico(personas["op"])
    libro.crear_cargo(publico, libros, 7000, hoy - timedelta(days=2), Cargo.MANUAL, usuario=personas["sup"], permitir_interno=True)
    assert publico.interno and tablero.por_cobrar_vencido(hoy)["total"] == esperado - 10000


def test_custodia_agregada_coincide_con_el_servicio(movimientos):
    personas, ana, beto = movimientos
    fijar("tope_retiro_individual", 1000000)
    fijar("tope_retiros_periodo", 10000000)
    fijar("maximo_retiros_periodo", 50)
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 200000, Pago.EFECTIVO, personas["op"], turno=turno)
    assert retiros.registrar_retiro(personas["op"], 3000, MotivoRetiro.objects.first()).retiro is not None
    turno_sup = turno_de(personas["sup"], "Caja 2")
    libro.registrar_pago(beto, 50000, Pago.EFECTIVO, personas["sup"], turno=turno_sup)
    agregadas = tablero.custodias()
    for usuario in Usuario.objects.all():
        assert agregadas.get(usuario.pk, 0) == caja.custodia(usuario), usuario
    assert tablero.efectivo_en_custodia(personas["dir"]) == {"total": 197000 + 50000, "personas": 2}
    assert tablero.efectivo_en_custodia(personas["sup"]) == {"total": 197000, "personas": 1}


def test_retiros_de_la_semana(movimientos):
    personas, ana, beto = movimientos
    fijar("tope_retiro_individual", 1000000)
    fijar("tope_retiros_periodo", 10000000)
    fijar("maximo_retiros_periodo", 50)
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 200000, Pago.EFECTIVO, personas["op"], turno=turno)
    motivo = MotivoRetiro.objects.first()
    retiros.registrar_retiro(personas["op"], 1000, motivo)
    retiros.registrar_retiro(personas["op"], 2500, motivo)
    viejo = retiros.registrar_retiro(personas["op"], 7000, motivo).retiro
    QuerySet.update(RetiroCaja.objects.filter(pk=viejo.pk), creado=retiros.periodo(None, "semana")[0] - timedelta(minutes=1))
    assert tablero.retiros_semana() == {"total": 3500, "cantidad": 2, "sin_comprobante": 2}


def _cifras(usuario):
    return {c["clave"]: c for c in tablero.cifras(usuario)}


def test_cada_cuadro_con_su_permiso_y_perfiles(movimientos):
    personas, ana, beto = movimientos
    assert tablero.perfil(personas["op"]) == tablero.RECEPCION and tablero.cifras(personas["op"]) == []
    assert tablero.perfil(personas["sup"]) == tablero.COORDINACION
    assert set(_cifras(personas["sup"])) == {"cobrado_hoy", "efectivo_sin_entregar", "banco_por_identificar", "corte_diario"}
    assert tablero.perfil(personas["dir"]) == tablero.DIRECCION
    assert list(_cifras(personas["dir"])) == ["cobrado_mes", "por_cobrar_vencido", "efectivo_custodia", "retiros_semana"]
    rol = personas["dir"].rol
    for permiso, clave in (("ver_cortes", "cobrado_mes"), ("ver_titulares", "por_cobrar_vencido"), ("recibir_efectivo", "efectivo_custodia"), ("revisar_retiros", "retiros_semana")):
        rol.asignaciones.filter(permiso=permiso).delete()
        cache.clear()
        usuario = Usuario.objects.get(pk=personas["dir"].pk)
        assert clave not in _cifras(usuario), permiso


def test_arqueo_ciego_en_el_tablero(movimientos):
    personas, ana, beto = movimientos
    turno = turno_de(personas["dir"])
    libro.registrar_pago(ana, 123456, Pago.EFECTIVO, personas["dir"], turno=turno)
    cifras = _cifras(personas["dir"])
    assert cifras["cobrado_mes"]["oculta"] and cifras["efectivo_custodia"]["oculta"] and cifras["cobrado_mes"]["importe"] is None
    pagina = cliente(personas["dir"]).get(reverse("inicio")).content.decode()
    assert pagina.count("Se muestra al cerrar tu turno") == 2 and "1,234.56" not in pagina
    sup = _cifras(personas["sup"])
    assert not sup["efectivo_sin_entregar"]["oculta"] and sup["efectivo_sin_entregar"]["importe"] == 123456
    turno_de(personas["sup"], "Caja 2")
    sup = _cifras(personas["sup"])
    assert sup["cobrado_hoy"]["oculta"] and sup["efectivo_sin_entregar"]["oculta"]
    assert "1,234.56" not in cliente(personas["sup"]).get(reverse("inicio")).content.decode()


def test_el_tablero_no_hace_una_consulta_por_renglon(movimientos):
    personas, ana, beto = movimientos
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 1000, Pago.EFECTIVO, personas["op"], turno=turno)
    tablero.cifras(personas["dir"])
    with CaptureQueriesContext(connection) as pocas:
        tablero.cifras(personas["dir"])
    for numero in range(6):
        otro = titular_activo(personas["op"], personas["sup"], f"Otro{numero}")
        libro.registrar_pago(otro, 1000, Pago.EFECTIVO, personas["op"], turno=turno)
        libro.registrar_pago(otro, 2000, Pago.BANCO, personas["sup"])
    otra = nuevo_usuario("operacion3", personas["op"].rol)
    libro.registrar_pago(beto, 1000, Pago.EFECTIVO, otra, turno=turno_de(otra, "Caja 3"))
    tablero.cifras(personas["dir"])
    with CaptureQueriesContext(connection) as muchas:
        tablero.cifras(personas["dir"])
    assert len(muchas) == len(pocas)


def test_inicio_de_recepcion_solo_cuenta_los_cobros(movimientos):
    personas, ana, beto = movimientos
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 98765, Pago.EFECTIVO, personas["op"], turno=turno)
    pagina = cliente(personas["op"]).get(reverse("inicio")).content.decode()
    assert "1 cobro · desde" in pagina and "987.65" not in pagina and "data-cifra" not in pagina
    assert 'aria-label="Accesos rápidos"' in pagina and 'id="buscar-inicio"' in pagina


class Consulta(list):
    def filter(self, *args, **kwargs):
        return self

    exclude = order_by = select_related = filter

    def count(self):
        return len(self)

    def exists(self):
        return bool(self)

    def first(self):
        return self[0] if self else None


class Falso(SimpleNamespace):
    def __str__(self):
        return getattr(self, "texto", "X")


ORIGINALES = {
    "bitacora_no_integra", "deposito_sin_conciliar", "efectivo_sin_trasladar", "entrega_sin_confirmar", "diferencia_arqueo", "recibo_cancelado",
    "retiros_cerca_del_tope", "retiro_sin_comprobante", "retiro_sin_revisar", "efectivo_sobre_maximo", "importacion_retenida", "pago_sin_respaldo",
    "pago_sin_estado", "carpeta_vigilada", "importacion_por_revisar", "inventario_bajo_minimo", "inventario_existencia_baja", "inventario_por_revisar",
    "inventario_conteo_viejo", "banco", "entregas_por_confirmar", "corte_diario_pendiente", "clave_recuperacion", "respaldos", "entregas_cortes",
    "corte_mayor_borrador", "faltan_denominaciones", "falta_cuenta", "codigo_autorizacion", "certificado_por_vencer",
}


@pytest.fixture
def todos_los_avisos(personas, monkeypatch):
    ahora = timezone.now()
    hoy = timezone.localdate()
    persona = Falso(texto="Persona Falsa")
    pago = Falso(pk=1, importe=1000, titular=Falso(nombre_completo="Titular Falso"), recibo="A-1", reversion=Falso(motivo="error"))
    importacion = Falso(pk=1, nombre_archivo="estado.pdf", creada=ahora, retenidos=2, monto_retenido=5000, importo="Persona Falsa", pagos=1, monto=1000, aplicados=3, retenida=True, liberada_en=None, get_continuidad_display=lambda: "Con hueco")
    retiro = Falso(pk=1, texto="R-1", importe=1000, registrado_por=persona, motivo="Insumos", motivo_sin_comprobante="se perdió", creado=ahora - timedelta(days=9))
    monkeypatch.setattr(tablero, "ultima_verificacion", lambda: Falso(valida=False, motivo="cadena", momento=ahora, numero=7))
    monkeypatch.setattr(tablero, "alertas_caja", lambda u: {
        "depositos_sin_conciliar": [Falso(importe=1000, origen=persona, creado=ahora, cuenta_bancaria="Cuenta", referencia="REF")],
        "sin_trasladar": [{"usuario": persona, "custodia": 1000, "desde": ahora}],
        "entregas_pendientes": [Falso(importe=1000, origen=persona, destino=persona)],
        "diferencias": [Falso(diferencia=-5000, turno=Falso(caja="Caja 2", usuario=persona), creado=ahora, nota="faltó")],
        "recibos_cancelados": [Falso(pk=1, texto="A-1", pago=pago)],
    })
    monkeypatch.setattr(retiros, "avisos", lambda u: {
        "cerca_del_tope": [{"caja": "Caja 1", "tope": "importe", "usado": 800, "limite": 1000}],
        "sin_comprobante": [retiro],
        "por_revisar_viejos": [Falso(**{**retiro.__dict__, "pk": 2})],
        "sobre_maximo": [Falso(caja="Caja 1", usuario=persona)],
    })
    from banco import conciliacion
    monkeypatch.setattr(conciliacion, "con_retenidos", lambda: Consulta([importacion]))
    monkeypatch.setattr(conciliacion, "sin_respaldo_vigentes", lambda: Consulta([Falso(fecha=hoy, importe=1000, pago=pago)]))
    monkeypatch.setattr(conciliacion, "antiguos_sin_respaldo", lambda: Consulta([Falso(fecha=hoy, importe=1000, pago=pago)]))
    monkeypatch.setattr(conciliacion, "pendientes_de_revision", lambda: Consulta([importacion]))
    falsa_importacion = Falso(CARPETA="carpeta", objects=Falso(filter=lambda **k: Consulta([importacion]), order_by=lambda *a: Consulta([importacion])))
    monkeypatch.setattr(tablero, "Importacion", falsa_importacion)
    articulo = Falso(texto="LIB-A · Libro A", minimo=3)
    monkeypatch.setattr(inventario, "avisos", lambda u: {"bajo_minimo": [(articulo, 1)], "existencia_baja": [(articulo, 2, 10)], "por_revisar": 2, "conteo_viejo": Falso(pk=1, creado=ahora)})
    monkeypatch.setattr(tablero, "Traslado", Falso(PENDIENTE="pendiente", objects=Falso(filter=lambda **k: Consulta([1]))))
    diarios = [{"caja": "Caja 1", "persona": persona, "desde": ahora, "dia_anterior": True, "limite": ahora}]
    monkeypatch.setattr(tablero.cortes, "diarios_pendientes", lambda: diarios)
    monkeypatch.setattr(tablero.cortes, "entregas_con_problema", lambda: Consulta([1]))
    Negocio.objects.filter(pk=1).update(clave_recuperacion_pendiente=True)
    monkeypatch.setattr(tablero.respaldos, "alertas", lambda: ["No hay carpeta de respaldo configurada: no se están haciendo respaldos."])
    monkeypatch.setattr(tablero, "Corte", Falso(BORRADOR="borrador", objects=Falso(filter=lambda **k: Consulta([Falso(pk=1, fecha=hoy)]))))
    monkeypatch.setattr(tablero, "Denominacion", Falso(objects=Falso(filter=lambda **k: Consulta())))
    monkeypatch.setattr(tablero.CuentaBancaria, "principal_activa", classmethod(lambda cls: None))
    monkeypatch.setattr(tablero, "por_revisar", lambda u: Consulta([1]))
    monkeypatch.setattr(tablero, "avisos_pendientes", lambda u: Consulta([1]))
    certificado = {"por_vencer": True, "vence": hoy + timedelta(days=5), "dias": 5}
    monkeypatch.setattr(tablero, "certificado_para", lambda u: certificado)
    monkeypatch.setattr(tablero, "cifras", lambda u, ahora=None, diarios=None: [])
    return personas, certificado, diarios


def test_ningun_aviso_que_existia_se_pierde(todos_los_avisos):
    personas, certificado, diarios = todos_los_avisos
    filas = tablero.avisos_control(personas["dir"], certificado, diarios)
    assert ORIGINALES <= {f["clave"] for f in filas}
    assert all(f["pastilla"] and f["titulo"] and f["detalle"] for f in filas)
    respuesta = cliente(personas["dir"]).get(reverse("inicio"))
    pagina = respuesta.content.decode()
    assert respuesta.status_code == 200 and not CSS_EN_LINEA.search(pagina)
    assert ORIGINALES <= set(re.findall(r'data-aviso="([a-z_]+)"', pagina))
    for texto in ("La bitácora no está íntegra", "Diferencia de arqueo", "Recibo A-1 cancelado", "ya usó", "declarado sin comprobante", "retenidas", "Pagos sin respaldo en el estado", "Pagos sin un estado que los respalde", "Importaciones bancarias por revisar", "existencia baja, quedan 2 de 10", "espera aprobación", "Corte diario pendiente", "Guarda la clave de recuperación", "No hay carpeta de respaldo", "entrega de cortes con problemas", "Corte mayor de", "Faltan las denominaciones de caja", "Faltan los datos de pago", "Avisos sobre tu código de autorización", "El certificado del servidor vence pronto", "por identificar"):
        assert texto in pagina, texto


def test_salud_del_sistema_con_pastillas(personas):
    filas = {f["clave"]: f for f in tablero.salud(personas["dir"], {"por_vencer": False, "vence": timezone.localdate() + timedelta(days=900), "dias": 900}, 1)}
    assert set(filas) == {"bitacora", "respaldo", "prueba_restauracion", "certificado", "equipos"}
    assert filas["certificado"]["pastilla"] == "Bien" and filas["equipos"]["pastilla"] == "Revisar" and filas["prueba_restauracion"]["pastilla"] == "Por hacer"
    assert tablero.salud(personas["op"]) == []
    assert {f["clave"] for f in tablero.salud(personas["sup"], None, 0)} == {"equipos"}
