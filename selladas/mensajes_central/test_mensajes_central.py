import base64
import getpass
import hashlib
import io
import json
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlencode

import pytest
from django.core.management import CommandError, call_command

from emision import servicios
from emision.models import Ajuste, Bitacora
from mensajeria.models import Baja, Cuota, Documento, Mensaje, Plantilla, Remitente
from mensajeria.proveedores import simulado
from nucleo.licencia import firmar, texto_de
from selladas.central.test_central import (  # noqa: F401  fixtures de la fase 12
    PETICION,
    RECHAZADA,
    Equipo,
    activado,
    activo,
    api,
    b64,
    hora,
    negocio,
    negocio_pagado,
    peticion,
)

NUMERO = "+525512345678"
OTRO_NUMERO = "+525587654321"
VALORES = {"nombre": "Ana", "folio": "A-17"}
RUTAS = {
    "mensajes_estado": "/v1/mensajes/estado",
    "mensajes_plantilla": "/v1/mensajes/plantilla",
    "mensajes_tope": "/v1/mensajes/tope",
    "mensajes_enviar": "/v1/mensajes/enviar",
    "mensajes_consultar": "/v1/mensajes/consultar",
}


@pytest.fixture(autouse=True)
def proveedor_limpio(db):
    Ajuste.objects.update_or_create(clave="rechazos_por_hora", defaults={"valor": 10000})
    simulado.ENVIADOS.clear()
    yield
    simulado.ENVIADOS.clear()


def pdf(relleno=b""):
    return b"%PDF-1.4\n%" + secrets.token_hex(8).encode() + b"\n" + relleno + b"\n%%EOF\n"


def firmado(equipo, accion, datos, momento, firmante=None):
    carga = {
        "formato": 1,
        "producto": "ariasmos",
        "tipo": "servicio",
        "instalacion": equipo.huella,
        "momento": texto_de(momento),
        "sello": secrets.token_hex(16),
        "version": "1.0.0",
        "accion": accion,
        "datos": datos,
    }
    return {"instalacion": equipo.huella, **firmar(carga, (firmante or equipo).privada)}


def romper(cuerpo):
    firma = bytearray(base64.b64decode(cuerpo["firma"]))
    firma[0] ^= 1
    return {**cuerpo, "firma": b64(bytes(firma))}


def mandar(api, ruta, cuerpo):
    return api.post(ruta, json.dumps(cuerpo), content_type="application/json")


def pedir(api, equipo, hora, accion, datos, adjunto=None):
    cuerpo = firmado(equipo, accion, datos, hora.momento)
    if adjunto is not None:
        cuerpo["adjunto"] = b64(adjunto)
    return mandar(api, RUTAS[accion], cuerpo)


def ok(respuesta):
    assert respuesta.status_code == 200, (respuesta.status_code, respuesta.content[:300])
    assert respuesta["Cache-Control"] == "no-store"
    datos = respuesta.json()
    assert "acuse" in datos
    return datos


def datos_envio(clave_envio, plantilla="aviso", destino=NUMERO, valores=VALORES, adjunto=None, sha=None):
    datos = {"clave_envio": clave_envio, "plantilla": plantilla, "destino": destino, "valores": valores}
    if adjunto is not None:
        datos["adjunto_sha256"] = sha or hashlib.sha256(adjunto).hexdigest()
    return datos


def enviar(api, equipo, hora, clave_envio, adjunto=None, sha=None, adjunto_real=None, **cambios):
    datos = datos_envio(clave_envio, adjunto=adjunto, sha=sha, **cambios)
    return pedir(api, equipo, hora, "mensajes_enviar", datos, adjunto=adjunto_real if adjunto_real is not None else adjunto)


def resultado(respuesta):
    return ok(respuesta)["resultado"]


