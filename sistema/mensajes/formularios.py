from django import forms

from . import variables


class FormularioPlantilla(forms.Form):
    nombre = forms.CharField(
        label="Cómo la reconocerás", max_length=variables.LARGO_MAXIMO_NOMBRE
    )
    texto = forms.CharField(
        label="Texto del mensaje",
        max_length=variables.LARGO_MAXIMO_TEXTO,
        widget=forms.Textarea(attrs={"rows": 5}),
    )


class FormularioTope(forms.Form):
    tope = forms.IntegerField(
        label="Tope de mensajes al mes", min_value=1, max_value=1_000_000
    )
