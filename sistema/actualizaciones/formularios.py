from django import forms

from .canales.github import clave_valida, repositorio_valido


class FormularioActualizaciones(forms.Form):
    activa = forms.BooleanField(label="Buscar actualizaciones del programa", required=False)
    repositorio = forms.CharField(label="Repositorio del canal (propietario/nombre)", max_length=140, required=False, widget=forms.TextInput(attrs={"autocomplete": "off", "spellcheck": "false"}))
    clave = forms.CharField(
        label="Clave de solo lectura del canal",
        max_length=300,
        required=False,
        strip=True,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="Se guarda cifrada y no se vuelve a mostrar. Déjala vacía para conservar la que ya está guardada.",
    )

    def __init__(self, *args, disponibles=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.disponibles = disponibles
        if not disponibles:
            self.fields["activa"].disabled = True
            self.fields["activa"].help_text = "Esta copia del programa no trae las llaves públicas de actualización: no se puede activar."

    def clean_repositorio(self):
        valor = self.cleaned_data.get("repositorio", "").strip()
        if valor and not repositorio_valido(valor):
            raise forms.ValidationError("Escribe el repositorio como propietario/nombre.")
        return valor

    def clean_clave(self):
        valor = self.cleaned_data.get("clave", "")
        if valor and not clave_valida(valor):
            raise forms.ValidationError("No tiene el formato de una clave de GitHub.")
        return valor
