import importlib
import re
from html.parser import HTMLParser

import pytest
from django import forms
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from caja.models import MotivoRetiro
from cobros.models import ConceptoCobro, ReglaRecargo
from cuentas.models import Usuario
from proyecto.dependencias import ConDependencias, depende
from rezagos.models import VALOR, ReglaRezago

from .conftest import cliente

MODULOS = (
    "actualizaciones.formularios",
    "banco.formularios",
    "banco.vistas_conciliacion",
    "caja.formularios",
    "cobros.formularios",
    "configuracion.formularios",
    "configuracion.vistas_padron",
    "cortes.formularios",
    "cuentas.formularios",
    "inventario.formularios",
    "respaldos.views",
    "rezagos.formularios",
    "solicitudes.formularios",
    "tarifas.formularios",
    "titulares.contactos",
    "titulares.formularios",
)
CONDICIONAL = re.compile(r"si elegiste|si eliges|si aplica|solo si|sólo si|\(si |si el tipo|si es en|solo recurrentes|obligatori[oa] si|obligatori[oa] con", re.IGNORECASE)


def clases():
    vistas = set()
    for nombre in MODULOS:
        modulo = importlib.import_module(nombre)
        for valor in vars(modulo).values():
            if isinstance(valor, type) and issubclass(valor, forms.BaseForm) and valor.__module__ == modulo.__name__ and valor not in vistas:
                vistas.add(valor)
    return sorted(vistas, key=lambda c: (c.__module__, c.__name__))


SIN_INSTANCIA = set()


def argumentos(clase):
    concepto = ConceptoCobro.objects.filter(tipo=ConceptoCobro.RECURRENTE).first()
    return {
        "FormularioTarifa": {"concepto": concepto},
        "FormularioEntrega": {"origen": Usuario.objects.first()},
        "FormularioAsistenteConceptos": {"conceptos": list(ConceptoCobro.objects.all()), "con_recargo": {c.nombre: {"tipo": "fijo"} for c in ConceptoCobro.objects.all()}},
        "FormularioPersonalizar": {"conceptos": list(ConceptoCobro.objects.all())},
        "FormularioExcepcion": {"existente": True},
        "FormularioColumnas": {"filas": [["Fecha", "Importe"], ["01/01/2026", "100"]]},
        "FormularioDelegacion": {"otorgante": Usuario.objects.first()},
    }.get(clase.__name__, {})


def instanciar(clase):
    try:
        return clase(**argumentos(clase))
    except (TypeError, AttributeError, KeyError):
        return None


def test_todo_formulario_sin_etiqueta_condicional_sin_dependencia(personas):
    revisados, sin_instancia, malos = 0, [], []
    for clase in clases():
        formulario = instanciar(clase)
        if formulario is None:
            sin_instancia.append(clase.__name__)
            continue
        revisados += 1
        for nombre, campo in formulario.fields.items():
            texto = f"{campo.label or ''} {campo.help_text or ''}"
            if CONDICIONAL.search(texto) and not getattr(campo, "depende", None):
                malos.append(f"{clase.__name__}.{nombre}: {texto.strip()}")
            if getattr(campo, "depende", None):
                assert isinstance(formulario, ConDependencias), clase.__name__
                assert campo.depende["de"] in formulario.fields, (clase.__name__, nombre)
    assert revisados > 60
    assert not malos, malos
    assert set(sin_instancia) <= SIN_INSTANCIA, sin_instancia


