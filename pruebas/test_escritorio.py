import re
from pathlib import Path

import pytest
from django.urls import reverse

from configuracion.formularios import FormularioAsistenteCortes, FormularioCarpetaBanco
from cortes.formularios import FormularioDestino
from proyecto import carpetas
from respaldos.views import FormularioCarpeta

from .conftest import cliente

RAIZ = Path(__file__).resolve().parents[1]
ESTATICOS = RAIZ / "sistema" / "estaticos"
NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"


def agente(version, modo="adicional"):
    return f"{NAVEGADOR} Ariasmos/{version} {modo}"


def test_botones_atras_y_adelante_en_la_barra(personas):
    pagina = cliente(personas["op"]).get(reverse("inicio")).content.decode()
    barra = pagina[pagina.index('<header class="barra">'):pagina.index("</header>")]
    assert barra.index("data-ir-atras") < barra.index('class="marcas"') and "data-ir-adelante" in barra
    assert 'data-navegacion hidden' in barra and 'aria-label="Atrás' in barra and 'aria-label="Adelante' in barra
    assert "js/escritorio.js" in pagina and "css/escritorio.css" in pagina
    codigo = (ESTATICOS / "js" / "escritorio.js").read_text(encoding="utf-8")
    for necesario in ("history.back()", "history.forward()", "canGoBack", "canGoForward", "currententrychange", "ArrowLeft", "ArrowRight", "evento.altKey", "evento.button === 3", "evento.button === 4", "irSiNadieMas", '"navigate"'):
        assert necesario in codigo, necesario
    hoja = (ESTATICOS / "css" / "escritorio.css").read_text(encoding="utf-8")
    assert ".flecha:disabled" in hoja and "border-radius: 999px" in hoja and ".flecha:focus-visible" in hoja


def test_el_puente_solo_manda_dos_mensajes():
    codigo = (ESTATICOS / "js" / "escritorio.js").read_text(encoding="utf-8")
    assert set(re.findall(r'tipo: "([a-z_]+)"', codigo)) == {"elegir_carpeta", "dar_permiso"}
    assert codigo.count("postMessage(") == 1 and "eval(" not in codigo and "innerHTML" not in codigo
    assert "Ariasmos\\/\\d+\\.\\d+\\.\\d+ principal" in codigo


def test_aviso_cuando_el_programa_de_la_computadora_es_viejo(personas):
    c = cliente(personas["op"])
    aviso = "es más viejo que el del servidor"
    assert aviso in c.get(reverse("inicio"), HTTP_USER_AGENT=agente("0.8.9")).content.decode()
    assert aviso in c.get(reverse("inicio"), HTTP_USER_AGENT=agente("0.0.1", "principal")).content.decode()
    for igual in (agente("9.0.0"), agente(open(RAIZ / "VERSION", encoding="utf-8").read().strip()), NAVEGADOR, NAVEGADOR + " Ariasmos/x.y.z adicional", ""):
        assert aviso not in c.get(reverse("inicio"), HTTP_USER_AGENT=igual).content.decode(), igual
    texto = c.get(reverse("inicio"), HTTP_USER_AGENT=agente("0.1.0") + "<script>").content.decode()
    assert "ver. 0.1.0" in texto and "<script>" not in texto.split("<main", 1)[1].split("</main>", 1)[0]


@pytest.mark.parametrize("clase, campos", [
    (FormularioDestino, ["ruta"]),
    (FormularioCarpetaBanco, ["carpeta_banco"]),
    (FormularioAsistenteCortes, ["carpeta_banco", "carpeta_entrega", "carpeta_respaldo"]),
    (FormularioCarpeta, ["carpeta_respaldo"]),
])
def test_campos_de_carpeta_llevan_examinar(clase, campos, db):
    formulario = clase()
    for campo in campos:
        html = str(formulario[campo])
        assert 'data-carpeta=""' in html and "data-sin-permiso" not in html, campo


def test_sin_permiso_marca_el_campo(tmp_path, monkeypatch, db):
    assert not carpetas.sin_permiso(str(tmp_path))
    assert not carpetas.sin_permiso("relativa")
    assert not carpetas.sin_permiso("\\\\servidor\\compartida")
    assert not carpetas.sin_permiso("//servidor/compartida")
    assert not carpetas.sin_permiso("")

    def negar(*args, **kwargs):
        raise PermissionError(13, "Acceso denegado")

    monkeypatch.setattr(Path, "write_bytes", negar)
    monkeypatch.setattr(Path, "mkdir", negar)
    assert carpetas.sin_permiso(str(tmp_path / "nueva" / "otra"))
    formulario = FormularioCarpeta({"carpeta_respaldo": str(tmp_path / "nueva")})
    assert not formulario.is_valid()
    assert "data-sin-permiso" in str(formulario["carpeta_respaldo"])
    assert "data-sin-permiso" not in str(FormularioCarpeta()["carpeta_respaldo"])
