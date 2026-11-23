from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from auditoria.models import Evento
from licencias import cliente as cliente_central
from licencias import reloj, servicios
from licencias.models import Instalacion
from selladas.producto.test_licencia_producto import central, hora, huella_nueva, licencia, local  # noqa: F401  fixtures de la primera tanda
from selladas.producto.test_vuelta2_producto import CentralFalso, acuse, estado


def oscilar(hora, veces, regreso):
    for _ in range(veces):
        hora.avanzar(minutes=4)
        servicios.situacion()
        hora.momento -= regreso
        servicios.momento_efectivo()


@pytest.mark.parametrize("regreso", [timedelta(minutes=4), timedelta(minutes=3, seconds=59)])
def test_reloj_oscilante_no_detiene_la_cuenta(central, hora, local, regreso):
    servicios.instalar(licencia(central, local.huella, hora.momento, dias=1, gracia=1))
    hora.avanzar(days=1, minutes=-30)
    assert estado() == ("vigente", "")

    oscilar(hora, 7, regreso)
    assert estado() == ("vigente", "")
    oscilar(hora, 1, regreso)
    assert estado() == ("gracia", "")

    hora.avanzar(days=1, minutes=-32)
    oscilar(hora, 7, regreso)
    assert estado() == ("gracia", "")
    oscilar(hora, 1, regreso)
    assert estado() == ("solo_consulta", "vencida") and not servicios.permite_escribir()


def test_pago_pendiente_con_acuse_autentico_corrige_la_cuenta(central, hora, local, monkeypatch):
    inicio = hora.momento
    servicios.instalar(licencia(central, local.huella, inicio, dias=30, gracia=14))
    hora.avanzar(days=10)
    assert estado() == ("vigente", "")
    cuenta = Instalacion.objects.get().mayor_momento
    hora_de_central = inicio + timedelta(days=60)

    falsos = [
        lambda carga: acuse(Ed25519PrivateKey.generate(), carga["instalacion"], carga["sello"], hora_de_central),
        lambda carga: acuse(central, huella_nueva(), carga["sello"], hora_de_central),
        lambda carga: acuse(central, carga["instalacion"], "0" * 32, hora_de_central),
    ]
    for numero, falso in enumerate(falsos, start=1):
        monkeypatch.setattr(cliente_central, "enviar", CentralFalso([lambda carga, falso=falso: (200, {"resultado": "pago_pendiente", "acuse": falso(carga)})]))
        assert servicios.renovar() == "pago_pendiente"
        assert Instalacion.objects.get().mayor_momento == cuenta and estado() == ("vigente", "")
        assert Evento.objects.filter(accion="licencia_rechazada", datos__motivo="acuse").count() == numero

    monkeypatch.setattr(cliente_central, "enviar", CentralFalso([lambda carga: (200, {"resultado": "pago_pendiente", "acuse": acuse(central, carga["instalacion"], carga["sello"], hora_de_central)})]))
    assert servicios.renovar() == "pago_pendiente"
    assert Instalacion.objects.get().mayor_momento == hora_de_central
    assert Evento.objects.filter(accion="reloj_ajustado").exists()
    assert estado() == ("solo_consulta", "vencida")


class Transcurrido:
    def __init__(self):
        self.segundos = 1000.0

    def __call__(self):
        return self.segundos


def test_reloj_detenido_la_tarea_vuelve_a_preguntar_por_tiempo_real(central, hora, local, monkeypatch):
    transcurrido = Transcurrido()
    monkeypatch.setattr(reloj, "transcurrido", transcurrido)
    monkeypatch.setattr(servicios, "ultimo_intento_real", None)
    Instalacion.objects.update(activada=True, ultimo_intento=hora.momento - timedelta(hours=1))
    falso = CentralFalso([lambda carga: (200, {"resultado": "pago_pendiente"})])
    monkeypatch.setattr(cliente_central, "enviar", falso)
    hoy = hora.momento.date()

    servicios.tarea_renovar(hoy)
    assert falso.envios == []
    transcurrido.segundos += 13 * 3600
    servicios.tarea_renovar(hoy)
    assert [ruta for ruta, _ in falso.envios] == ["/v1/renovar"]
    servicios.tarea_renovar(hoy)
    assert len(falso.envios) == 1
