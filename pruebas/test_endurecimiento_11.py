from django.urls import reverse

from cuentas.models import Dispositivo

from .conftest import cliente, equipo_aprobado
from .test_fase_11 import padron, turno


def test_lo_ultimo_que_entro_exige_equipo_aprobado(personas, padron, turno):
    assert cliente().get(reverse("ultimo")).status_code == 302
    credencial = equipo_aprobado()
    c = cliente(personas["sup"], credencial=credencial)
    assert c.get(reverse("ultimo")).status_code == 200
    Dispositivo.objects.update(estado=Dispositivo.PENDIENTE)
    respuesta = c.get(reverse("ultimo"))
    assert respuesta.status_code in (302, 403)
    assert b"vivo" not in respuesta.content or respuesta.status_code == 403


def test_las_rutas_en_vivo_no_se_guardan_en_cache(personas):
    c = cliente(personas["sup"])
    for nombre in ("pulso", "ir"):
        respuesta = c.get(reverse(nombre), {"q": "a"})
        assert respuesta.status_code == 200
        assert respuesta["Cache-Control"] == "no-store"
