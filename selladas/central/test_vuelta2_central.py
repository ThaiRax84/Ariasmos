import base64
import json
from datetime import timedelta

from emision import llave, servicios
from emision.models import Ajuste, Bitacora, CodigoActivacion, Instalacion, Rechazo, Sello
from nucleo.licencia import abrir, texto_de
from selladas.central.test_central import (  # noqa: F401  fixtures de la primera tanda
    RECHAZADA,
    Equipo,
    activado,
    activar,
    activo,
    api,
    b64,
    cuerpo_activar,
    enviar,
    hora,
    negocio,
    negocio_pagado,
    peticion,
    renovar,
)


def sello_de(cuerpo):
    return json.loads(base64.b64decode(cuerpo["carga"]))["sello"]


def escrito():
    return Rechazo.objects.count(), Sello.objects.count(), Bitacora.objects.count(), Instalacion.objects.count()


def comprobar_acuse(respuesta, equipo, sello, hora):
    carga = abrir(respuesta.json()["acuse"], [llave.publica()], "acuse")
    assert (carga["instalacion"], carga["sello"], carga["hora"]) == (equipo.huella, sello, texto_de(hora.momento))


def test_activacion_a_medias_se_puede_repetir_solo_por_el_mismo_equipo(api, hora, db):
    for pagado, resultado in ((True, "activada"), (False, "pago_pendiente")):
        empresa = negocio_pagado(hora, f"Negocio {resultado}") if pagado else servicios.crear_negocio(f"Negocio {resultado}")
        codigo, equipo = servicios.crear_codigo(empresa), Equipo()
        primera = activar(api, equipo, codigo, hora.momento)
        assert primera.status_code == 200 and primera.json()["resultado"] == resultado
        instalaciones, rechazos = Instalacion.objects.count(), Rechazo.objects.count()

        for _ in range(2):
            repetida = activar(api, equipo, codigo, hora.momento)
            assert repetida.status_code == 200 and repetida.json()["resultado"] == resultado
            if pagado:
                assert abrir(repetida.json()["documento"], [llave.publica()], "licencia")["instalacion"] == equipo.huella
            else:
                assert repetida.json() == {"resultado": "pago_pendiente"}
        assert (Instalacion.objects.count(), Rechazo.objects.count()) == (instalaciones, rechazos)
        assert CodigoActivacion.objects.get(negocio=empresa).instalacion.huella == equipo.huella

        otro = activar(api, Equipo(), codigo, hora.momento)
        assert otro.status_code == 403 and otro.json() == RECHAZADA and Instalacion.objects.count() == instalaciones

        servicios.revocar(empresa, huella=equipo.huella)
        revocada = activar(api, equipo, codigo, hora.momento)
        assert revocada.status_code == 403 and revocada.json() == RECHAZADA

    servicios.revocar(empresa, huella=equipo.huella, deshacer=True)
    hora.momento += timedelta(days=8)
    vencido = activar(api, equipo, codigo, hora.momento)
    assert vencido.status_code == 403 and vencido.json() == RECHAZADA


def test_sobre_el_limite_la_renovacion_autentica_pasa_y_la_falsa_no_escribe(api, hora, activo):
    for _ in range(2):
        assert activar(api, Equipo(), "AAAAA-AAAAA-AAAAA-AAAAA", hora.momento).status_code == 403
    Ajuste.objects.create(clave="rechazos_por_hora", valor=2)

    autentica = {"instalacion": activo.huella, **peticion(activo, "renovacion", hora.momento)}
    respuesta = enviar(api, "/v1/renovar", autentica)
    assert respuesta.status_code == 200 and respuesta.json()["resultado"] == "renovada"

    firma_rota = bytearray(base64.b64decode(autentica["firma"]))
    firma_rota[0] ^= 1
    falsas = [
        autentica,
        {**autentica, "firma": b64(bytes(firma_rota))},
        {"instalacion": activo.huella, **peticion(activo, "renovacion", hora.momento - timedelta(minutes=11))},
        {"instalacion": activo.huella, **peticion(activo, "renovacion", hora.momento, firmante=Equipo())},
        {"instalacion": Equipo().huella, **peticion(activo, "renovacion", hora.momento)},
        {**autentica, "extra": 1},
    ]
    codigo_ajeno = servicios.crear_codigo(negocio_pagado(hora, "Otro negocio"))
    antes = escrito()
    for falsa in falsas:
        respuesta = enviar(api, "/v1/renovar", falsa)
        assert respuesta.status_code == 429 and respuesta.json() == {"error": "espera"}
    respuesta = activar(api, Equipo(), codigo_ajeno, hora.momento)
    assert respuesta.status_code == 429
    assert escrito() == antes


def test_renovada_y_activada_traen_acuse_de_central(api, hora, db):
    negocio = negocio_pagado(hora)
    equipo = Equipo()
    cuerpo = cuerpo_activar(equipo, servicios.crear_codigo(negocio), hora.momento)
    respuesta = enviar(api, "/v1/activar", cuerpo)
    assert respuesta.json()["resultado"] == "activada"
    comprobar_acuse(respuesta, equipo, sello_de(cuerpo), hora)

    hora.momento += timedelta(minutes=3)
    cuerpo = {"instalacion": equipo.huella, **peticion(equipo, "renovacion", hora.momento)}
    respuesta = enviar(api, "/v1/renovar", cuerpo)
    assert respuesta.json()["resultado"] == "renovada"
    comprobar_acuse(respuesta, equipo, sello_de(cuerpo), hora)

    moroso = Equipo()
    sin_pago = servicios.crear_negocio("Negocio sin pago")
    assert activar(api, moroso, servicios.crear_codigo(sin_pago), hora.momento).json() == {"resultado": "pago_pendiente"}
    assert renovar(api, moroso, hora.momento).json() == {"resultado": "pago_pendiente"}
    servicios.revocar(negocio)
    assert set(renovar(api, equipo, hora.momento).json()) == {"resultado", "documento"}

    salud = api.get("/v1/salud")
    assert salud.status_code == 200 and salud.json() == {"estado": "ok", "hora": texto_de(hora.momento)}


def test_rutas_ajenas_no_llenan_el_disco(api, hora, db):
    ajenas = [
        ("/no-existe", {}),
        ("/v1/activar/", {}),
        ("/v1//renovar", {}),
        ("/v1/salud", {"HTTP_HOST": "intruso.example"}),
    ]
    bitacora = Bitacora.objects.count()
    for ruta, extra in ajenas:
        respuesta = api.post(ruta, "{}", content_type="application/json", **extra)
        assert 400 <= respuesta.status_code < 500 and respuesta.status_code != 429
    assert Rechazo.objects.count() == len(ajenas) and Bitacora.objects.count() == bitacora

    Ajuste.objects.create(clave="rechazos_por_hora", valor=len(ajenas))
    antes = escrito()
    for _ in range(3):
        for ruta, extra in ajenas:
            respuesta = api.post(ruta, "{}", content_type="application/json", **extra)
            assert respuesta.status_code == 429
            assert api.get(ruta, **extra).status_code == 429
    assert escrito() == antes
