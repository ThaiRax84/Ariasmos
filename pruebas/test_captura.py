import importlib
import pkgutil
import re
from pathlib import Path

import pytest
from django import forms
from django.conf import settings

from cobros.formularios import CampoImporte, CampoPorcentaje
from cuentas.models import Usuario

from .conftest import nuevo_usuario

APLICACIONES = ("asistente", "auditoria", "banco", "caja", "cobros", "configuracion", "cuentas", "inventario", "solicitudes", "titulares")
EXTRA = {
    "FormularioColumnas": lambda: {"filas": [["fecha", "importe"], ["03/08/2026", "10"]], "encabezado": 0, "propuesta": {}},
    "FormularioDelegacion": lambda: {"otorgante": Usuario.objects.get(usuario="direccion")},
    "FormularioEntrega": lambda: {"origen": Usuario.objects.get(usuario="operacion")},
}
ATRIBUTO = re.compile(r'([a-zA-Z\-]+)="([^"]*)"')


def modulos():
    raiz = Path(settings.RAIZ) / "sistema"
    for aplicacion in APLICACIONES:
        if not (raiz / aplicacion).is_dir():
            continue
        paquete = importlib.import_module(aplicacion)
        for info in pkgutil.walk_packages(paquete.__path__, f"{aplicacion}."):
            if ".migrations" in info.name or ".management" in info.name or ".templatetags" in info.name:
                continue
            importlib.import_module(info.name)


def clases():
    modulos()
    vistas = set()
    pendientes = [forms.BaseForm]
    while pendientes:
        clase = pendientes.pop()
        for hija in clase.__subclasses__():
            pendientes.append(hija)
            if hija.__module__.split(".")[0] in APLICACIONES and not hija.__name__.startswith("_"):
                vistas.add(hija)
    return sorted(vistas, key=lambda c: (c.__module__, c.__name__))


def atributos(html):
    etiqueta = re.search(r"<(input|textarea)\b[^>]*>", html)
    return dict(ATRIBUTO.findall(etiqueta.group(0))) if etiqueta else {}


def campos_de(personas):
    for clase in clases():
        extra = EXTRA.get(clase.__name__, lambda: {})()
        formulario = clase(**extra)
        for campo in formulario.visible_fields():
            yield clase, campo


def test_todos_los_formularios_guian_la_captura(personas):
    revisados = 0
    faltan = []
    for clase, campo in campos_de(personas):
        definicion = campo.field
        html = str(campo)
        datos = atributos(html)
        nombre = f"{clase.__module__}.{clase.__name__}.{campo.name}"
        if isinstance(definicion, forms.CharField) and not isinstance(campo.field.widget, (forms.HiddenInput,)):
            revisados += 1
            if not datos.get("maxlength", "").isdigit():
                faltan.append(f"{nombre}: sin maxlength")
        if isinstance(definicion, CampoImporte) and (datos.get("data-acepta") != "dinero" or "adorno" not in html):
            faltan.append(f"{nombre}: dinero sin data-acepta o sin símbolo")
        if isinstance(definicion, CampoPorcentaje) and (datos.get("data-acepta") != "porcentaje" or ">%<" not in html):
            faltan.append(f"{nombre}: porcentaje sin data-acepta o sin %")
        if isinstance(definicion, forms.IntegerField) and datos.get("data-acepta") != "entero":
            faltan.append(f"{nombre}: entero sin data-acepta")
    assert revisados > 40
    assert not faltan, "\n".join(faltan)
