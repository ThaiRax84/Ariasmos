import io
import re
from urllib.parse import parse_qs, urlparse

import pytest
import segno
from django.conf import settings
from django.test import Client
from django.urls import reverse
from pypdf import PdfReader

from auditoria.models import Evento
from caja.models import Denominacion
from cobros.formularios import FormularioRegla
from cobros.models import ConceptoCobro, ReglaRecargo
from configuracion import esquema, moneda, plantillas
from configuracion.models import Negocio, Parametro
from cuentas.models import Usuario
from cuentas.qr import agrupar
from nucleo import totp

from .conftest import CONTRASENA, cliente, codigo_actual
from .libro_ayudas import preparar_conceptos, titular_activo

ATRIBUTO = re.compile(r'([a-zA-Z\-]+)="([^"]*)"')


def entrada(html, nombre):
    etiqueta = re.search(rf'<input[^>]*name="{nombre}"[^>]*>', html)
    assert etiqueta, nombre
    return dict(ATRIBUTO.findall(etiqueta.group(0)))


def matriz_de_svg(svg):
    trazo = re.search(r'class="qrline"[^>]*d="([^"]+)"', svg).group(1)
    oscuros = set()
    x = y = 0.0
    for orden, a, b in re.findall(r"([Mmh])(-?[\d.]+)(?:\s(-?[\d.]+))?", trazo):
        if orden == "M":
            x, y = float(a), float(b)
        elif orden == "m":
            x, y = x + float(a), y + float(b)
        else:
            for paso in range(int(float(a))):
                oscuros.add((int(x) + paso, int(y)))
            x += float(a)
    return oscuros


def matriz_esperada(uri):
    codigo = segno.make(uri, error="m", micro=False)
    return {(columna + 4, fila + 4) for fila, renglon in enumerate(codigo.matrix) for columna, valor in enumerate(renglon) if valor}


def test_dinero_y_porcentaje_con_adornos_y_largos(personas):
    preparar_conceptos()
    c = cliente(personas["dir"])
    html = c.get(reverse("cobros:regla_nueva")).content.decode()
    importe = entrada(html, "valor_importe")
    porcentaje = entrada(html, "valor_porcentaje")
    assert importe["data-acepta"] == "dinero" and importe["inputmode"] == "decimal" and importe["maxlength"].isdigit()
    assert porcentaje["data-acepta"] == "porcentaje" and porcentaje["maxlength"] == "6"
    assert re.search(r'<span class="adorno"[^>]*>\$</span><input[^>]*name="valor_importe"[^>]*><span class="adorno"[^>]*>MXN</span>', html)
    assert re.search(r'<input[^>]*name="valor_porcentaje"[^>]*><span class="adorno"[^>]*>%</span>', html)
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    beca = c.get(reverse("cobros:beca", args=[ana.pk])).content.decode()
    assert entrada(beca, "porcentaje")["data-acepta"] == "porcentaje" and ">%</span>" in beca
    Negocio.objects.filter(pk=1).update(moneda="EUR")
    html = c.get(reverse("cobros:regla_nueva")).content.decode()
    assert ">€</span>" in html and ">EUR</span>" in html


def test_clabe_telefono_codigo_y_usuario_guiados(personas):
    c = cliente(personas["dir"])
    cuenta = c.get(reverse("banco:nueva")).content.decode()
    clabe = entrada(cuenta, "clabe")
    assert clabe["maxlength"] == "18" and clabe["data-acepta"] == "digitos" and clabe["inputmode"] == "numeric"
    alta = c.get(reverse("titulares:nuevo")).content.decode()
    telefono = re.search(r'<input[^>]*autocomplete="tel-national"[^>]*>', alta).group(0)
    assert 'maxlength="10"' in telefono and 'data-acepta="digitos"' in telefono
    Parametro.objects.update_or_create(clave="digitos_telefono_nacional", defaults={"valor": "8"})
    assert 'maxlength="8"' in re.search(r'<input[^>]*autocomplete="tel-national"[^>]*>', c.get(reverse("titulares:nuevo")).content.decode()).group(0)
    entrar = cliente().get(reverse("entrar")).content.decode()
    assert entrada(entrar, "usuario")["data-acepta"] == "usuario"
    activar = cliente().get(reverse("activar")).content.decode()
    assert entrada(activar, "codigo")["data-acepta"] == "codigo_activacion" and entrada(activar, "codigo")["maxlength"] == "11"
    nuevo = c.get(reverse("usuario_nuevo")).content.decode()
    assert entrada(nuevo, "usuario")["maxlength"] == "60"


