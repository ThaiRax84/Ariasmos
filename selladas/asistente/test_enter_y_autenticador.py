import re
from urllib.parse import parse_qs, urlsplit

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from configuracion import marca as marca_negocio
from configuracion.models import Negocio, parametro
from cuentas import qr
from cuentas.models import Usuario
from nucleo import totp
from pruebas.conftest import CONTRASENA
from pruebas.test_asistente import paso_inicio
from pruebas.test_fabrica import Campos

PASOS = ("inicio", "marca", "personalizar", "grupos", "conceptos", "pago", "caja", "reglas", "cortes", "usuario", "codigo")
# Enter solo envía desde campos de una línea; un formulario con solo un archivo (el logo de «Marca») no se envía con Enter.
ESCRIBIBLES = {"text", "search", "url", "tel", "email", "password", "number", "date", "month", "week", "time", "datetime-local"}
COLOR_PRINCIPAL, COLOR_ACENTO = "#1F1A4E", "#F58634"
TEXTO_CONSTANCIA = "Constancia de prueba enviada con Enter"
DATOS = {
    "inicio": paso_inicio(settings.TOKEN_ASISTENTE),
    "marca": {"color_principal": COLOR_PRINCIPAL, "color_acento": COLOR_ACENTO},
    "pago": {"clabe": "002 010 07777777777 1", "beneficiario": "Mi negocio SA", "referencia_en": "ambos", "contacto_dudas": "55 1234 5678"},
    "reglas": {"texto_consentimiento": TEXTO_CONSTANCIA},
    "cortes": {"guardada": "on"},
}


class Formularios(Campos):
    def __init__(self):
        super().__init__(None)
        self.en_contenido = False

    def handle_starttag(self, etiqueta, atributos):
        if etiqueta == "main":
            self.en_contenido = True
        super().handle_starttag(etiqueta, atributos)
        if self.actual is None:
            return
        atributos = dict(atributos)
        tipo = (atributos.get("type") or "").lower()
        if etiqueta == "form":
            self.actual.update(botones=[], escribible=False, en_contenido=self.en_contenido)
        elif etiqueta == "button" and tipo in ("", "submit") or etiqueta == "input" and tipo == "submit":
            self.actual["botones"].append(atributos)
        elif etiqueta == "input" and (tipo or "text") in ESCRIBIBLES:
            self.actual["escribible"] = True

    def handle_endtag(self, etiqueta):
        super().handle_endtag(etiqueta)
        if etiqueta == "main":
            self.en_contenido = False


def formulario_de(html):
    lector = Formularios()
    lector.feed(html)
    candidatos = [f for f in lector.formularios if f["en_contenido"] and f["escribible"]]
    assert candidatos, "La pantalla no tiene un formulario donde Enter envíe"
    return candidatos[0]


def secreto_del_qr(html, usuario):
    clave = re.search(r'<code class="[^"]*clave-autenticador[^"]*">([^<]+)</code>', html)
    assert clave, "La pantalla del autenticador no muestra la clave"
    enlace = totp.uri(clave.group(1).replace(" ", ""), usuario, Negocio.objects.get().nombre)
    assert qr.svg(enlace) in html, "El QR de la pantalla no es el del enlace otpauth:// de la clave mostrada"
    return parse_qs(urlsplit(enlace).query)["secret"][0]


def llenar(paso, html, usuario):
    if paso == "usuario":
        return {"usuario": usuario, "nombre": f"Persona {usuario}", "contrasena1": CONTRASENA, "contrasena2": CONTRASENA}
    if paso == "codigo":
        return {"codigo": totp.codigo(secreto_del_qr(html, usuario), totp.paso_actual())}
    return DATOS.get(paso, {})


def enviar(c, paso, con_enter=False, boton=None, extra=None, usuario="jefa"):
    ruta = reverse(f"asistente:{paso}")
    pagina = c.get(ruta)
    assert pagina.status_code == 200, (paso, pagina.status_code, getattr(pagina, "url", ""))
    html = pagina.content.decode()
    formulario = formulario_de(html)
    datos = dict(formulario["datos"])
    datos.update(llenar(paso, html, usuario))
    datos.update(extra or {})
    if con_enter and formulario["botones"]:
        boton = formulario["botones"][0]
        if boton.get("name"):
            datos[boton["name"]] = boton.get("value") or ""
        ruta = boton.get("formaction") or formulario["accion"] or ruta
    elif boton:
        datos[boton[0]] = boton[1]
    return c.post(ruta, datos)


