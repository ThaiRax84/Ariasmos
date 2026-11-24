import importlib
from datetime import timedelta

import pytest
from django.apps import apps as aplicaciones
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Evento
from banco.models import Banco, CuentaBancaria, Importacion, MovimientoBancario
from cobros import libro
from cobros.models import ConceptoCobro, Pago
from configuracion.models import Parametro
from cuentas.models import Delegacion, PermisoRol
from inventario import servicios as inventario
from inventario.models import Articulo, Venta
from titulares.servicios import crear_titular

from .conftest import cliente
from .libro_ayudas import preparar_conceptos


@pytest.fixture
def escenario(personas):
    preparar_conceptos()
    PermisoRol.objects.get_or_create(rol=personas["op"].rol, permiso="sugerir_conciliacion")
    ana = crear_titular(personas["dir"], {"nombre": "Ana", "apellidos": "Zamora"}, contacto={"nombre": "Resp", "valores": {}})
    libro.crear_cargo(ana, ConceptoCobro.objects.get(nombre="Inscripción"), 777700, timezone.now().date(), "manual")
    return ana


def _cobro(titular, importe, usuario):
    return libro.registrar_pago(titular, importe, Pago.BANCO, usuario)


def test_ultimo_sin_permiso_no_manda_importes_ajenos_pero_si_los_propios(personas, escenario):
    _cobro(escenario, 111100, personas["sup"])
    _cobro(escenario, 222200, personas["op"])
    sin = cliente(personas["op"]).get(reverse("ultimo")).content.decode()
    assert "1,111.00" not in sin and "2,222.00" in sin
    assert 'data-aviso="Transferencia recibida · Ana Zamora"' in sin
    con = cliente(personas["sup"]).get(reverse("ultimo")).content.decode()
    assert "1,111.00" in con and "2,222.00" in con


def test_cola_del_banco_pide_ver_ingresos_y_el_menu_no_la_ofrece(personas, escenario):
    cuenta = CuentaBancaria.objects.create(banco=Banco.objects.get(clave="002"), clabe="002010077777777771", beneficiario="B", principal=True)
    importacion = Importacion.objects.create(cuenta=cuenta, nombre_archivo="e.pdf", sha256="0" * 64, adaptador=Importacion.ESTADO_PDF, creada_por=personas["dir"])
    movimiento = MovimientoBancario.objects.create(cuenta=cuenta, importacion=importacion, fecha=timezone.now().date(), importe=987600, sentido="abono", clase="spei", huella="h1", estado="por_identificar")
    c = cliente(personas["op"])
    detalle = reverse("conciliacion:movimiento", args=[movimiento.pk])
    assert c.get(reverse("conciliacion:cola")).status_code == 403
    assert c.get(detalle).status_code == 403
    assert c.post(reverse("conciliacion:proponer", args=[movimiento.pk]), {"matricula": "1"}).status_code == 403
    assert reverse("conciliacion:cola") not in c.get(reverse("inicio")).content.decode()
    assert cliente(personas["sup"]).get(reverse("conciliacion:cola")).status_code == 200
    assert cliente(personas["sup"]).get(detalle).status_code == 200


def test_ventas_ajenas_solo_con_ver_ingresos(personas, escenario):
    Parametro.objects.update_or_create(clave="modulo_inventario", defaults={"valor": "1"})
    articulo = Articulo.objects.create(clave="LIB-1", nombre="Libro", precio=10000, concepto=ConceptoCobro.objects.first())
    ajena = inventario.vender(escenario, [(articulo.pk, 2)], Venta.ADEUDO, personas["sup"])
    propia = inventario.vender(escenario, [(articulo.pk, 1)], Venta.ADEUDO, personas["op"])
    c = cliente(personas["op"])
    lista = c.get(reverse("inventario:ventas")).content.decode()
    assert str(propia) in lista and str(ajena) not in lista
    assert c.get(reverse("inventario:venta", args=[propia.pk])).status_code == 200
    assert c.get(reverse("inventario:venta", args=[ajena.pk])).status_code == 403
    assert c.get(reverse("inventario:devolver_venta", args=[ajena.pk])).status_code == 403
    assert str(ajena) in cliente(personas["sup"]).get(reverse("inventario:ventas")).content.decode()


def test_la_delegacion_da_y_quita_ver_ingresos_al_momento(personas, escenario):
    _cobro(escenario, 333300, personas["sup"])
    delegacion = Delegacion.objects.create(otorgante=personas["dir"], receptor=personas["op"], permiso="ver_ingresos", vence=timezone.now() + timedelta(days=1))
    assert "3,333.00" in cliente(personas["op"]).get(reverse("ultimo")).content.decode()
    Delegacion.objects.filter(pk=delegacion.pk).update(revocada=True)
    assert "3,333.00" not in cliente(personas["op"]).get(reverse("ultimo")).content.decode()
    assert Delegacion.objects.get(pk=delegacion.pk).usos == 0


def test_la_migracion_da_ver_ingresos_solo_a_quien_ve_cortes(roles):
    PermisoRol.objects.filter(permiso="ver_ingresos").delete()
    migracion = importlib.import_module("cuentas.migrations.0011_ver_ingresos")
    migracion.otorgar(aplicaciones, None)
    con_cortes = set(PermisoRol.objects.filter(permiso="ver_cortes").values_list("rol__nombre", flat=True))
    assert set(PermisoRol.objects.filter(permiso="ver_ingresos").values_list("rol__nombre", flat=True)) == con_cortes != set()
    eventos = Evento.objects.filter(accion="permiso_agregado")
    assert {e.datos["papel"] for e in eventos} == con_cortes and all(e.datos["permiso"] == "ver_ingresos" for e in eventos)
    migracion.quitar(aplicaciones, None)
    assert not PermisoRol.objects.filter(permiso="ver_ingresos").exists()