# El contrato no fija un servicio para conectar: el remitente se crea por el modelo.
def conectar(negocio, numero="+525500001111"):
    return Remitente.objects.create(
        negocio=negocio, numero=numero, cuenta_sid="AC" + "0" * 32, servicio_sid="MG" + "0" * 32, token_cifrado="sin-uso-con-el-simulado", activo=True
    )


def plantilla(negocio, clave="aviso", con_documento=False, estado="aprobada", texto="Hola [nombre], tu folio es [folio], gracias."):
    return Plantilla.objects.create(
        negocio=negocio, clave=clave, nombre=clave.capitalize(), texto=texto, con_documento=con_documento, variables=["nombre", "folio"], estado=estado, motivo="", id_proveedor="HX" + secrets.token_hex(16)
    )


def listo(negocio, numero="+525500001111"):
    conectar(negocio, numero)
    plantilla(negocio)


def webhook(api, ruta, campos, firma=simulado.FIRMA):
    extra = {} if firma is None else {"HTTP_X_TWILIO_SIGNATURE": firma}
    return api.post(ruta, urlencode(campos), content_type="application/x-www-form-urlencoded", **extra)


def estado_twilio(api, id_mensaje, estado, firma=simulado.FIRMA, **campos):
    return webhook(api, f"/v1/twilio/estado/{id_mensaje}", {"MessageSid": "SM" + "1" * 32, "MessageStatus": estado, **campos}, firma)


def entrante(api, negocio, texto, de="whatsapp:" + NUMERO, firma=simulado.FIRMA):
    return webhook(api, f"/v1/twilio/entrante/{negocio.id}", {"MessageSid": "SM" + "2" * 32, "From": de, "Body": texto}, firma)


def datos_de(accion, n):
    return {
        "mensajes_estado": {},
        "mensajes_plantilla": {"clave": f"falsa_{n}", "nombre": "Falsa", "texto": "Hola [nombre], prueba.", "con_documento": False},
        "mensajes_tope": {"tope": 1},
        "mensajes_enviar": datos_envio(f"falsa-{n}"),
        "mensajes_consultar": {"ids": []},
    }[accion]


def escrito():
    return (
        len(simulado.ENVIADOS),
        Mensaje.objects.count(),
        Plantilla.objects.count(),
        sorted((str(n), t, m) for n, t, m in Cuota.objects.values_list("negocio", "tope", "tope_maximo")),
    )


def test_1_peticion_falsa_a_central_da_403_y_el_proveedor_no_recibe_nada(api, hora, negocio, activo):
    listo(negocio)
    otro = negocio_pagado(hora, "Otro negocio")
    intruso = activado(api, otro, hora)
    listo(otro, "+525500002222")
    ahora = hora.momento
    intentos = [(RUTAS[accion], romper(firmado(activo, accion, datos_de(accion, n), ahora))) for n, accion in enumerate(RUTAS)]
    enviar_ruta = RUTAS["mensajes_enviar"]
    intentos += [
        (enviar_ruta, firmado(activo, "mensajes_enviar", datos_de("mensajes_enviar", 10), ahora, firmante=intruso)),
        (enviar_ruta, {**firmado(intruso, "mensajes_enviar", datos_de("mensajes_enviar", 11), ahora), "instalacion": activo.huella}),
        (enviar_ruta, firmado(Equipo(), "mensajes_enviar", datos_de("mensajes_enviar", 12), ahora)),
        (enviar_ruta, {"instalacion": activo.huella, **peticion(activo, "renovacion", ahora)}),
        (enviar_ruta, firmado(activo, "mensajes_estado", {}, ahora)),
        (RUTAS["mensajes_tope"], firmado(activo, "mensajes_enviar", datos_de("mensajes_enviar", 13), ahora)),
        (enviar_ruta, firmado(activo, "mensajes_enviar", datos_de("mensajes_enviar", 14), ahora - timedelta(minutes=11))),
        (enviar_ruta, firmado(activo, "mensajes_enviar", datos_de("mensajes_enviar", 15), ahora + timedelta(minutes=11))),
    ]
    antes = escrito()
    respuestas = [mandar(api, ruta, cuerpo) for ruta, cuerpo in intentos]
    assert escrito() == antes

    buena = firmado(activo, "mensajes_enviar", datos_envio("buena"), ahora)
    assert resultado(mandar(api, enviar_ruta, buena)) == "aceptado"
    respuestas.append(mandar(api, enviar_ruta, buena))
    despues_de_la_buena = escrito()
    assert despues_de_la_buena[:2] == (antes[0] + 1, antes[1] + 1)

    def revocar_negocio(deshacer):
        servicios.revocar(negocio, deshacer=deshacer)

    def revocar_instalacion(deshacer):
        servicios.revocar(negocio, huella=activo.huella, deshacer=deshacer)

    def sin_pago(deshacer):
        hora.momento = ahora if deshacer else ahora + timedelta(days=91)

    for condicion in (revocar_negocio, revocar_instalacion, sin_pago):
        condicion(False)
        for n, accion in enumerate(RUTAS, start=20):
            respuestas.append(pedir(api, activo, hora, accion, datos_de(accion, n)))
        condicion(True)

    for respuesta in respuestas:
        assert respuesta.status_code == 403 and respuesta.json() == RECHAZADA, (respuesta.status_code, respuesta.content[:200])
        assert respuesta.content == respuestas[0].content
    assert escrito() == despues_de_la_buena
    assert resultado(enviar(api, activo, hora, "despues")) == "aceptado"


