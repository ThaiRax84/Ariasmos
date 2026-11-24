import io

import pytest
from django.urls import reverse
from pypdf import PdfReader

from banco import conciliacion
from banco.models import Importacion, MovimientoBancario
from caja.servicios import cerrar_turno
from cobros import libro
from cobros.models import ConceptoCobro
from configuracion.models import Parametro, hoy_negocio
from cuentas.models import Delegacion, PermisoRol, Rol
from inventario import servicios as inventario
from inventario.models import Articulo, Conteo
from pruebas.conftest import cliente, nuevo_usuario
from pruebas.libro_ayudas import piezas_de, preparar_conceptos, titular_activo, turno_de
from solicitudes import motor

from .test_ver_ingresos import lleva, movimiento, pagina, sin_frecuencia_previa  # noqa: F401

PROPIO = 317450
AJENO_CAJA = 624350
AJENO_BANCO = 853127
PUBLICO = 194750
APLICADO_SOLO = 739214


def _venta_al_publico(gente, turno):
    Parametro.objects.update_or_create(clave="modulo_inventario", defaults={"valor": "1"})
    globo = Articulo.objects.create(clave="GLO-1", nombre="Globo terráqueo", precio=PUBLICO, concepto=ConceptoCobro.objects.get(nombre="Libros"))
    conteo = inventario.subir_conteo({globo.pk: 3}, gente["op"], Conteo.PANTALLA)
    motor.aprobar(conteo.solicitud, gente["sup"])
    return inventario.vender_publico([(globo.pk, 1)], gente["op2"], turno, None).pago


def _rutas(pago):
    return [reverse("cobros:recibo", args=[pago.recibo.pk]), reverse("cobros:recibo_pdf", args=[pago.recibo.pk]), reverse("cobros:revertir", args=[pago.pk])]


def test_8_recibos_ajenos_por_numero_dan_403(personas):
    preparar_conceptos()
    op = personas["op"]
    ana = titular_activo(op, personas["sup"], "Ana")
    beto = titular_activo(op, personas["sup"], "Beto")
    turno = turno_de(op)
    propio = libro.registrar_pago(ana, PROPIO, "efectivo", op, turno=turno)
    cerrar_turno(turno, op, piezas_de(PROPIO))
    turno_ajeno = turno_de(personas["op2"], "Caja 2")
    ajenos = [
        libro.registrar_pago(beto, AJENO_CAJA, "efectivo", personas["op2"], turno=turno_ajeno),
        libro.registrar_pago(beto, AJENO_BANCO, "banco", personas["dir"]),
        _venta_al_publico(personas, turno_ajeno),
    ]
    for con_turno in (False, True):
        if con_turno:
            turno_de(op)
        c = cliente(op)
        for pago in ajenos:
            for url in _rutas(pago):
                respuesta = c.get(url)
                assert respuesta.status_code == 403, url
                assert not lleva(respuesta.content.decode(errors="ignore"), pago.importe)
        for url in _rutas(propio):
            assert c.get(url).status_code == 200, url
    c = cliente(op)
    for pago in ajenos:
        recibo = pago.recibo
        valido = c.get(reverse("cobros:verificar"), {"folio": f"{recibo.serie}-{recibo.folio}", "codigo": recibo.codigo})
        assert valido.status_code == 200 and pago.titular.nombre_completo in valido.content.decode()
    recibo = ajenos[1].recibo
    falso = c.get(reverse("cobros:verificar"), {"folio": f"{recibo.serie}-{recibo.folio}", "codigo": "AAAAA-AAAAA"})
    assert beto.nombre_completo not in falso.content.decode()
    sup = cliente(personas["sup"])
    for pago in ajenos:
        assert all(sup.get(url).status_code == 200 for url in _rutas(pago))


def test_9_importaciones_y_topes_sin_ver_ingresos(personas):
    preparar_conceptos()
    carla = titular_activo(personas["op"], personas["sup"], "Carla")
    deposito = movimiento(APLICADO_SOLO, "h-topes", personas["dir"])
    Importacion.objects.filter(pk=deposito.importacion_id).update(adaptador=Importacion.ARCHIVO)
    conciliacion.confirmar(deposito, carla, personas["dir"])
    MovimientoBancario.objects.filter(pk=deposito.pk).update(dia_aplicado_solo=hoy_negocio())
    banco = Rol.objects.create(nombre="Banco sin ingresos", nivel=2)
    for permiso in ("conciliar_banco", "configurar_topes_banco"):
        PermisoRol.objects.create(rol=banco, permiso=permiso)
    concilia = cliente(nuevo_usuario("conciliadora", banco))
    lista = reverse("conciliacion:importaciones")
    detalle = reverse("conciliacion:importacion", args=[deposito.importacion_id])
    for url in (lista, detalle):
        respuesta = concilia.get(url)
        assert respuesta.status_code == 403
        assert not lleva(respuesta.content.decode(), APLICADO_SOLO)
    topes = pagina(concilia, "conciliacion:topes")
    assert not lleva(topes, APLICADO_SOLO)
    direccion = cliente(personas["dir"])
    for url in (lista, detalle):
        assert direccion.get(url).status_code == 200
    assert lleva(pagina(direccion, "conciliacion:topes"), APLICADO_SOLO)


def _prestar(otorgante, receptor, **limite):
    return cliente(otorgante).post(reverse("delegacion_nueva"), {"receptor": receptor.pk, "permiso": limite.pop("permiso", "ver_ingresos"), "motivo": "cubrir la caja", **limite})


@pytest.mark.parametrize("quien_otorga", ["dir", "sup"])
def test_10_prestamo_de_ver_ingresos_solo_por_usos_se_rechaza(personas, quien_otorga):
    otorgante, op = personas[quien_otorga], personas["op"]
    respuesta = _prestar(otorgante, op, usos="3")
    assert respuesta.status_code == 200
    assert not Delegacion.objects.exists()
    assert _prestar(otorgante, op, usos="3", dias="2").status_code == 302
    assert Delegacion.objects.filter(receptor=op, permiso="ver_ingresos", vence__isnull=False).count() == 1
    assert _prestar(otorgante, personas["op2"], dias="1").status_code == 302
    assert _prestar(otorgante, op, permiso="alta_baja_directa", usos="2").status_code == 302
    assert Delegacion.objects.filter(permiso="alta_baja_directa", vence__isnull=True, usos_maximos=2).exists()
    assert Delegacion.objects.filter(permiso="ver_ingresos").count() == 2


def test_11_historial_del_cliente_sigue_visible(personas):
    preparar_conceptos()
    dana = titular_activo(personas["op"], personas["sup"], "Dana")
    libro.registrar_pago(dana, AJENO_CAJA, "efectivo", personas["op2"], turno=turno_de(personas["op2"], "Caja 2"))
    libro.registrar_pago(dana, AJENO_BANCO, "banco", personas["dir"])
    c = cliente(personas["op"])
    ficha = pagina(c, "titulares:detalle", dana.pk)
    respuesta = c.get(reverse("titulares:estado_pdf", args=[dana.pk]))
    assert respuesta.status_code == 200
    estado = "".join(p.extract_text() for p in PdfReader(io.BytesIO(respuesta.content)).pages)
    for importe in (AJENO_CAJA, AJENO_BANCO):
        assert lleva(ficha, importe) and lleva(estado, importe)
