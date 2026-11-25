import json

import pytest
from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import Client
from django.urls import reverse

from configuracion.models import Negocio, parametro, vocabulario
from cortes import calendario
from cuentas.models import Usuario
from nucleo import totp
from pruebas.test_asistente import paso_inicio
from selladas.asistente.test_enter_y_autenticador import configurado_por, destino, enviar, secreto_del_qr

INICIO = reverse("asistente:inicio")
PASOS_INTERNOS = ("personalizar", "conceptos", "marca", "pago", "caja", "reglas", "cortes", "usuario", "codigo")
VOCABULARIO_PROPIO = {"titular": "Socio", "titulares": "Socios"}
CAJA_PROPIA = {"periodo_retiros": "semana", "corte_5": "14:00"}
ESPERADO = {**VOCABULARIO_PROPIO, "periodo_retiros": "semana", "corte_5": "14:00"}


def autorizar(c, token=None):
    return c.post(INICIO, paso_inicio(token or settings.TOKEN_ASISTENTE))


def recorrer(c, pasos, extras=None):
    for paso in pasos:
        respuesta = enviar(c, paso, extra=(extras or {}).get(paso))
        assert respuesta.status_code == 302 and respuesta.url != INICIO, (paso, destino(respuesta))


def perder_sesion(c):
    c.cookies.pop(settings.SESSION_COOKIE_NAME, None)


def personalizado():
    return {
        "titular": vocabulario()["titular"],
        "titulares": vocabulario()["titulares"],
        "periodo_retiros": parametro("periodo_retiros"),
        "corte_5": calendario.actual().get("5"),
    }


@pytest.mark.django_db
def test_sin_cookie_de_sesion_el_siguiente_paso_abre():
    c = Client()
    assert destino(autorizar(c)) == reverse("asistente:personalizar")
    recorrer(c, ("personalizar", "conceptos", "marca"))
    perder_sesion(c)
    respuesta = c.get(reverse("asistente:pago"))
    assert respuesta.status_code == 200, f"Sin la cookie de sesión «Datos de pago» fue a {destino(respuesta)}"


@pytest.mark.django_db
def test_volver_por_inicio_con_la_misma_plantilla_no_pisa_lo_personalizado():
    c = Client()
    autorizar(c)
    recorrer(c, ("personalizar", "conceptos", "marca", "pago", "caja"), {"personalizar": VOCABULARIO_PROPIO, "caja": CAJA_PROPIA})
    assert c.get(reverse("asistente:reglas")).status_code == 200
    assert personalizado() == ESPERADO
    c.cookies.clear()
    respuesta = autorizar(c)
    assert personalizado() == ESPERADO, f"Volver por «inicio» con la misma plantilla pisó lo personalizado: {personalizado()}"
    assert destino(respuesta) == reverse("asistente:reglas")


@pytest.mark.django_db
def test_otro_equipo_sin_token_no_entra_ni_cambia_nada():
    c = Client()
    autorizar(c)
    recorrer(c, ("personalizar", "conceptos"), {"personalizar": VOCABULARIO_PROPIO})
    otro = Client()
    intentos = {
        "personalizar": {"titular": "Intruso", "titulares": "Intrusos", "seguir": "continuar"},
        "caja": {"periodo_retiros": "mes", "corte_5": "09:00"},
        "reglas": {"texto_consentimiento": "Texto ajeno"},
        "usuario": {"usuario": "ajena", "nombre": "Persona ajena", "contrasena1": "Clave-ajena-12345", "contrasena2": "Clave-ajena-12345"},
        "codigo": {"codigo": "000000"},
    }
    antes = (personalizado(), parametro("texto_consentimiento"), Negocio.objects.get().nombre)
    for paso in PASOS_INTERNOS:
        ruta = reverse(f"asistente:{paso}")
        assert destino(otro.get(ruta)) == INICIO, (paso, "GET")
        assert destino(otro.post(ruta, intentos.get(paso, {}))) == INICIO, (paso, "POST")
    assert (personalizado(), parametro("texto_consentimiento"), Negocio.objects.get().nombre) == antes
    assert not Usuario.objects.exists()
    assert c.get(reverse("asistente:marca")).status_code == 200


@pytest.mark.django_db
def test_token_invalido_no_reanuda_ni_autoriza():
    c = Client()
    autorizar(c)
    recorrer(c, ("personalizar", "conceptos"), {"personalizar": VOCABULARIO_PROPIO})
    assert c.get(reverse("asistente:marca")).status_code == 200
    otro = Client()
    respuesta = autorizar(otro, token="token-equivocado")
    assert respuesta.status_code == 200, f"Con token inválido fue a {destino(respuesta)}"
    assert otro.get(INICIO).status_code == 200
    for paso in PASOS_INTERNOS:
        assert destino(otro.get(reverse(f"asistente:{paso}"))) == INICIO, paso
    assert vocabulario()["titular"] == "Socio" and Negocio.objects.get().nombre == "Mi negocio"
    assert c.get(reverse("asistente:marca")).status_code == 200


@pytest.mark.django_db
def test_secreto_sobrevive_sin_sesion_y_no_queda_en_claro():
    c = Client()
    autorizar(c)
    recorrer(c, ("personalizar", "conceptos", "marca", "pago", "caja", "reglas", "cortes", "usuario"))
    secreto = secreto_del_qr(c.get(reverse("asistente:codigo")).content.decode(), "jefa")
    perder_sesion(c)
    pagina = c.get(reverse("asistente:codigo"))
    assert pagina.status_code == 200, f"Sin la cookie de sesión «Autenticador» fue a {destino(pagina)}"
    assert secreto_del_qr(pagina.content.decode(), "jefa") == secreto, "El secreto cambió al perder la sesión"

    from configuracion.models import AvanceAsistente

    fila = AvanceAsistente.objects.get()
    campos = {campo.name: getattr(fila, campo.attname) for campo in AvanceAsistente._meta.concrete_fields}
    for nombre, valor in campos.items():
        texto = bytes(valor).decode("latin-1") if isinstance(valor, (bytes, memoryview)) else json.dumps(valor, default=str)
        assert secreto not in texto, f"El secreto está en claro en el campo «{nombre}» del avance"
    for sesion in Session.objects.all():
        assert secreto not in sesion.session_data and secreto not in json.dumps(sesion.get_decoded(), default=str), "El secreto está en claro en django_session"
    respuesta = c.post(reverse("asistente:codigo"), {"codigo": totp.codigo(secreto, totp.paso_actual())})
    assert destino(respuesta) == reverse("primeros_pasos")
    assert configurado_por("jefa")


@pytest.mark.django_db
def test_al_terminar_no_queda_avance_y_el_asistente_desaparece():
    c = Client()
    autorizar(c)
    recorrer(c, ("personalizar", "conceptos", "marca", "pago", "caja", "reglas", "cortes", "usuario", "codigo"))
    assert configurado_por("jefa")

    from configuracion.models import AvanceAsistente

    assert not AvanceAsistente.objects.exists(), "Quedó la fila de avance tras terminar"
    assert c.get("/asistente/").status_code == 404
    assert Client().get("/asistente/").status_code == 404
