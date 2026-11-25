import json
import re

from django.urls import reverse

from auditoria.models import Evento
from configuracion import marca
from configuracion.models import MarcaNegocio
from pruebas.conftest import cliente
from pruebas.test_interfaz import limpio  # noqa: F401  borra la caché de /marca.css entre pruebas

PRINCIPAL, ACENTO = "#2B4A1F", "#C4662E"
CLARO, OSCURO = "#F8E16C", "#1F1A4E"
PRIMARIO_ARIASMOS = "#9E431C"
TEXTO_OSCURO = "#1F1813"
MALOS = ("red;}body{display:none}", "#12345", "#1234567", "url(javascript:1)", "#FFF", "red", "#1F1A\n4E", "#1F1A4E\n}body{display:none}", "#1F1A4E;\r\n--x:url(a)")


def texto_esperado(fondo):
    return "#FFFFFF" if marca.contraste("#FFFFFF", fondo) >= 4.5 else TEXTO_OSCURO


def guardar_barra(c, opcion, color=""):
    actual = MarcaNegocio.objects.get()
    return c.post(reverse("configuracion:marca"), {"accion": "colores", "color_principal": actual.color_principal, "color_acento": actual.color_acento, "barra": opcion, "color_barra": color})


def hoja(c):
    actual = marca.actual()
    return c.get(reverse("marca_css") + f"?v={actual.version if actual else 0}").content.decode()


def variable(texto, nombre):
    valores = re.findall(rf"{nombre}:\s*([^;]*);", texto)
    assert len(valores) == 1, f"{nombre} aparece {len(valores)} veces en /marca.css:\n{texto}"
    return valores[0]


def barra_de(texto):
    valor = variable(texto, "--barra")
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", valor), repr(valor)
    return valor.upper(), variable(texto, "--barra-texto").upper()


def test_color_inyectado_no_se_guarda_ni_llega_a_la_hoja(personas, limpio):  # noqa: F811
    marca.guardar_colores(PRINCIPAL, ACENTO, personas["dir"])
    c = cliente(personas["dir"])
    hoja(c)
    for malo in MALOS:
        antes = MarcaNegocio.objects.get()
        respuesta = guardar_barra(c, "otro", malo)
        despues = MarcaNegocio.objects.get()
        assert respuesta.status_code != 302 and despues.version == antes.version, f"Se aceptó {malo!r}"
        assert getattr(despues, "color_barra", "") == ""
    texto = hoja(c)
    assert "display:none" not in texto and "url(" not in texto
    assert barra_de(texto)[0] == PRINCIPAL


def test_sin_permiso_no_cambia_el_color_de_la_barra(personas, limpio):  # noqa: F811
    marca.guardar_colores(PRINCIPAL, ACENTO, personas["dir"])
    for persona in ("op", "sup"):
        c = cliente(personas[persona])
        for accion in ("colores", "barra", "color_barra", ""):
            antes = MarcaNegocio.objects.get().version
            respuesta = c.post(reverse("configuracion:marca"), {"accion": accion, "color_principal": PRINCIPAL, "color_acento": ACENTO, "barra": "otro", "color_barra": CLARO})
            assert respuesta.status_code == 403 or MarcaNegocio.objects.get().version == antes, (persona, accion)
    assert getattr(MarcaNegocio.objects.get(), "color_barra", "") == ""
    assert CLARO not in hoja(cliente(personas["op"]))


def test_por_omision_principal_y_el_cambio_se_ve_al_instante(personas, limpio):  # noqa: F811
    c = cliente(personas["dir"])
    sin_marca = barra_de(hoja(c))
    assert sin_marca == (PRIMARIO_ARIASMOS, texto_esperado(PRIMARIO_ARIASMOS))
    marca.guardar_colores(PRINCIPAL, ACENTO, personas["dir"])
    assert barra_de(hoja(c))[0] == PRINCIPAL
    assert MarcaNegocio.objects.get().color_barra == ""
    ultimo = Evento.objects.order_by("-numero").values_list("numero", flat=True).first()
    assert guardar_barra(c, "otro", CLARO.lower()).status_code == 302
    assert MarcaNegocio.objects.get().color_barra == CLARO
    assert barra_de(hoja(c))[0] == CLARO, "/marca.css sirve la barra vieja"
    assert f'href="{reverse("marca_css")}?v={MarcaNegocio.objects.get().version}"' in c.get(reverse("inicio")).content.decode()
    eventos = Evento.objects.filter(numero__gt=ultimo)
    assert any("antes" in e.datos and CLARO in json.dumps(e.datos.get("despues")) and CLARO not in json.dumps(e.datos["antes"]) for e in eventos), "El cambio no quedó en la bitácora con antes y después"
    assert guardar_barra(c, "principal", OSCURO).status_code == 302
    assert MarcaNegocio.objects.get().color_barra == ""
    assert barra_de(hoja(c))[0] == PRINCIPAL


def test_texto_de_la_barra_legible(personas, limpio):  # noqa: F811
    marca.guardar_colores(PRINCIPAL, ACENTO, personas["dir"])
    c = cliente(personas["dir"])
    assert guardar_barra(c, "otro", CLARO).status_code == 302
    assert barra_de(hoja(c)) == (CLARO, TEXTO_OSCURO)
    assert guardar_barra(c, "otro", OSCURO).status_code == 302
    assert barra_de(hoja(c)) == (OSCURO, "#FFFFFF")
    for fondo, texto in ((CLARO, TEXTO_OSCURO), (OSCURO, "#FFFFFF")):
        assert marca.contraste(texto, fondo) >= 4.5
