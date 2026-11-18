from django.core.cache import cache
from django.urls import reverse

from cobros.models import ConceptoCobro
from configuracion.models import Parametro
from inventario import servicios as inventario
from inventario.models import Articulo, Conteo, Venta
from solicitudes import motor

from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo


def test_las_ventas_de_contado_que_nadie_cobro_le_aparecen_a_quien_revisa(personas, monkeypatch):
    cache.clear()
    preparar_conceptos()
    Parametro.objects.update_or_create(clave="modulo_inventario", defaults={"valor": "1"})
    libros = ConceptoCobro.objects.get(nombre="Libros")
    cuaderno = Articulo.objects.create(clave="CUA-1", nombre="Cuaderno", precio=5000, concepto=libros)
    conteo = inventario.subir_conteo({cuaderno.pk: 20}, personas["op"], Conteo.PANTALLA)
    motor.aprobar(conteo.solicitud, personas["sup"])
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    venta = inventario.vender(ana, [(cuaderno.pk, 1)], Venta.AHORA, personas["op"])
    assert inventario.avisos(personas["sup"])["ventas_sin_cobrar"] == 0
    monkeypatch.setattr(inventario, "MINUTOS_VENTA_SIN_COBRAR", -1)
    assert inventario.avisos(personas["sup"])["ventas_sin_cobrar"] == 1
    assert not inventario.avisos(personas["op"]).get("ventas_sin_cobrar")
    pagina = cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    assert "sin cobro" in pagina