def test_2_un_negocio_no_ve_ni_usa_lo_de_otro(api, hora, negocio, activo):
    listo(negocio, "+525500001111")
    otro = negocio_pagado(hora, "Negocio B")
    equipo_b = activado(api, otro, hora)
    conectar(otro, "+525500009999")
    secreta = plantilla(otro, clave="secreta", texto="Texto exclusivo de B [nombre] con folio [folio] marca-b-7c1f.")
    Cuota.objects.update_or_create(negocio=otro, defaults={"tope_maximo": 50, "tope": 40})

    datos_b = ok(enviar(api, equipo_b, hora, "b-1", plantilla="secreta"))
    assert datos_b["resultado"] == "aceptado"
    id_b = datos_b["id"]
    assert entrante(api, otro, "BAJA").status_code == 200
    vista_b = ok(pedir(api, equipo_b, hora, "mensajes_consultar", {"ids": [id_b]}))
    assert [m["id"] for m in vista_b["mensajes"]] == [id_b] and vista_b["bajas"] == ["b-1"]
    enviados_b = len(simulado.ENVIADOS)

    estado_a = ok(pedir(api, activo, hora, "mensajes_estado", {}))
    assert {p["clave"] for p in estado_a["plantillas"]} == {"aviso"}
    assert estado_a["numero_final"] == "1111" and estado_a["enviados_mes"] == 0
    respuesta = pedir(api, activo, hora, "mensajes_estado", {})
    assert b"marca-b-7c1f" not in respuesta.content and b"9999" not in respuesta.content

    assert resultado(enviar(api, activo, hora, "a-1", plantilla="secreta")) == "plantilla"
    assert len(simulado.ENVIADOS) == enviados_b

    datos_a = ok(enviar(api, activo, hora, "a-2"))
    assert datos_a["resultado"] == "aceptado"
    consulta = ok(pedir(api, activo, hora, "mensajes_consultar", {"ids": [id_b, datos_a["id"]]}))
    assert [m["id"] for m in consulta["mensajes"]] == [datos_a["id"]]
    assert consulta["bajas"] == []
    solo_ajenos = ok(pedir(api, activo, hora, "mensajes_consultar", {"ids": [id_b]}))
    assert solo_ajenos["mensajes"] == [] and solo_ajenos["bajas"] == []

    pedir(api, activo, hora, "mensajes_plantilla", {"clave": "secreta", "nombre": "Mía", "texto": "Texto de A [nombre] distinto.", "con_documento": False})
    pedir(api, activo, hora, "mensajes_tope", {"tope": 1})
    secreta_ahora = Plantilla.objects.get(pk=secreta.pk)
    assert (secreta_ahora.negocio_id, secreta_ahora.texto, secreta_ahora.estado) == (otro.id, secreta.texto, "aprobada")
    assert Cuota.objects.filter(negocio=otro).values_list("tope", "tope_maximo").get() == (40, 50)
    assert Mensaje.objects.get(id=id_b).negocio_id == otro.id and Mensaje.objects.filter(negocio=otro).count() == 1


