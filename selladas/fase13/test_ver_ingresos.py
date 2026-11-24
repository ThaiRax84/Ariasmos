import json
import re
from datetime import timedelta
from html.parser import HTMLParser

import pytest
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Evento
from banco import conciliacion
from banco.models import Banco, CuentaBancaria, Importacion, MovimientoBancario
from caja.servicios import cerrar_turno
from cobros import libro
from cobros.models import ConceptoCobro
from configuracion import plantillas
from configuracion.models import Negocio, Parametro
from cuentas import permisos
from cuentas.models import Delegacion, PermisoRol, Rol
from inventario import servicios as inventario
from inventario.models import Articulo, Conteo, Venta
from pruebas.conftest import cliente, nuevo_usuario
from pruebas.libro_ayudas import piezas_de, preparar_conceptos, titular_activo, turno_de
from solicitudes import motor

PROPIO = 295850
AJENO_CAJA = 481750
AJENO_BANCO = 736291
TRANSFERENCIA = 618329
VENTA_AJENA = 563817
VENTA_PROPIA = 382946
CLABE = "002010077777777771"

# Estado de las migraciones en main antes de la fase 13: volver a él simula una instalación existente.
HOJAS_ANTES_DE_LA_FASE = [
    ("actualizaciones", "0002_contadores_por_llave"),
    ("auditoria", "0003_bitacora_sellada"),
    ("banco", "0010_origen_aviso"),
    ("caja", "0006_tipo_denominacion"),
    ("cobros", "0009_periodos_semanales_y_quincenales"),
    ("configuracion", "0017_control_denominaciones_de_fabrica"),
    ("cortes", "0002_niveles_con_vocabulario"),
    ("cuentas", "0010_merge_20261118_1411"),
    ("envios", "0001_inicial"),
    ("inventario", "0002_dinero_por_renglon_devuelto"),
    ("licencias", "0001_initial"),
    ("respaldos", "0001_inicial"),
    ("rezagos", "0001_inicial"),
    ("solicitudes", "0011_acciones_sin_credito"),
    ("tarifas", "0001_inicial"),
    ("titulares", "0005_hojas_y_apellidos_opcionales"),
    ("vivo", "0001_inicial"),
]


@pytest.fixture(autouse=True)
def sin_frecuencia_previa():
    cache.clear()
    yield
    cache.clear()


def rastros(centavos):
    pesos, resto = divmod(centavos, 100)
    return {f"{pesos:,}.{resto:02d}", f"{pesos}.{resto:02d}", f"{pesos:,}", str(centavos)}


def lleva(texto, centavos):
    return any(r in texto for r in rastros(centavos))


class _Avisos(HTMLParser):
    def __init__(self):
        super().__init__()
        self.avisos = []

    def handle_starttag(self, etiqueta, atributos):
        datos = dict(atributos)
        if datos.get("data-medio") == "banco" and "data-aviso" in datos:
            self.avisos.append(datos["data-aviso"] or "")


def avisos_de_transferencia(html):
    lector = _Avisos()
    lector.feed(html)
    return lector.avisos


def enlaza(html, url):
    return re.search(r"""href=["']""" + re.escape(url) + r"""["']""", html) is not None


def pagina(c, nombre, *args):
    respuesta = c.get(reverse(nombre, args=args))
    assert respuesta.status_code == 200
    return respuesta.content.decode()


def cobros_de_todos(gente):
    ana = titular_activo(gente["op"], gente["sup"], "Ana")
    beto = titular_activo(gente["op"], gente["sup"], "Beto")
    carla = titular_activo(gente["op"], gente["sup"], "Carla")
    turno_propio = turno_de(gente["op"])
    libro.registrar_pago(ana, PROPIO, "efectivo", gente["op"], turno=turno_propio)
    cerrar_turno(turno_propio, gente["op"], piezas_de(PROPIO))
    libro.registrar_pago(beto, AJENO_CAJA, "efectivo", gente["op2"], turno=turno_de(gente["op2"], "Caja 2"))
    libro.registrar_pago(carla, AJENO_BANCO, "banco", gente["dir"])
    return ana, beto, carla


