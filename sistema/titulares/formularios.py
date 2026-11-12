from django import forms

from cobros.models import ConceptoCobro

from .contactos import FormularioContacto
from .models import Agrupacion, MotivoBaja, Titular


class FormularioTitular(forms.ModelForm):
    class Meta:
        model = Titular
        fields = ["nombre", "apellidos", "agrupacion", "notas"]
        widgets = {"notas": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, voc=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["agrupacion"].queryset = Agrupacion.objects.filter(activa=True)
        self.fields["agrupacion"].required = False
        if voc:
            self.fields["agrupacion"].label = voc["agrupacion"]


class FormularioAlta(FormularioContacto):
    nombre = forms.CharField(label="Nombre", max_length=100)
    apellidos = forms.CharField(label="Apellidos", max_length=150)
    agrupacion = forms.ModelChoiceField(label="Agrupación", queryset=Agrupacion.objects.none(), required=False)
    conceptos = forms.ModelMultipleChoiceField(label="Conceptos iniciales", queryset=ConceptoCobro.objects.none(), required=False, widget=forms.CheckboxSelectMultiple)
    notas = forms.CharField(label="Notas", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    constancia_consentimiento = forms.BooleanField(label="Se entregó el aviso de privacidad y se obtuvo el consentimiento", required=True)

    def __init__(self, *args, voc=None, **kwargs):
        super().__init__(*args, exigir_obligatorios=True, **kwargs)
        self.fields["agrupacion"].queryset = Agrupacion.objects.filter(activa=True)
        self.fields["conceptos"].queryset = ConceptoCobro.objects.filter(activo=True)
        if voc:
            self.fields["agrupacion"].label = voc["agrupacion"]
        orden = ["nombre", "apellidos", "agrupacion", "contacto_nombre", "contacto_relacion"]
        orden += [c.clave for c in self.campos]
        orden += ["conceptos", "notas", "constancia_consentimiento"]
        self.order_fields(orden)

    def datos_titular(self):
        datos = self.cleaned_data
        return {
            "nombre": datos["nombre"],
            "apellidos": datos["apellidos"],
            "agrupacion": datos.get("agrupacion"),
            "notas": datos.get("notas", ""),
            "constancia_consentimiento": datos["constancia_consentimiento"],
        }

    def datos_contacto(self):
        return {"nombre": self.cleaned_data["contacto_nombre"], "relacion": self.cleaned_data.get("contacto_relacion"), "valores": self.valores()}


class FormularioEditarContacto(FormularioContacto):
    contacto_principal = forms.BooleanField(label="Contacto principal", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, exigir_obligatorios=True, **kwargs)

    def datos_contacto(self):
        return {"nombre": self.cleaned_data["contacto_nombre"], "relacion": self.cleaned_data.get("contacto_relacion"), "valores": self.valores()}


class FormularioBaja(forms.Form):
    motivo = forms.ModelChoiceField(label="Motivo", queryset=MotivoBaja.objects.none())
    nota = forms.CharField(label="Nota", max_length=300, required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["motivo"].queryset = MotivoBaja.objects.filter(activo=True)


class FormularioNota(forms.Form):
    nota = forms.CharField(label="Nota", max_length=300, required=False, widget=forms.Textarea(attrs={"rows": 3}))