def test_3_webhook_sin_firma_valida_no_cambia_nada(api, hora, negocio, activo):
    listo(negocio)
    sin_remitente = negocio_pagado(hora, "Negocio sin WhatsApp")
    primero = ok(enviar(api, activo, hora, "w-1"))["id"]
    segundo = ok(enviar(api, activo, hora, "w-2", destino=OTRO_NUMERO))["id"]
    assert Mensaje.objects.get(id=primero).estado == "aceptado"
    enviados = len(simulado.ENVIADOS)

    for firma in (None, "", "firma-falsa", simulado.FIRMA + "x"):
        for estado in ("delivered", "read", "failed"):
            assert estado_twilio(api, primero, estado, firma=firma, ErrorCode="30008").status_code == 403
        assert entrante(api, negocio, "BAJA", firma=firma).status_code == 403
    assert entrante(api, sin_remitente, "BAJA").status_code == 403
    assert Mensaje.objects.get(id=primero).estado == "aceptado" and Mensaje.objects.get(id=primero).error == ""
    assert not Baja.objects.exists()

    assert 400 <= estado_twilio(api, uuid.uuid4(), "delivered").status_code < 500
    for estado_twilio_, esperado in (("sent", "enviado"), ("delivered", "entregado"), ("sent", "entregado"), ("read", "leido"), ("delivered", "leido"), ("failed", "leido"), ("undelivered", "leido")):
        assert estado_twilio(api, primero, estado_twilio_, ErrorCode="30008").status_code == 200
        assert Mensaje.objects.get(id=primero).estado == esperado
    assert estado_twilio(api, segundo, "undelivered", ErrorCode="63016").status_code == 200
    fallido = Mensaje.objects.get(id=segundo)
    assert fallido.estado == "fallido" and "63016" in fallido.error

    respuesta = entrante(api, negocio, " baja ")
    assert respuesta.status_code == 200 and respuesta.content == b""
    assert Baja.objects.filter(negocio=negocio).count() == 1
    assert entrante(api, negocio, "Gracias").status_code == 200
    assert Baja.objects.filter(negocio=negocio).count() == 1
    assert entrante(api, negocio, "ALTA").status_code == 200
    assert not Baja.objects.exists()
    assert len(simulado.ENVIADOS) == enviados


