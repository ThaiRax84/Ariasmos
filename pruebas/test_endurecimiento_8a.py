import pytest
from django.test import Client
from django.urls import reverse

from cortes import entrega
from envios.middleware import CAMPO, nueva_ficha
from envios.models import EnvioUsado


@pytest.mark.parametrize("ruta", ["\\\\servidor\\compartida", "\\\\10.0.0.5\\c$\\datos", "//servidor/compartida", "\\\\?\\UNC\\servidor\\x", "\\\\.\\pipe\\algo"])
def test_las_carpetas_de_red_se_rechazan_sin_tocarlas(ruta, monkeypatch):
    tocadas = []
    monkeypatch.setattr(entrega.Path, "resolve", lambda self, *a, **k: tocadas.append(self) or self)
    with pytest.raises(entrega.ErrorEntrega, match="red"):
        entrega.validar_ruta(ruta)
    assert tocadas == []


@pytest.mark.django_db
def test_sin_sesion_no_se_guardan_fichas_de_envio():
    c = Client()
    for _ in range(20):
        c.post(reverse("entrar"), {"usuario": "nadie", "password": "x", CAMPO: nueva_ficha()})
    assert EnvioUsado.objects.count() == 0