def movimiento(importe, huella, quien):
    banco, _ = Banco.objects.get_or_create(clave="002", defaults={"nombre": "Banco de prueba"})
    cuenta = CuentaBancaria.objects.filter(clabe=CLABE).first() or CuentaBancaria.objects.create(banco=banco, clabe=CLABE, beneficiario="Negocio de prueba", principal=True)
    importacion = Importacion.objects.create(cuenta=cuenta, nombre_archivo=f"{huella}.pdf", sha256="0" * 64, adaptador=Importacion.ESTADO_PDF, creada_por=quien)
    return MovimientoBancario.objects.create(
        cuenta=cuenta, importacion=importacion, fecha=timezone.localdate(), importe=importe, sentido="abono", clase="spei", huella=huella, estado="por_identificar", nombre_pagador="PERSONA FICTICIA"
    )


def ventas_de_dos(gente):
    Parametro.objects.update_or_create(clave="modulo_inventario", defaults={"valor": "1"})
    libros = ConceptoCobro.objects.get(nombre="Libros")
    atlas = Articulo.objects.create(clave="ATL-1", nombre="Atlas", precio=VENTA_AJENA, concepto=libros)
    brujula = Articulo.objects.create(clave="BRU-1", nombre="Brújula", precio=VENTA_PROPIA, concepto=libros)
    conteo = inventario.subir_conteo({atlas.pk: 5, brujula.pk: 5}, gente["op"], Conteo.PANTALLA)
    motor.aprobar(conteo.solicitud, gente["sup"])
    dana = titular_activo(gente["op"], gente["sup"], "Dana")
    elisa = titular_activo(gente["op"], gente["sup"], "Elisa")
    ajena = inventario.vender(dana, [(atlas.pk, 1)], Venta.ADEUDO, gente["dir"])
    propia = inventario.vender(elisa, [(brujula.pk, 1)], Venta.ADEUDO, gente["op"])
    return ajena, propia


def ve_todo_lo_que_entra(c, nombres_ajenos):
    for html in (pagina(c, "ultimo"), pagina(c, "inicio")):
        assert lleva(html, AJENO_CAJA) and lleva(html, AJENO_BANCO)
        assert all(n in html for n in nombres_ajenos)


def test_1_ultimos_cobros_sin_importes_ajenos(personas):
    preparar_conceptos()
    ana, beto, carla = cobros_de_todos(personas)
    c = cliente(personas["op"])
    for html in (pagina(c, "ultimo"), pagina(c, "inicio")):
        assert not lleva(html, AJENO_CAJA) and not lleva(html, AJENO_BANCO)
        assert beto.nombre_completo in html and carla.nombre_completo in html
        assert lleva(html, PROPIO) and ana.nombre_completo in html
    ve_todo_lo_que_entra(cliente(personas["sup"]), (beto.nombre_completo, carla.nombre_completo))


def test_2_aviso_de_transferencia_sin_importe(personas):
    preparar_conceptos()
    fany = titular_activo(personas["op"], personas["sup"], "Fany")
    conciliacion.confirmar(movimiento(TRANSFERENCIA, "h-transferencia", personas["dir"]), fany, personas["dir"])
    c = cliente(personas["op"])
    for html in (pagina(c, "ultimo"), pagina(c, "inicio")):
        avisos = avisos_de_transferencia(html)
        assert avisos and all(fany.nombre_completo in a for a in avisos)
        assert not lleva(html, TRANSFERENCIA)
    avisos = avisos_de_transferencia(pagina(cliente(personas["sup"]), "ultimo"))
    assert avisos and any(lleva(a, TRANSFERENCIA) and fany.nombre_completo in a for a in avisos)


def test_3_cola_del_banco_cerrada_aun_con_sugerir_conciliacion(personas):
    deposito = movimiento(AJENO_BANCO, "h-cola", personas["dir"])
    op = personas["op"]
    assert op.tiene_permiso("sugerir_conciliacion")
    cola = reverse("conciliacion:cola")
    detalle = reverse("conciliacion:movimiento", args=[deposito.pk])
    c = cliente(op)
    for url in (cola, detalle):
        respuesta = c.get(url)
        assert respuesta.status_code == 403
        assert not lleva(respuesta.content.decode(), AJENO_BANCO)
    assert not enlaza(pagina(c, "inicio"), cola)
    sup = cliente(personas["sup"])
    for url in (cola, detalle):
        respuesta = sup.get(url)
        assert respuesta.status_code == 200 and lleva(respuesta.content.decode(), AJENO_BANCO)
    assert enlaza(pagina(sup, "inicio"), cola)


