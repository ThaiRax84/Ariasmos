from django import forms
from django.forms.boundfield import BoundField
from django.forms.renderers import DjangoTemplates
from django.utils.html import format_html

ENTRADA = {
    "digitos": "numeric",
    "matricula": "numeric",
    "dinero": "decimal",
    "porcentaje": "decimal",
    "entero": "numeric",
    "usuario": "text",
    "codigo_activacion": "text",
}


class CampoGuiado(BoundField):
    def build_widget_attrs(self, attrs, widget=None):
        attrs = super().build_widget_attrs(attrs, widget)
        campo = self.field
        acepta = getattr(campo, "acepta", None)
        if acepta is None and isinstance(campo, forms.IntegerField):
            acepta = "entero"
        if acepta:
            attrs.setdefault("data-acepta", acepta)
            attrs.setdefault("inputmode", ENTRADA[acepta])
        tecleo = getattr(campo, "maximo_tecleo", None)
        if tecleo:
            attrs["maxlength"] = str(tecleo)
        return attrs


class Renderizador(DjangoTemplates):
    bound_field_class = CampoGuiado


class EntradaAdornada(forms.TextInput):
    def adornos(self):
        return "", ""

    def render(self, name, value, attrs=None, renderer=None):
        entrada = super().render(name, value, attrs, renderer)
        izquierda, derecha = self.adornos()
        return format_html(
            '<span class="con-adorno">{}{}{}</span>',
            format_html('<span class="adorno" aria-hidden="true">{}</span>', izquierda) if izquierda else "",
            entrada,
            format_html('<span class="adorno" aria-hidden="true">{}</span>', derecha) if derecha else "",
        )


class EntradaDinero(EntradaAdornada):
    def adornos(self):
        from configuracion.moneda import actual

        moneda = actual()
        return moneda["simbolo"], moneda["codigo"]


class EntradaPorcentaje(EntradaAdornada):
    def adornos(self):
        return "", "%"


class CampoGuiadoTexto(forms.CharField):
    acepta = None
    maximo_tecleo = None

    def __init__(self, *args, acepta=None, maximo_tecleo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if acepta:
            self.acepta = acepta
        if maximo_tecleo:
            self.maximo_tecleo = maximo_tecleo


class CampoDigitos(CampoGuiadoTexto):
    acepta = "digitos"

    def to_python(self, valor):
        valor = super().to_python(valor)
        return "".join(valor.split()).replace("-", "") if valor else valor


class CampoUsuario(forms.RegexField):
    acepta = "usuario"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 60)
        kwargs.setdefault("error_messages", {"invalid": "Solo letras, números, punto, guion y guion bajo."})
        super().__init__(r"^[a-zA-Z0-9_.-]+$", *args, **kwargs)


class CampoContrasena(forms.CharField):
    def __init__(self, *args, autocompletar="current-password", enfocar=False, **kwargs):
        atributos = {"autocomplete": autocompletar}
        if enfocar:
            atributos["autofocus"] = True
        kwargs.setdefault("max_length", 128)
        kwargs.setdefault("strip", False)
        kwargs.setdefault("widget", forms.PasswordInput(attrs=atributos))
        super().__init__(*args, **kwargs)
