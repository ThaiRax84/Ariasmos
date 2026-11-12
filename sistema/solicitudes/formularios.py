from django import forms

from .models import PoliticaAccion


class FormularioCodigoTelefono(forms.Form):
    autorizador = forms.ChoiceField(label="¿Quién autoriza?")
    codigo = forms.CharField(label="Código de 6 dígitos que te dictó", max_length=10, widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off"}))

    def __init__(self, *args, autorizadores=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.autorizadores = {str(u.pk): u for u in autorizadores}
        self.fields["autorizador"].choices = [(str(u.pk), u.nombre) for u in autorizadores]

    def usuario_autorizador(self):
        return self.autorizadores[self.cleaned_data["autorizador"]]


class FormularioRechazo(forms.Form):
    nota = forms.CharField(label="Motivo del rechazo", max_length=300, required=False)


class FormularioPolitica(forms.ModelForm):
    class Meta:
        model = PoliticaAccion
        fields = ["permiso_directo", "permiso_solicitar", "permiso_aprobar", "horas_caducidad", "horas_resaltar", "permite_delegacion", "permite_codigo"]
        labels = {
            "permiso_directo": "Permiso para ejecutar directo",
            "permiso_solicitar": "Permiso para solicitar",
            "permiso_aprobar": "Permiso para aprobar",
            "horas_caducidad": "Horas antes de caducar",
            "horas_resaltar": "Horas antes de resaltar en la bandeja",
            "permite_delegacion": "Admite delegación temporal",
            "permite_codigo": "Admite código por teléfono",
        }

    def clean(self):
        datos = super().clean()
        if datos.get("horas_caducidad") is not None and datos["horas_caducidad"] < 1:
            raise forms.ValidationError("La caducidad debe ser de al menos una hora.")
        return datos
