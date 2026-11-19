import json

from django import forms
from django.utils.html import format_html, format_html_join

MARCADO = "on"


class ConDependencias:
    def _valor_control(self, nombre, vistos):
        campo = self.fields.get(nombre)
        if campo is None:
            return []
        if not self._aplica(nombre, vistos):
            return []
        valor = campo.widget.value_from_datadict(self.data, self.files, self.add_prefix(nombre))
        if isinstance(campo, forms.BooleanField):
            return [MARCADO] if campo.to_python(valor) else [""]
        if isinstance(valor, (list, tuple)):
            return [str(v) for v in valor]
        if valor is None:
            valor = self.initial.get(nombre, campo.initial)
            valor = valor() if callable(valor) else valor
            valor = getattr(valor, "pk", valor)
        return ["" if valor is None else str(valor)]

    def _aplica(self, nombre, vistos=None):
        regla = getattr(self.fields.get(nombre), "depende", None)
        if not regla:
            return True
        vistos = set(vistos or ())
        if nombre in vistos:
            return True
        vistos.add(nombre)
        if regla["valores"] is None:
            return True
        valores = self._valor_control(regla["de"], vistos)
        coincide = any(v in regla["valores"] for v in valores)
        return not coincide if regla["negar"] else coincide

    def aplica(self, nombre):
        return self._aplica(nombre)

    def _clean_fields(self):
        super()._clean_fields()
        for nombre, campo in self.fields.items():
            if getattr(campo, "depende", None) and not self._aplica(nombre):
                self._errors.pop(nombre, None)
                self.cleaned_data[nombre] = vacio(campo)


def vacio(campo):
    if isinstance(campo, forms.BooleanField):
        return False
    if isinstance(campo, (forms.MultipleChoiceField, forms.ModelMultipleChoiceField)):
        return []
    requerido = campo.required
    campo.required = False
    try:
        return campo.clean("")
    except forms.ValidationError:
        return None
    finally:
        campo.required = requerido


def _texto_opcion(control, valor):
    if isinstance(control, forms.BooleanField):
        return None
    for clave, texto in getattr(control, "choices", ()):
        if str(clave) == str(valor):
            return str(texto)
    return str(valor)


def _nota(formulario, control_nombre, valores, negar):
    control = formulario.fields.get(control_nombre)
    if control is None:
        return ""
    etiqueta = str(control.label or "").rstrip(":")
    if isinstance(control, forms.BooleanField):
        return f"Se usa cuando {'no ' if negar else ''}está marcado «{etiqueta}»."
    if valores is None:
        return ""
    opciones = [_texto_opcion(control, v) for v in valores]
    lista = " o ".join(f"«{o}»" for o in opciones if o)
    if not lista:
        return ""
    return f"Se usa cuando en «{etiqueta}» {'no ' if negar else ''}eliges {lista}."


def depende(formulario, nombre, de, valores=None, etiquetas=None, maximos=None, negar=False):
    if not isinstance(formulario, ConDependencias):
        raise TypeError(f"{type(formulario).__name__} declara dependencias sin ConDependencias")
    if nombre not in formulario.fields or de not in formulario.fields:
        return
    lista = None if valores is None else [str(v) for v in ([valores] if isinstance(valores, str) else valores)]
    if isinstance(formulario.fields[de], forms.BooleanField) and lista is None:
        lista = [MARCADO]
    formulario.fields[nombre].depende = {
        "de": de,
        "control": formulario.add_prefix(de),
        "valores": lista,
        "negar": negar,
        "etiquetas": {str(k): str(v) for k, v in (etiquetas or {}).items()},
        "maximos": {str(k): int(v) for k, v in (maximos or {}).items()},
        "nota": _nota(formulario, de, lista, negar),
    }


def segun(formulario, control, valores):
    for nombre, (valor, corta) in valores.items():
        depende(formulario, nombre, control, [valor], etiquetas={valor: corta} if corta else None)


def atributos(regla):
    if not regla:
        return ""
    pares = [("data-depende-de", regla["control"])]
    if regla["valores"] is not None:
        pares.append(("data-ocultar-si" if regla["negar"] else "data-mostrar-si", " ".join(regla["valores"])))
    if regla["etiquetas"]:
        pares.append(("data-etiquetas", json.dumps(regla["etiquetas"], ensure_ascii=False)))
    if regla["maximos"]:
        pares.append(("data-maximos", json.dumps(regla["maximos"])))
    return format_html_join("", ' {}="{}"', pares)


def nota(regla):
    if not regla or not regla.get("nota"):
        return ""
    return format_html('<small class="nota-dependencia" data-nota-dependencia>{}</small>', regla["nota"])


def declaradas(formulario):
    return {nombre: campo.depende for nombre, campo in formulario.fields.items() if getattr(campo, "depende", None)}