def destino(respuesta):
    return respuesta.url if respuesta.status_code == 302 else f"sin redirigir ({respuesta.status_code})"


def siguiente(paso):
    indice = PASOS.index(paso)
    return reverse(f"asistente:{PASOS[indice + 1]}") if indice + 1 < len(PASOS) else reverse("primeros_pasos")


def quedo_guardado(paso):
    if paso == "marca":
        actual = marca_negocio.actual()
        return bool(actual) and actual.color_principal == COLOR_PRINCIPAL
    if paso == "reglas":
        return parametro("texto_consentimiento") == TEXTO_CONSTANCIA
    if paso == "cortes":
        return not Negocio.objects.get().clave_recuperacion_pendiente
    return True


def configurado_por(usuario):
    persona = Usuario.objects.get(usuario=usuario)
    return Negocio.objects.get().configurado and persona.totp_confirmado


@pytest.mark.django_db
def test_enter_en_cada_paso_hace_la_accion_principal():
    c = Client()
    fallos = []
    for paso in PASOS:
        esperado = siguiente(paso)
        respuesta = enviar(c, paso, con_enter=True)
        if destino(respuesta) != esperado:
            fallos.append((paso, f"fue a {destino(respuesta)} y no a {esperado}"))
            respuesta = enviar(c, paso)
            assert destino(respuesta) == esperado, (paso, destino(respuesta))
        elif not quedo_guardado(paso):
            fallos.append((paso, "avanzó sin guardar: Enter omitió el paso"))
    assert not fallos, f"Enter no hizo la acción principal en: {fallos}"
    assert configurado_por("jefa")


@pytest.mark.django_db
def test_ida_y_vuelta_al_primer_usuario_conserva_el_qr():
    c = Client()
    c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE))
    assert destino(enviar(c, "usuario")) == reverse("asistente:codigo")
    primero = secreto_del_qr(c.get(reverse("asistente:codigo")).content.decode(), "jefa")
    for _ in range(2):
        assert destino(enviar(c, "codigo", boton=("atras", "1"), extra={"codigo": ""})) == reverse("asistente:usuario")
        assert destino(enviar(c, "usuario")) == reverse("asistente:codigo")
        assert secreto_del_qr(c.get(reverse("asistente:codigo")).content.decode(), "jefa") == primero, "El QR cambió al volver a «Primer usuario» con la misma persona"
    respuesta = enviar(c, "codigo", extra={"codigo": totp.codigo(primero, totp.paso_actual())})
    assert destino(respuesta) == reverse("primeros_pasos")
    assert configurado_por("jefa")


@pytest.mark.django_db
def test_instalacion_completa_solo_con_enter():
    c = Client()
    recorrido = []
    paso = "inicio"
    for _ in range(3 * len(PASOS)):
        recorrido.append(paso)
        respuesta = enviar(c, paso, con_enter=True)
        assert respuesta.status_code == 302, (recorrido, respuesta.status_code)
        if respuesta.url == reverse("primeros_pasos"):
            break
        paso = next(p for p in PASOS if reverse(f"asistente:{p}") == respuesta.url)
    else:
        pytest.fail(f"Con Enter la instalación no termina; ciclo: {' -> '.join(recorrido)}")
    assert recorrido == list(PASOS)
    assert configurado_por("jefa")


@pytest.mark.django_db
def test_otra_persona_en_primer_usuario_recibe_otro_secreto():
    c = Client()
    c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE))
    assert destino(enviar(c, "usuario", usuario="jefa")) == reverse("asistente:codigo")
    primero = secreto_del_qr(c.get(reverse("asistente:codigo")).content.decode(), "jefa")
    assert destino(enviar(c, "codigo", boton=("atras", "1"), extra={"codigo": ""}, usuario="jefa")) == reverse("asistente:usuario")
    assert destino(enviar(c, "usuario", usuario="otra")) == reverse("asistente:codigo")
    segundo = secreto_del_qr(c.get(reverse("asistente:codigo")).content.decode(), "otra")
    assert segundo != primero
    con_el_viejo = enviar(c, "codigo", extra={"codigo": totp.codigo(primero, totp.paso_actual())}, usuario="otra")
    assert destino(con_el_viejo) != reverse("primeros_pasos") and not Negocio.objects.get().configurado
    assert destino(enviar(c, "codigo", usuario="otra")) == reverse("primeros_pasos")
    assert configurado_por("otra")