def test_4_ventas_solo_las_propias(personas):
    preparar_conceptos()
    ajena, propia = ventas_de_dos(personas)
    url_ajena = reverse("inventario:venta", args=[ajena.pk])
    url_propia = reverse("inventario:venta", args=[propia.pk])
    c = cliente(personas["op"])
    lista = pagina(c, "inventario:ventas")
    assert enlaza(lista, url_propia) and lleva(lista, VENTA_PROPIA)
    assert not enlaza(lista, url_ajena) and not lleva(lista, VENTA_AJENA)
    respuesta = c.get(url_ajena)
    assert respuesta.status_code == 403 and not lleva(respuesta.content.decode(), VENTA_AJENA)
    assert c.get(url_propia).status_code == 200
    sup = cliente(personas["sup"])
    lista = pagina(sup, "inventario:ventas")
    assert enlaza(lista, url_ajena) and lleva(lista, VENTA_AJENA) and enlaza(lista, url_propia)
    assert sup.get(url_ajena).status_code == 200


def _delegar(otorgante, receptor):
    respuesta = cliente(otorgante).post(reverse("delegacion_nueva"), {"receptor": receptor.pk, "permiso": "ver_ingresos", "dias": "1", "motivo": "cubrir la caja"})
    assert respuesta.status_code == 302
    return Delegacion.objects.get(receptor=receptor, permiso="ver_ingresos", revocada=False)


def _ve_importes(usuario):
    c = cliente(usuario)
    return lleva(pagina(c, "ultimo"), AJENO_BANCO), c.get(reverse("conciliacion:cola")).status_code


@pytest.mark.parametrize("quien_otorga", ["dir", "sup"])
def test_5_conceder_por_delegacion_y_perderlo_al_vencer_o_revocar(personas, quien_otorga):
    preparar_conceptos()
    cobros_de_todos(personas)
    otorgante, op = personas[quien_otorga], personas["op"]
    assert otorgante.tiene_permiso("otorgar_delegaciones")
    assert _ve_importes(op) == (False, 403)
    delegacion = _delegar(otorgante, op)
    assert _ve_importes(op) == (True, 200)
    assert cliente(otorgante).post(reverse("delegacion_revocar", args=[delegacion.pk])).status_code == 302
    assert _ve_importes(op) == (False, 403)
    otra = _delegar(otorgante, op)
    assert _ve_importes(op) == (True, 200)
    Delegacion.objects.filter(pk=otra.pk).update(vence=timezone.now() - timedelta(seconds=1))
    assert _ve_importes(op) == (False, 403)


def _datos_rol(rol, lista):
    datos = {"nombre": rol.nombre, "nivel": rol.nivel, "minutos_inactividad": rol.minutos_inactividad, "permisos": sorted(lista)}
    if rol.requiere_totp:
        datos["requiere_totp"] = "on"
    return datos


def test_6_operacion_no_puede_darse_ver_ingresos(personas):
    assert "ver_ingresos" in permisos.PERMISOS and "ver_ingresos" in permisos.DELEGABLES
    op, op2 = personas["op"], personas["op2"]
    rol = op.rol
    antes = rol.permisos()
    c = cliente(op)
    for receptor in (op, op2):
        assert c.post(reverse("delegacion_nueva"), {"receptor": receptor.pk, "permiso": "ver_ingresos", "dias": "1", "motivo": "yo"}).status_code == 403
    assert c.post(reverse("rol_editar", args=[rol.pk]), _datos_rol(rol, antes | {"ver_ingresos"})).status_code == 403
    assert not Delegacion.objects.exists() and rol.permisos() == antes

    # Aun con permisos para delegar y editar papeles, solo se da lo que se tiene por el propio papel.
    for extra in ("otorgar_delegaciones", "administrar_roles"):
        PermisoRol.objects.create(rol=rol, permiso=extra)
    ampliados = rol.permisos()
    prestada = _delegar(personas["dir"], op)
    c = cliente(op)
    for receptor in (op, op2):
        c.post(reverse("delegacion_nueva"), {"receptor": receptor.pk, "permiso": "ver_ingresos", "dias": "1", "motivo": "yo"})
    c.post(reverse("rol_editar", args=[rol.pk]), _datos_rol(rol, ampliados | {"ver_ingresos"}))
    assert list(Delegacion.objects.filter(permiso="ver_ingresos").values_list("pk", flat=True)) == [prestada.pk]
    assert rol.permisos() == ampliados