def test_4_documento_solo_por_token_y_solo_pdf_valido(api, hora, negocio, activo):
    conectar(negocio)
    plantilla(negocio, clave="recibo", con_documento=True)
    plantilla(negocio, clave="aviso")
    contenido = pdf()
    primero = ok(enviar(api, activo, hora, "d-1", plantilla="recibo", adjunto=contenido))
    assert primero["resultado"] == "aceptado"
    segundo = ok(enviar(api, activo, hora, "d-2", plantilla="recibo", adjunto=pdf()))
    token = Documento.objects.get(mensaje_id=primero["id"]).token
    otro_token = Documento.objects.get(mensaje_id=segundo["id"]).token
    for t in (token, otro_token):
        assert len(t) == 43 and set(t) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert token != otro_token and str(primero["id"]) not in token

    descarga = api.get(f"/v1/documentos/{token}.pdf")
    assert descarga.status_code == 200 and descarga.content == contenido
    assert descarga["Content-Type"] == "application/pdf" and descarga["Cache-Control"] == "no-store" and descarga["X-Content-Type-Options"] == "nosniff"

    cambiado = ("A" if token[0] != "A" else "B") + token[1:]
    negados = [api.get(f"/v1/documentos/{secrets.token_urlsafe(32)}.pdf"), api.get(f"/v1/documentos/{cambiado}.pdf")]
    assert estado_twilio(api, segundo["id"], "delivered").status_code == 200
    negados.append(api.get(f"/v1/documentos/{otro_token}.pdf"))
    assert not Documento.objects.filter(mensaje_id=segundo["id"]).exists()
    hora.momento += timedelta(hours=2, seconds=1)
    negados.append(api.get(f"/v1/documentos/{token}.pdf"))
    for respuesta in negados:
        assert respuesta.status_code == 404
        assert (respuesta.content, respuesta.get("Content-Type")) == (negados[0].content, negados[0].get("Content-Type"))
    for ruta in ("/v1/documentos/", f"/v1/documentos/{token}", f"/v1/documentos/{token}.html", "/v1/documentos/../v1/salud.pdf"):
        assert api.get(ruta).status_code == 404
    hora.momento -= timedelta(hours=2, seconds=1)

    antes = (len(simulado.ENVIADOS), Mensaje.objects.count(), Documento.objects.count())
    grande = pdf(b"0" * 1_550_000)
    malos = [
        (enviar(api, activo, hora, "m-1", plantilla="recibo", adjunto=b"<html>no soy pdf</html>"), {400}),
        (enviar(api, activo, hora, "m-2", plantilla="recibo", adjunto=b"PDF-%PDF-1.4\n"), {400}),
        (enviar(api, activo, hora, "m-3", plantilla="recibo", adjunto=pdf(), sha="0" * 64), {400}),
        (enviar(api, activo, hora, "m-4", plantilla="recibo", adjunto=contenido, adjunto_real=pdf()), {400}),
        (pedir(api, activo, hora, "mensajes_enviar", datos_envio("m-5", plantilla="recibo")), {400}),
        (enviar(api, activo, hora, "m-6", plantilla="aviso", adjunto=pdf()), {400}),
        (pedir(api, activo, hora, "mensajes_enviar", datos_envio("m-7", plantilla="aviso"), adjunto=pdf()), {400}),
        (enviar(api, activo, hora, "m-8", plantilla="recibo", adjunto=grande), {400, 413}),
    ]
    for respuesta, esperados in malos:
        assert respuesta.status_code in esperados and respuesta.json() == PETICION, (respuesta.status_code, respuesta.content[:200])
    assert (len(simulado.ENVIADOS), Mensaje.objects.count(), Documento.objects.count()) == antes