def test_el_servidor_sigue_rechazando_lo_invalido(personas):
    preparar_conceptos()
    c = cliente(personas["dir"])
    for clabe in ("00201007777777777A", "0020100777777777711", "002010077777777772"):
        r = c.post(reverse("banco:nueva"), {"clabe": clabe, "beneficiario": "B", "referencia_en": "ambos", "contacto_dudas": "5512345678"})
        assert r.status_code == 200
    r = c.post(reverse("banco:nueva"), {"clabe": "002-010-07777777777-1", "beneficiario": "B", "referencia_en": "ambos", "contacto_dudas": "5512345678", "activa": "on"})
    assert r.status_code == 302
    base = {"nombre": "R", "tipo": "porcentaje", "dias_gracia": 0}
    assert c.post(reverse("cobros:regla_nueva"), {**base, "valor_importe": "100"}).status_code == 200
    assert c.post(reverse("cobros:regla_nueva"), {**base, "valor_porcentaje": "150"}).status_code == 200
    assert c.post(reverse("cobros:regla_nueva"), {**base, "tipo": "fijo", "valor_porcentaje": "10"}).status_code == 200
    assert c.post(reverse("cobros:regla_nueva"), {**base, "tipo": "fijo", "valor_importe": "12.345"}).status_code == 200
    assert not ReglaRecargo.objects.filter(nombre="R").exists()
    assert c.post(reverse("cobros:regla_nueva"), {**base, "valor_porcentaje": "12.5%"}).status_code == 302
    assert ReglaRecargo.objects.get(nombre="R").valor == 1250
    assert c.post(reverse("cobros:regla_nueva"), {**base, "nombre": "F", "tipo": "fijo", "valor_importe": "$1,200.50 MXN"}).status_code == 302
    assert ReglaRecargo.objects.get(nombre="F").valor == 120050
    formulario = FormularioRegla(instance=ReglaRecargo.objects.get(nombre="R"))
    assert 'value="12.50"' in str(formulario["valor_porcentaje"]) and not formulario["valor_importe"].value()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    url = reverse("titulares:contacto_nuevo", args=[ana.pk])
    nombre_tel = re.search(r'<input[^>]*autocomplete="tel-national"[^>]*>', c.get(url).content.decode()).group(0)
    nombre_tel = dict(ATRIBUTO.findall(nombre_tel))["name"]
    for malo in ("55abc12345", "551234567890123"):
        r = c.post(url, {"contacto_nombre": "X", nombre_tel: malo})
        assert r.status_code == 200 and "Teléfono no válido" in r.content.decode()


def test_moneda_por_defecto_cambio_antes_del_primer_cargo_y_bloqueo_despues(personas):
    negocio = Negocio.objects.get()
    assert negocio.moneda == "MXN" and moneda.codigo_actual() == "MXN"
    assert Denominacion.objects.filter(activa=True).exists()
    c = cliente(personas["dir"])
    pagina = c.get(reverse("configuracion:avanzado")).content.decode()
    assert '<option value="MXN" selected>' in pagina and "CLP" not in pagina
    assert c.post(reverse("configuracion:moneda"), {"moneda": "CLP"}).status_code == 200
    assert c.post(reverse("configuracion:moneda"), {"moneda": "USD"}).status_code == 302
    negocio.refresh_from_db()
    assert negocio.moneda == "USD" and not Denominacion.objects.filter(activa=True).exists()
    assert Evento.objects.filter(accion="moneda_cambiada").exists()
    assert "Faltan las denominaciones de caja" in c.get(reverse("inicio")).content.decode()
    preparar_conceptos()
    titular_activo(personas["op"], personas["sup"], "Ana")
    pagina = c.get(reverse("configuracion:avanzado")).content.decode()
    assert "la moneda quedó fija" in pagina and "Cambiar moneda" not in pagina
    c.post(reverse("configuracion:moneda"), {"moneda": "EUR"})
    negocio.refresh_from_db()
    assert negocio.moneda == "USD" and Evento.objects.filter(accion="moneda_rechazada").exists()