class Campos(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pila = []
        self.campos = []
        self.actual = None
        self.en_nota = 0

    def handle_starttag(self, etiqueta, atributos):
        atributos = dict(atributos)
        if etiqueta == "div":
            depende = "data-depende-de" in atributos or any(d for d in self.pila if d)
            self.pila.append(depende)
            if "campo" in (atributos.get("class") or "").split():
                self.actual = {"depende": depende, "texto": "", "nivel": len(self.pila)}
                self.campos.append(self.actual)
        if etiqueta == "small" and "data-nota-dependencia" in atributos:
            self.en_nota += 1

    def handle_endtag(self, etiqueta):
        if etiqueta == "div" and self.pila:
            if self.actual is not None and self.actual["nivel"] == len(self.pila):
                self.actual = None
            self.pila.pop()
        if etiqueta == "small" and self.en_nota:
            self.en_nota -= 1

    def handle_data(self, datos):
        if self.actual is not None and not self.en_nota:
            self.actual["texto"] += datos


def rutas_sin_argumentos(patrones=None, prefijo=""):
    for patron in patrones if patrones is not None else get_resolver().url_patterns:
        if isinstance(patron, URLResolver):
            espacio = f"{patron.namespace}:" if patron.namespace else ""
            yield from rutas_sin_argumentos(patron.url_patterns, prefijo + espacio)
        elif isinstance(patron, URLPattern) and patron.name and not patron.pattern.regex.groups:
            yield prefijo + patron.name


EXCLUIDAS = {"salir", "respaldos:clave", "configuracion:exportar"}


def test_pantallas_sin_etiquetas_condicionales_sueltas(personas):
    c = cliente(personas["dir"])
    malos, vistas = [], 0
    rutas = [r for r in rutas_sin_argumentos() if r not in EXCLUIDAS and not r.startswith("asistente:")]
    regla = ReglaRecargo.objects.create(nombre="Regla", tipo="fijo", valor=100)
    concepto = ConceptoCobro.objects.filter(tipo=ConceptoCobro.RECURRENTE).first()
    extra = [reverse("cobros:regla_editar", args=[regla.pk]), reverse("cobros:concepto_editar", args=[concepto.pk]), reverse("tarifas:concepto", args=[concepto.pk]), reverse("tarifas:nueva", args=[concepto.pk])]
    for ruta in [reverse(r) for r in rutas] + extra:
        respuesta = c.get(ruta)
        assert respuesta.status_code < 500, ruta
        if respuesta.status_code != 200 or "text/html" not in respuesta.get("Content-Type", ""):
            continue
        vistas += 1
        lector = Campos()
        lector.feed(respuesta.content.decode())
        for campo in lector.campos:
            if CONDICIONAL.search(campo["texto"]) and not campo["depende"]:
                malos.append((ruta, " ".join(campo["texto"].split())[:120]))
    assert vistas > 40
    assert not malos, malos


def test_limites_ignoran_el_valor_cuando_es_ilimitado(roles):
    from rezagos.formularios import FormularioLimites

    formulario = FormularioLimites({"modo_importe": "ilimitado", "importe_maximo": "basura", "modo_dias": VALOR, "dias_maximos": "10"})
    assert formulario.is_valid(), formulario.errors
    assert formulario.cleaned_data["importe_maximo"] == 0 and formulario.cleaned_data["dias_maximos"] == 10
    otro = FormularioLimites({"modo_importe": VALOR, "importe_maximo": "", "modo_dias": "ilimitado", "dias_maximos": "x"})
    assert not otro.is_valid() and "importe_maximo" in otro.errors and "dias_maximos" not in otro.errors
    campo = FormularioLimites()["importe_maximo"]
    html = str(campo.field.depende)
    assert "modo_importe" in html


def test_regla_de_rezago_solo_valida_el_campo_del_alcance_elegido(roles):
    from rezagos.formularios import FormularioRegla

    base = {"nombre": "R", "texto": "Aviso", "dias_minimos": "5", "aviso_inicio": "on", "activa": "on"}
    todos = FormularioRegla({**base, "alcance": ReglaRezago.TODOS, "matricula": "no-existe", "agrupacion": "999"})
    assert todos.is_valid(), todos.errors
    assert todos.cleaned_data["agrupacion"] is None and todos.cleaned_data["titular"] is None
    por_persona = FormularioRegla({**base, "alcance": ReglaRezago.TITULAR, "matricula": "123"})
    assert not por_persona.is_valid() and "matricula" in por_persona.errors


def test_las_dependencias_se_dibujan_como_atributos_y_nota_sin_js(personas):
    pagina = cliente(personas["dir"]).get(reverse("rezagos:regla_nueva")).content.decode()
    assert 'data-depende-de="alcance" data-mostrar-si="agrupacion"' in pagina
    assert 'data-depende-de="alcance" data-mostrar-si="titular"' in pagina
    assert "data-nota-dependencia" in pagina and "Se usa cuando en «A quién aplica» eliges" in pagina
    limites = cliente(personas["dir"]).get(reverse("rezagos:limites")).content.decode()
    assert 'data-depende-de="modo_importe" data-mostrar-si="valor"' in limites
    concepto = cliente(personas["dir"]).get(reverse("cobros:concepto_nuevo")).content.decode()
    assert 'data-depende-de="tipo" data-mostrar-si="recurrente"' in concepto and "data-maximos=" in concepto and "data-etiquetas=" in concepto


def test_dependencias_encadenadas_y_valor_de_fabrica(roles):
    from cobros.formularios import FormularioConcepto

    datos = {"nombre": "Cuota", "tipo": ConceptoCobro.UNICO, "importe_centavos": "100", "periodicidad": "semanal", "dia_vencimiento": "99", "aplica_a": "manual", "prioridad": "1", "activo": "on"}
    formulario = FormularioConcepto(datos)
    assert formulario.is_valid(), formulario.errors
    assert formulario.cleaned_data["periodicidad"] == "" and formulario.cleaned_data["dia_vencimiento"] is None
    recurrente = FormularioConcepto({**datos, "tipo": ConceptoCobro.RECURRENTE})
    assert not recurrente.is_valid()
    assert FormularioConcepto({**datos, "tipo": ConceptoCobro.RECURRENTE, "dia_vencimiento": "7"}).is_valid()


def test_declarar_sin_el_mecanismo_falla(roles):
    class Suelto(forms.Form):
        tipo = forms.ChoiceField(choices=[("a", "A")])
        valor = forms.CharField()

    with pytest.raises(TypeError):
        depende(Suelto(), "valor", "tipo", ["a"])


def test_devolucion_pide_piezas_solo_en_efectivo(personas):
    from inventario.formularios import FormularioDevolucion

    formulario = FormularioDevolucion()
    piezas = [n for n, c in formulario.fields.items() if getattr(c, "pieza", None)]
    assert piezas and all(formulario.fields[n].depende["valores"] == ["efectivo"] for n in piezas)
    assert "solo si" not in " ".join(str(formulario.fields[n].label) for n in piezas)


def test_motivo_de_retiro_existe(roles):
    assert MotivoRetiro.objects.exists()