def test_5_tope_y_clave_repetida(api, hora, negocio, activo):
    listo(negocio)
    Cuota.objects.update_or_create(negocio=negocio, defaults={"tope_maximo": 3, "tope": 2})

    primero = ok(enviar(api, activo, hora, "t-1"))
    assert primero["resultado"] == "aceptado"
    repetido = ok(enviar(api, activo, hora, "t-1", destino=OTRO_NUMERO))
    assert (repetido["resultado"], repetido["id"]) == ("repetido", primero["id"])
    assert len(simulado.ENVIADOS) == 1 and Mensaje.objects.filter(clave_envio="t-1").count() == 1
    assert resultado(enviar(api, activo, hora, "t-2")) == "aceptado"
    assert resultado(enviar(api, activo, hora, "t-3")) == "tope"
    assert len(simulado.ENVIADOS) == 2 and Mensaje.objects.count() == 2

    for tope in (4, 0, -1, 10**6):
        assert ok(pedir(api, activo, hora, "mensajes_tope", {"tope": tope}))["resultado"] == "fuera_de_rango"
    assert Cuota.objects.filter(negocio=negocio).values_list("tope", "tope_maximo").get() == (2, 3)
    assert resultado(enviar(api, activo, hora, "t-3")) == "tope"
    assert ok(pedir(api, activo, hora, "mensajes_tope", {"tope": 3}))["resultado"] == "guardado"
    assert Cuota.objects.get(negocio=negocio).tope == 3

    tercero = ok(enviar(api, activo, hora, "t-3"))
    assert tercero["resultado"] == "aceptado"
    assert resultado(enviar(api, activo, hora, "t-4")) == "tope"
    estado = ok(pedir(api, activo, hora, "mensajes_estado", {}))
    assert (estado["enviados_mes"], estado["tope"], estado["tope_maximo"]) == (3, 3, 3)
    assert len(simulado.ENVIADOS) == 3

    assert estado_twilio(api, tercero["id"], "failed", ErrorCode="30008").status_code == 200
    assert resultado(enviar(api, activo, hora, "t-4")) == "aceptado"
    assert resultado(enviar(api, activo, hora, "t-5")) == "tope"
    assert len(simulado.ENVIADOS) == 4


@pytest.mark.parametrize("de", ["whatsapp:" + NUMERO, NUMERO])
def test_6_tras_la_baja_central_no_manda_a_ese_numero(api, hora, negocio, activo, de):
    listo(negocio)
    primero = ok(enviar(api, activo, hora, "b-1"))
    assert primero["resultado"] == "aceptado"
    assert entrante(api, negocio, "BAJA", de=de).status_code == 200
    enviados = len(simulado.ENVIADOS)

    baja = ok(enviar(api, activo, hora, "b-2"))
    assert baja["resultado"] == "baja"
    assert len(simulado.ENVIADOS) == enviados and not Mensaje.objects.filter(clave_envio="b-2", negocio=negocio).exclude(estado="fallido").exists()
    assert ok(pedir(api, activo, hora, "mensajes_consultar", {"ids": [primero["id"]]}))["bajas"] == ["b-1"]
    assert resultado(enviar(api, activo, hora, "b-3", destino=OTRO_NUMERO)) == "aceptado"

    numero_sin_signo = NUMERO.lstrip("+")
    guardado = json.dumps([list(Baja.objects.values_list("resumen", flat=True)), [str(v) for v in Mensaje.objects.values_list("destino_final", "destino_resumen", "error", "id_proveedor")]])
    assert numero_sin_signo not in guardado and numero_sin_signo[-10:] not in guardado
    assert set(Mensaje.objects.values_list("destino_final", flat=True)) == {NUMERO[-4:], OTRO_NUMERO[-4:]}

    assert entrante(api, negocio, "ALTA", de=de).status_code == 200
    assert resultado(enviar(api, activo, hora, "b-4")) == "aceptado"
    assert len(simulado.ENVIADOS) == enviados + 2


def test_8_plantilla_no_aprobada_o_valores_hostiles_no_se_mandan(api, hora, negocio, activo):
    conectar(negocio)
    plantilla(negocio)
    plantilla(negocio, clave="en_revision", estado="en_revision")
    plantilla(negocio, clave="rechazada", estado="rechazada")
    creada = ok(pedir(api, activo, hora, "mensajes_plantilla", {"clave": "rechazable", "nombre": "Rechazable", "texto": "Hola [nombre], esto se rechaza [rechazar] siempre.", "con_documento": False}))
    assert creada["resultado"] == "rechazada"
    assert Plantilla.objects.get(negocio=negocio, clave="rechazable").estado == "rechazada"

    for clave in ("en_revision", "rechazada", "rechazable", "no_existe"):
        assert resultado(enviar(api, activo, hora, f"p-{clave}", plantilla=clave)) == "plantilla"
    hostiles = [
        {"nombre": "Ana"},
        {**VALORES, "extra": "x"},
        {},
        {**VALORES, "nombre": "Ana\nBAJA"},
        {**VALORES, "nombre": "Ana\rDos"},
        {**VALORES, "folio": "{{1}}"},
        {**VALORES, "folio": "A{x}"},
        {**VALORES, "nombre": "A" * 201},
    ]
    for n, valores in enumerate(hostiles):
        assert resultado(enviar(api, activo, hora, f"v-{n}", valores=valores)) == "plantilla"
    assert simulado.ENVIADOS == [] and not Mensaje.objects.exclude(estado="fallido").exists()

    assert resultado(enviar(api, activo, hora, "v-limite", valores={**VALORES, "nombre": "A" * 200})) == "aceptado"
    assert len(simulado.ENVIADOS) == 1


