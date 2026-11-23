from datetime import timedelta

import pytest

from emision import llave, servicios
from emision.models import Bitacora, Instalacion
from nucleo.licencia import abrir
from selladas.central.test_central import Equipo, activado, api, cuerpo_activar, enviar, hora, negocio_pagado, peticion  # noqa: F401  fixtures de la primera tanda
from selladas.central.test_vuelta2_central import comprobar_acuse, sello_de


def test_pago_pendiente_y_revocada_traen_acuse(api, hora, db):
    sin_pago = servicios.crear_negocio("Negocio sin pago")
    moroso = Equipo()
    cuerpo = cuerpo_activar(moroso, servicios.crear_codigo(sin_pago), hora.momento)
    respuesta = enviar(api, "/v1/activar", cuerpo)
    assert set(respuesta.json()) == {"resultado", "acuse"} and respuesta.json()["resultado"] == "pago_pendiente"
    comprobar_acuse(respuesta, moroso, sello_de(cuerpo), hora)

    hora.momento += timedelta(minutes=3)
    cuerpo = {"instalacion": moroso.huella, **peticion(moroso, "renovacion", hora.momento)}
    respuesta = enviar(api, "/v1/renovar", cuerpo)
    assert set(respuesta.json()) == {"resultado", "acuse"} and respuesta.json()["resultado"] == "pago_pendiente"
    comprobar_acuse(respuesta, moroso, sello_de(cuerpo), hora)

    servicios.revocar(sin_pago)
    hora.momento += timedelta(minutes=3)
    cuerpo = {"instalacion": moroso.huella, **peticion(moroso, "renovacion", hora.momento)}
    respuesta = enviar(api, "/v1/renovar", cuerpo)
    assert set(respuesta.json()) == {"resultado", "documento", "acuse"} and respuesta.json()["resultado"] == "revocada"
    assert abrir(respuesta.json()["documento"], [llave.publica()], "revocacion")["instalacion"] == moroso.huella
    comprobar_acuse(respuesta, moroso, sello_de(cuerpo), hora)


def revocadas(negocio):
    return dict(Instalacion.objects.filter(negocio=negocio).values_list("huella", "revocada"))


def test_deshacer_una_cancelacion_respeta_el_tope(api, hora, db):
    negocio = negocio_pagado(hora, instalaciones=1)
    primero = activado(api, negocio, hora)
    servicios.revocar(negocio, huella=primero.huella)
    segundo = activado(api, negocio, hora)
    antes, bitacora = revocadas(negocio), Bitacora.objects.count()

    with pytest.raises(servicios.TopeDeInstalaciones):
        servicios.revocar(negocio, huella=primero.huella, deshacer=True)
    assert revocadas(negocio) == antes == {primero.huella: True, segundo.huella: False}
    assert Bitacora.objects.count() == bitacora

    servicios.revocar(negocio, huella=segundo.huella)
    servicios.revocar(negocio, huella=primero.huella, deshacer=True)
    assert revocadas(negocio) == {primero.huella: False, segundo.huella: True}