def test_importes_con_simbolo_y_codigo_en_pantalla_y_pdf(personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    c = cliente(personas["op"])
    assert "$1,000.00 MXN" in c.get(reverse("titulares:detalle", args=[ana.pk])).content.decode()
    texto = PdfReader(io.BytesIO(c.get(reverse("titulares:estado_pdf", args=[ana.pk])).content)).pages[0].extract_text()
    assert "$1,000.00 MXN" in texto
    Negocio.objects.filter(pk=1).update(moneda="CRC")
    assert "₡1,000.00 CRC" in c.get(reverse("titulares:detalle", args=[ana.pk])).content.decode()
    texto = PdfReader(io.BytesIO(c.get(reverse("titulares:estado_pdf", args=[ana.pk])).content)).pages[0].extract_text()
    assert "1,000.00 CRC" in texto
    ficha = c.get(reverse("titulares:ficha_pago", args=[ana.pk])).content.decode()
    assert "CRC" in ficha or "1,000.00" not in ficha


def test_plantilla_exportada_con_moneda_y_moneda_desconocida_rechazada(personas):
    Negocio.objects.filter(pk=1).update(moneda="PEN")
    datos = plantillas.exportar()
    assert datos["moneda"] == "PEN"
    for invalida in ("XXX", "CLP", 5, ""):
        with pytest.raises(esquema.PlantillaInvalida, match="moneda"):
            esquema.validar({**datos, "moneda": invalida})
    assert esquema.validar({k: v for k, v in datos.items() if k != "moneda"})["moneda"] == "MXN"
    Denominacion.objects.all().delete()
    plantillas.cargar("escuela")
    assert not Denominacion.objects.exists()
    Negocio.objects.filter(pk=1).update(moneda="MXN")
    plantillas.cargar("escuela")
    assert Denominacion.objects.count() == len(plantillas.leer("escuela")["denominaciones"])


@pytest.mark.django_db
def test_asistente_pregunta_la_moneda_con_mxn_preseleccionada():
    c = Client()
    pagina = c.get(reverse("asistente:inicio")).content.decode()
    assert '<option value="MXN" selected>' in pagina and 'name="moneda"' in pagina
    datos = {"token": settings.TOKEN_ASISTENTE, "nombre": "Mi negocio", "plantilla": "escuela", "zona_horaria": "America/Mexico_City", "moneda": "GTQ"}
    assert c.post(reverse("asistente:inicio"), datos).url == reverse("asistente:personalizar")
    assert Negocio.objects.get().moneda == "GTQ" and not Denominacion.objects.exists()
    assert c.post(reverse("asistente:inicio"), {**datos, "moneda": "ZZZ"}).status_code == 200


def test_textos_del_autenticador_y_qr_del_secreto_pendiente(personas, roles):
    sin = Usuario.objects.create_user("sintotp", CONTRASENA, nombre="Sin", rol=roles["Supervisión"])
    otro = Usuario.objects.create_user("otrotp", CONTRASENA, nombre="Otro", rol=roles["Supervisión"])
    c = cliente(sin)
    respuesta = c.get(reverse("totp"))
    pagina = respuesta.content.decode()
    secreto = c.session["totp_propuesto"]
    for texto in ("aplicación gratuita", "6 dígitos", "30 segundos", "Google Authenticator", "Microsoft Authenticator", "Authy", "2FAS", "TOTP", "Agregar cuenta", "Introducir clave manualmente", "Escanea este código con la aplicación; si no puedes, escribe la clave", "Negocio de prueba: sintotp"):
        assert texto in pagina, texto
    assert agrupar(secreto) in pagina and len(agrupar(secreto).split(" ")[0]) == 4
    assert respuesta["Cache-Control"] == "no-store"
    svg = re.search(r"<svg.*?</svg>", pagina, re.S).group(0)
    esperada = totp.uri(secreto, "sintotp", "Negocio de prueba")
    assert matriz_de_svg(svg) == matriz_esperada(esperada)
    assert parse_qs(urlparse(esperada).query)["secret"] == [secreto]
    c_otro = cliente(otro)
    pagina_otro = c_otro.get(reverse("totp")).content.decode()
    secreto_otro = c_otro.session["totp_propuesto"]
    assert secreto_otro != secreto and agrupar(secreto) not in pagina_otro
    assert matriz_de_svg(re.search(r"<svg.*?</svg>", pagina_otro, re.S).group(0)) != matriz_esperada(esperada)
    c.post(reverse("totp"), {"codigo": totp.codigo(secreto, totp.paso_actual())})
    sin.refresh_from_db()
    assert sin.totp_confirmado
    despues = c.get(reverse("totp")).content.decode()
    assert "<svg" not in despues and agrupar(secreto) not in despues and secreto not in despues


def test_pantalla_del_codigo_al_entrar_explica_el_autenticador(personas):
    c = Client()
    c.cookies[settings.COOKIE_DISPOSITIVO] = cliente().cookies[settings.COOKIE_DISPOSITIVO].value
    c.post(reverse("entrar"), {"usuario": personas["dir"].usuario, "contrasena": CONTRASENA})
    pagina = c.get(reverse("entrar_codigo")).content.decode()
    assert "Google Authenticator" in pagina and "30 segundos" in pagina
    codigo = entrada(pagina, "codigo")
    assert codigo["maxlength"] == "6" and codigo["data-acepta"] == "digitos"
    assert c.post(reverse("entrar_codigo"), {"codigo": " ".join([codigo_actual(personas["dir"])[:3], codigo_actual(personas["dir"])[3:]])}).status_code == 302


@pytest.mark.django_db
def test_asistente_paso_del_autenticador_con_qr_y_sin_qr_al_terminar():
    from .test_asistente import paso_inicio

    c = Client()
    c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE))
    c.post(reverse("asistente:usuario"), {"usuario": "jefa", "nombre": "Jefa", "contrasena1": CONTRASENA, "contrasena2": CONTRASENA})
    secreto = c.session["asistente"]["secreto"]
    pagina = c.get(reverse("asistente:codigo")).content.decode()
    assert "Google Authenticator" in pagina and agrupar(secreto) in pagina and "Mi negocio: jefa" in pagina
    svg = re.search(r"<svg.*?</svg>", pagina, re.S).group(0)
    assert matriz_de_svg(svg) == matriz_esperada(totp.uri(secreto, "jefa", "Mi negocio"))
    c.post(reverse("asistente:codigo"), {"codigo": totp.codigo(secreto, totp.paso_actual())})
    assert Negocio.objects.get().configurado
    respuesta = c.get(reverse("asistente:codigo"))
    assert respuesta.status_code in (302, 404) and b"<svg" not in respuesta.content