def test_9_el_token_no_se_filtra_y_las_entradas_hostiles_dan_4xx(api, hora, negocio, activo, monkeypatch):
    token = "tok" + secrets.token_hex(16)
    formas = [token, b64(token.encode()), token.encode().hex()]
    monkeypatch.setenv("TWILIO_TOKEN", token)
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: token)
    monkeypatch.setattr("sys.stdin", io.StringIO(token + "\n"))
    salida, errores = io.StringIO(), io.StringIO()
    call_command("whatsapp_conectar", str(negocio.id), numero=NUMERO, cuenta="AC" + "1" * 32, servicio="MG" + "1" * 32, stdout=salida, stderr=errores)
    with pytest.raises(CommandError):
        call_command("whatsapp_conectar", str(negocio.id), "--numero", OTRO_NUMERO, "--cuenta", "AC" + "2" * 32, "--servicio", "MG" + "2" * 32, "--token", token, stdout=salida, stderr=errores)
    call_command("whatsapp_estado", stdout=salida, stderr=errores)
    remitente = Remitente.objects.get(negocio=negocio)
    assert remitente.activo and remitente.numero == NUMERO and remitente.token_cifrado
    textos = [salida.getvalue(), errores.getvalue(), remitente.token_cifrado]
    plantilla(negocio)
    plantilla(negocio, clave="recibo", con_documento=True)

    validos = {accion: firmado(activo, accion, datos_de(accion, 0), hora.momento) for accion in RUTAS}
    pruebas = []
    for accion, valido in validos.items():
        ruta = RUTAS[accion]
        limite = 2 * 1024 * 1024 if accion == "mensajes_enviar" else 16 * 1024
        pruebas += [
            (ruta, json.dumps({**valido, "relleno": "A" * (limite + 10)}), {413}),
            (ruta, "{", {400}),
            (ruta, "[]", {400}),
            (ruta, "null", {400}),
            (ruta, "[" * 5000 + "]" * 5000, {400}),
            (ruta, b"\xff\xfe\x00{", {400}),
            (ruta, '{"instalacion": NaN}', {400}),
            (ruta, json.dumps({**valido, "extra": 1}), {400}),
            (ruta, json.dumps({c: v for c, v in valido.items() if c != "firma"}), {400}),
        ]
        for clave in valido:
            for incorrecto in (123, None, [], {}, True):
                pruebas.append((ruta, json.dumps({**valido, clave: incorrecto}), {400}))
    enviar_ruta = RUTAS["mensajes_enviar"]
    con_documento = datos_envio("h-0", plantilla="recibo", adjunto=pdf())
    for adjunto in ("@@@no-es-base64@@@", "QUJD=", "%PDF-", 123, [], None):
        pruebas.append((enviar_ruta, json.dumps({**firmado(activo, "mensajes_enviar", con_documento, hora.momento), "adjunto": adjunto}), {400}))

    def hostil(accion, datos):
        return (RUTAS[accion], json.dumps(firmado(activo, accion, datos, hora.momento)), set(range(400, 500)))

    base_envio = datos_envio("h-1")
    pruebas += [
        hostil("mensajes_estado", []),
        hostil("mensajes_estado", "nada"),
        hostil("mensajes_tope", {"tope": "5"}),
        hostil("mensajes_tope", {"tope": None}),
        hostil("mensajes_tope", {"tope": 1.5}),
        hostil("mensajes_tope", {"tope": True}),
        hostil("mensajes_tope", {}),
        hostil("mensajes_consultar", {"ids": "abc"}),
        hostil("mensajes_consultar", {"ids": [1]}),
        hostil("mensajes_consultar", {"ids": [str(uuid.uuid4()) for _ in range(101)]}),
        hostil("mensajes_consultar", {}),
        hostil("mensajes_plantilla", {"clave": 1, "nombre": "X", "texto": "Hola [nombre] fin", "con_documento": False}),
        hostil("mensajes_plantilla", {"clave": "x", "nombre": "X", "texto": None, "con_documento": False}),
        hostil("mensajes_plantilla", {"clave": "x", "nombre": "X", "texto": "Hola [nombre] fin", "con_documento": "si"}),
        hostil("mensajes_enviar", {**base_envio, "clave_envio": 7}),
        hostil("mensajes_enviar", {**base_envio, "valores": ["Ana", "A-17"]}),
        hostil("mensajes_enviar", {**base_envio, "destino": 525512345678}),
        hostil("mensajes_enviar", {**base_envio, "plantilla": None}),
        hostil("mensajes_enviar", {k: v for k, v in base_envio.items() if k != "destino"}),
    ]
    menos_de_500 = set(range(400, 500))
    pruebas += [
        ("/v1/twilio/estado/no-es-uuid", urlencode({"MessageStatus": "delivered"}), menos_de_500),
        (f"/v1/twilio/estado/{uuid.uuid4()}", "A" * (3 * 1024 * 1024), menos_de_500),
        (f"/v1/twilio/entrante/{negocio.id}", "%%%=&&&" * 10, menos_de_500 | {200}),
        (f"/v1/twilio/entrante/{negocio.id}", urlencode({"From": "whatsapp:" + NUMERO}), menos_de_500 | {200}),
        (f"/v1/twilio/entrante/{negocio.id}", urlencode({"Body": "BAJA"}), menos_de_500 | {200}),
        ("/v1/twilio/entrante/no-es-uuid", urlencode({"Body": "BAJA", "From": NUMERO}), menos_de_500),
    ]
    antes = escrito()

    respuestas = []
    for ruta, cuerpo, esperados in pruebas:
        tipo = "application/x-www-form-urlencoded" if ruta.startswith("/v1/twilio/") else "application/json"
        respuestas.append((ruta, api.post(ruta, cuerpo, content_type=tipo, HTTP_X_TWILIO_SIGNATURE=simulado.FIRMA), esperados))
    respuestas += [(ruta, api.get(ruta), {405}) for ruta in RUTAS.values()]
    respuestas += [(ruta, api.get(ruta), menos_de_500) for ruta in (f"/v1/twilio/estado/{uuid.uuid4()}", f"/v1/twilio/entrante/{negocio.id}")]
    respuestas.append(("estado", pedir(api, activo, hora, "mensajes_estado", {}), {200}))
    respuestas.append(("plantilla", pedir(api, activo, hora, "mensajes_plantilla", datos_de("mensajes_plantilla", 1)), {200}))

    for ruta, respuesta, esperados in respuestas:
        assert respuesta.status_code in esperados, (ruta, respuesta.status_code, respuesta.content[:200])
        textos.append(respuesta.content.decode("utf-8", "replace"))
    assert escrito()[0] == antes[0] and escrito()[1] == antes[1]
    textos.append(json.dumps(list(Bitacora.objects.values_list("accion", "datos"))))
    for texto in textos:
        assert "Traceback" not in texto
        assert not any(forma in texto for forma in formas)
