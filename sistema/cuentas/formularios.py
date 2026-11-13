from django import forms
from django.contrib.auth import password_validation

from configuracion.models import parametro
from proyecto.captura import CampoContrasena, CampoDigitos, CampoGuiadoTexto, CampoUsuario

from .models import Rol, Usuario
from .permisos import DELEGABLES, PERMISOS


class FormularioEntrar(forms.Form):
    usuario = CampoUsuario(label="Usuario", widget=forms.TextInput(attrs={"autocomplete": "username", "autofocus": True}))
    contrasena = CampoContrasena(label="Contraseña")


class FormularioCodigo(forms.Form):
    codigo = CampoDigitos(label="Código de 6 dígitos", max_length=10, maximo_tecleo=6, widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "autofocus": True}))


class FormularioConfirmar(forms.Form):
    contrasena = CampoContrasena(label="Tu contraseña", enfocar=True)


class ContrasenaNueva(forms.Form):
    contrasena1 = CampoContrasena(label="Contraseña nueva", autocompletar="new-password")
    contrasena2 = CampoContrasena(label="Repite la contraseña", autocompletar="new-password")

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario_objetivo = usuario
        super().__init__(*args, **kwargs)

    def clean(self):
        datos = super().clean()
        uno, dos = datos.get("contrasena1"), datos.get("contrasena2")
        if uno and dos and uno != dos:
            raise forms.ValidationError("Las contraseñas no coinciden.")
        if uno:
            password_validation.validate_password(uno, self.usuario_objetivo)
        return datos


class FormularioCambioPropio(ContrasenaNueva):
    actual = CampoContrasena(label="Contraseña actual")
    field_order = ["actual", "contrasena1", "contrasena2"]

    def clean_actual(self):
        valor = self.cleaned_data["actual"]
        if not self.usuario_objetivo.check_password(valor):
            raise forms.ValidationError("La contraseña actual no es correcta.")
        return valor


class FormularioUsuarioNuevo(forms.Form):
    usuario = CampoUsuario(label="Usuario")
    nombre = forms.CharField(label="Nombre completo", max_length=150)
    rol = forms.ModelChoiceField(label="Rol", queryset=Rol.objects.all())

    def clean_usuario(self):
        valor = self.cleaned_data["usuario"]
        if Usuario.objects.filter(usuario__iexact=valor).exists():
            raise forms.ValidationError("Ese usuario ya existe.")
        return valor


class FormularioUsuarioEditar(forms.ModelForm):
    restablecer_acceso = forms.BooleanField(label="Restablecer acceso: invalida su contraseña y sus sesiones y genera un código de activación", required=False)
    desbloquear = forms.BooleanField(label="Quitar bloqueo por intentos", required=False)
    reiniciar_totp = forms.BooleanField(label="Reiniciar autenticador (deberá darlo de alta otra vez)", required=False)

    class Meta:
        model = Usuario
        fields = ["nombre", "rol", "activo"]

class FormularioActivacion(ContrasenaNueva):
    usuario = CampoUsuario(label="Usuario", widget=forms.TextInput(attrs={"autocomplete": "username", "autofocus": True}))
    codigo = CampoGuiadoTexto(label="Código de activación", max_length=20, acepta="codigo_activacion", maximo_tecleo=11, widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "characters"}))
    field_order = ["usuario", "codigo", "contrasena1", "contrasena2"]


class FormularioRol(forms.ModelForm):
    permisos = forms.MultipleChoiceField(label="Permisos", choices=list(PERMISOS.items()), required=False, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Rol
        fields = ["nombre", "nivel", "minutos_inactividad", "requiere_totp"]
        labels = {
            "nivel": "Nivel",
            "minutos_inactividad": "Minutos de inactividad antes de cerrar sesión",
            "requiere_totp": "Exigir autenticador (obligatorio si aprueba)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["permisos"] = sorted(self.instance.permisos())

    def clean(self):
        datos = super().clean()
        if "aprobar_solicitudes" in datos.get("permisos", []) and not datos.get("requiere_totp"):
            raise forms.ValidationError("Un rol que aprueba solicitudes debe exigir el autenticador.")
        if datos.get("minutos_inactividad") is not None and not 1 <= datos["minutos_inactividad"] <= 720:
            raise forms.ValidationError("Los minutos de inactividad deben estar entre 1 y 720.")
        return datos


class FormularioAprobarDispositivo(forms.Form):
    nombre = forms.CharField(label="Nombre del equipo", max_length=100)


class FormularioDelegacion(forms.Form):
    receptor = forms.ModelChoiceField(label="Persona", queryset=Usuario.objects.none())
    permiso = forms.ChoiceField(label="Permiso")
    dias = forms.IntegerField(label="Días de vigencia", required=False, min_value=1)
    usos = forms.IntegerField(label="Número de usos", required=False, min_value=1, max_value=1000)
    motivo = forms.CharField(label="Motivo", max_length=200, required=False)

    def __init__(self, *args, otorgante=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.otorgante = otorgante
        self.fields["receptor"].queryset = Usuario.objects.filter(activo=True).exclude(pk=otorgante.pk)
        self.fields["permiso"].choices = [(p, PERMISOS[p]) for p in DELEGABLES if otorgante.tiene_permiso_de_rol(p)]
        self.fields["dias"].max_value = parametro("dias_maximos_delegacion")
        self.fields["dias"].help_text = f"Máximo {parametro('dias_maximos_delegacion')} días."

    def clean(self):
        datos = super().clean()
        if not datos.get("dias") and not datos.get("usos"):
            raise forms.ValidationError("Indica los días de vigencia, el número de usos o ambos.")
        if datos.get("dias") and datos["dias"] > parametro("dias_maximos_delegacion"):
            raise forms.ValidationError("La vigencia supera el máximo permitido.")
        return datos


class FormularioRevision(forms.Form):
    decision = forms.ChoiceField(choices=[("confirmar", "Confirmar"), ("reportar", "Reportar")])