def _instalacion_vieja():
    Negocio.objects.update_or_create(pk=1, defaults={"nombre": "Negocio existente", "nota_ficha": "Instrucciones", "plantilla": "escuela", "configurado": True})
    datos = plantillas.leer("escuela")
    datos = {**datos, "roles": [{**r, "permisos": [p for p in r["permisos"] if p != "ver_ingresos"]} for r in datos["roles"]]}
    plantillas.cargar_datos(datos, "escuela")
    contabilidad = Rol.objects.create(nombre="Contabilidad", nivel=2)
    PermisoRol.objects.create(rol=contabilidad, permiso="ver_cortes")
    mostrador = Rol.objects.create(nombre="Mostrador del banco", nivel=1)
    for permiso in ("ver_titulares", "sugerir_conciliacion", "conciliar_banco", "registrar_pago_efectivo"):
        PermisoRol.objects.create(rol=mostrador, permiso=permiso)


def _migrar(destino=None):
    ejecutor = MigrationExecutor(connection)
    ejecutor.loader.build_graph()
    ejecutor.migrate(destino or ejecutor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_7_instalacion_existente_recibe_ver_ingresos_donde_hay_ver_cortes():
    try:
        _migrar(HOJAS_ANTES_DE_LA_FASE)
        _instalacion_vieja()
        assert not PermisoRol.objects.filter(permiso="ver_ingresos").exists()
        antes = {rol.nombre: rol.permisos() for rol in Rol.objects.all()}
    finally:
        _migrar()
    con_cortes = {n for n, lista in antes.items() if "ver_cortes" in lista}
    assert con_cortes == {"Supervisión", "Dirección", "Contabilidad"}
    assert set(PermisoRol.objects.filter(permiso="ver_ingresos").values_list("rol__nombre", flat=True)) == con_cortes
    assert {rol.nombre: rol.permisos() for rol in Rol.objects.all()} == {n: lista | ({"ver_ingresos"} if n in con_cortes else set()) for n, lista in antes.items()}
    eventos = [e.datos for e in Evento.objects.filter(accion="permiso_agregado")]
    assert sorted(json.dumps(d, sort_keys=True) for d in eventos) == sorted(json.dumps({"permiso": "ver_ingresos", "papel": n}, sort_keys=True) for n in con_cortes)

    roles = {r.nombre: r for r in Rol.objects.all()}
    gente = {
        "op": nuevo_usuario("operacion", roles["Operación"]),
        "op2": nuevo_usuario("operacion2", roles["Operación"]),
        "sup": nuevo_usuario("supervision", roles["Supervisión"]),
        "dir": nuevo_usuario("direccion", roles["Dirección"]),
    }
    preparar_conceptos()
    _, beto, carla = cobros_de_todos(gente)
    deposito = movimiento(TRANSFERENCIA, "h-existente", gente["dir"])
    ajena, _ = ventas_de_dos(gente)
    for quien in ("sup", "dir"):
        c = cliente(gente[quien])
        ve_todo_lo_que_entra(c, (beto.nombre_completo, carla.nombre_completo))
        assert c.get(reverse("conciliacion:cola")).status_code == 200
        assert lleva(pagina(c, "conciliacion:movimiento", deposito.pk), TRANSFERENCIA)
        assert lleva(pagina(c, "inventario:ventas"), VENTA_AJENA)
        assert c.get(reverse("inventario:venta", args=[ajena.pk])).status_code == 200
    assert not lleva(pagina(cliente(gente["op"]), "ultimo"), AJENO_BANCO)
