import base64
import json
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from auditoria.models import Evento
from licencias import cliente as cliente_central
from licencias import servicios
from licencias.models import Instalacion
from nucleo.licencia import firmar, texto_de
from selladas.producto.test_licencia_producto import central, hora, huella_nueva, licencia, local  # noqa: F401  fixtures de la primera tanda


def carga_de(cuerpo):
    return json.loads(base64.b64decode(cuerpo["carga"]))


def acuse(privada, instalacion, sello, momento):
    return firmar({"formato": 1, "producto": "ariasmos", "tipo": "acuse", "instalacion": instalacion, "sello": sello, "hora": texto_de(momento)}, privada)


class CentralFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.envios = []

    def __call__(self, ruta, cuerpo):
        self.envios.append((ruta, cuerpo))
        return self.respuestas.pop(0)(carga_de(cuerpo))


def estado():
    situacion = servicios.situacion()
    return situacion.estado, situacion.motivo


@pytest.mark.parametrize("forma", ["un_atraso_grande", "muchos_atrasos_pequenos"])
def test_atrasar_el_reloj_no_congela_la_licencia(central, hora, local, forma):
    servicios.instalar(licencia(central, local.huella, hora.momento, dias=30, gracia=14))
    hora.avanzar(days=10)
    assert estado() == ("vigente", "")
    cuenta = servicios.momento_efectivo()

    if forma == "un_atraso_grande":
        hora.avanzar(days=-9)
        assert estado() == ("vigente", "")
        assert Evento.objects.filter(accion="reloj_atrasado").exists()
    else:
        for _ in range(10):
            hora.avanzar(minutes=-50)
            assert estado() == ("vigente", "")
    assert servicios.momento_efectivo() == cuenta

    hora.avanzar(days=20, minutes=1)
    assert estado() == ("gracia", "")
    hora.avanzar(days=14)
    assert estado() == ("solo_consulta", "vencida") and not servicios.permite_escribir()


def test_acuse_falso_no_mueve_la_cuenta_y_el_autentico_cura_un_adelanto(central, hora, local, monkeypatch):
    inicio = hora.momento
    servicios.instalar(licencia(central, local.huella, inicio, dias=30))
    hora.avanzar(days=365)
    assert estado() == ("solo_consulta", "vencida")
    hora.avanzar(days=-365)
    assert estado() == ("solo_consulta", "vencida")
    cuenta = Instalacion.objects.get().mayor_momento
    hora_de_central = inicio + timedelta(minutes=5)

    falsos = [
        lambda carga: acuse(Ed25519PrivateKey.generate(), carga["instalacion"], carga["sello"], hora_de_central),
        lambda carga: acuse(central, huella_nueva(), carga["sello"], hora_de_central),
        lambda carga: acuse(central, carga["instalacion"], "0" * 32, hora_de_central),
    ]
    for numero, falso in enumerate(falsos, start=1):
        nueva = licencia(central, local.huella, inicio + timedelta(minutes=numero), dias=30)
        monkeypatch.setattr(cliente_central, "enviar", CentralFalso([lambda carga, nueva=nueva, falso=falso: (200, {"resultado": "renovada", "documento": nueva, "acuse": falso(carga)})]))
        servicios.renovar()
        assert Instalacion.objects.get().mayor_momento == cuenta
        assert estado() == ("solo_consulta", "vencida")
        assert Evento.objects.filter(accion="licencia_rechazada", datos__motivo="acuse").count() == numero

    nueva = licencia(central, local.huella, inicio + timedelta(minutes=4), dias=30)
    monkeypatch.setattr(cliente_central, "enviar", CentralFalso([lambda carga: (200, {"resultado": "renovada", "documento": nueva, "acuse": acuse(central, carga["instalacion"], carga["sello"], hora_de_central)})]))
    assert servicios.renovar() == "renovada"
    situacion = servicios.situacion()
    assert situacion.estado == "vigente" and situacion.vence == inicio + timedelta(minutes=4, days=30)
    assert Instalacion.objects.get().mayor_momento < cuenta
    assert Evento.objects.filter(accion="reloj_ajustado").exists()


@pytest.mark.parametrize("accion, resultado", [("renovar", "renovada"), ("activar", "activada")])
def test_hora_mal_puesta_reintenta_una_vez_con_la_hora_de_central(central, hora, local, monkeypatch, accion, resultado):
    ejecutar = servicios.renovar if accion == "renovar" else lambda: servicios.activar("ABCDE-FGHJK-MNPQR-STVWX")
    hora_de_central = hora.momento + timedelta(hours=3)

    def rechazo(carga):
        return 403, {"error": "rechazada"}

    def acepta(carga):
        return 200, {"resultado": resultado, "documento": licencia(central, local.huella, hora.momento)}

    for horas, respuestas, envios, final in (
        (None, [rechazo], 1, "rechazada"),
        (hora.momento + timedelta(minutes=1), [rechazo], 1, "rechazada"),
        (hora_de_central, [rechazo, rechazo], 2, "rechazada"),
        (hora_de_central, [rechazo, acepta], 2, resultado),
    ):
        falso = CentralFalso(respuestas)
        monkeypatch.setattr(cliente_central, "enviar", falso)
        monkeypatch.setattr(cliente_central, "hora_central", lambda horas=horas: horas)
        cuenta = Instalacion.objects.get().mayor_momento
        assert ejecutar() == final
        assert len(falso.envios) == envios
        primera = carga_de(falso.envios[0][1])
        assert primera["momento"] == texto_de(servicios.momento_efectivo())
        if envios == 2:
            segunda = carga_de(falso.envios[1][1])
            assert segunda["momento"] == texto_de(hora_de_central) and segunda["sello"] != primera["sello"]
        assert Instalacion.objects.get().mayor_momento == cuenta
    assert estado() == ("vigente", "") and Instalacion.objects.get().activada

    Instalacion.objects.update(activada=True, ultimo_intento=hora.momento + timedelta(days=30))
    falso = CentralFalso([lambda carga: (200, {"resultado": "pago_pendiente"})])
    monkeypatch.setattr(cliente_central, "enviar", falso)
    servicios.tarea_renovar(hora.momento.date())
    assert [ruta for ruta, _ in falso.envios] == ["/v1/renovar"]
