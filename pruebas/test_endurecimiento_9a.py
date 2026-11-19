import re

import pytest
from django.core.cache import cache
from django.urls import reverse

from caja import servicios as caja
from caja.models import Caja, Turno
from cobros import libro
from cobros.models import Pago
from configuracion.models import Parametro
from cuentas.models import PreferenciaOrden

from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo
from .test_endurecimiento_5a import rutas


@pytest.mark.parametrize("con_piezas", [True, False], ids=["con-piezas", "sin-piezas"])
def test_abrir_con_efectivo_sin_contar_nada_no_abre_en_cero_a_escondidas(personas, con_piezas):
    cache.clear()
    if not con_piezas:
        Parametro.objects.update_or_create(clave="control_denominaciones", defaults={"valor": "0"})
    unica = Caja.objects.get_or_create(nombre="Caja 1")[0]
    c = cliente(personas["op"])
    respuesta = c.post(reverse("caja:abrir"), {"caja": unica.pk, "apertura": "efectivo"})
    assert respuesta.status_code == 200 and "elige abrir en cero" in respuesta.content.decode()
    assert not Turno.objects.exists()
    assert c.post(reverse("caja:abrir"), {"caja": unica.pk, "apertura": "cero"}).status_code == 302
    assert Turno.objects.get().fondo_inicial == 0


def test_con_piezas_el_fondo_es_la_suma_y_no_lo_que_se_mande_escrito(personas):
    cache.clear()
    unica = Caja.objects.get_or_create(nombre="Caja 1")[0]
    c = cliente(personas["op"])
    pagina = c.get(reverse("caja:inicio")).content.decode()
    piezas = sorted(set(re.findall(r'name="(f_[^"]+)"', pagina)))
    assert piezas and 'name="fondo_inicial"' not in pagina
    datos = {"caja": unica.pk, "apertura": "efectivo", "fondo_inicial": "999999.00", piezas[0]: "2"}
    assert c.post(reverse("caja:abrir"), datos).status_code == 302
    turno = Turno.objects.get()
    assert 0 < turno.fondo_inicial < 99999900


def test_las_pantallas_de_caja_no_revelan_lo_esperado_con_el_turno_abierto(personas):
    cache.clear()
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    turno = caja.abrir_turno(personas["op"], Caja.objects.get_or_create(nombre="Caja 1")[0], 77777)
    libro.registrar_pago(ana, 123456, Pago.EFECTIVO, personas["op"], turno=turno)
    libro.registrar_pago(ana, 432101, Pago.EFECTIVO, personas["op"], turno=turno)
    huellas = ("6,333.34", "6333.34", "633334", "5,555.57", "5555.57", "555557", "1,234.56", "4,321.01")
    c = cliente(personas["op"])
    vistas = 0
    for nombre, patron in rutas():
        if not (nombre.startswith("caja:") or nombre == "inicio"):
            continue
        url = re.sub(r"<[^>]+>", str(turno.pk), "/" + patron.replace("^", "").replace("$", ""))
        respuesta = c.get(url)
        if respuesta.status_code == 200 and respuesta.get("Content-Type", "").startswith("text/html"):
            vistas += 1
            texto = respuesta.content.decode()
            assert [h for h in huellas if h in texto] == [], nombre
    assert vistas >= 3


@pytest.mark.parametrize("orden", ["contrasena", "usuario__contrasena", "-id", "nombre;drop", "matricula__regex", "", "0"])
def test_el_orden_de_las_listas_solo_acepta_claves_conocidas(personas, orden):
    cache.clear()
    c = cliente(personas["op"])
    respuesta = c.get(reverse("titulares:lista"), {"orden": orden, "sentido": "arriba"})
    assert respuesta.status_code == 200
    assert not PreferenciaOrden.objects.filter(clave=orden).exists()
