from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django import forms

from cobros.formularios import CampoImporte
from cobros.models import ReglaRecargo
from cuentas.formularios import ContrasenaNueva
from nucleo.matricula import LONGITUD_MAX, LONGITUD_MIN
from titulares.models import Agrupacion, CampoContacto, MotivoBaja, RelacionContacto

from .models import PARAMETROS, VOCABULARIO_BASE, Negocio


def validar_zona(valor):
    try:
        ZoneInfo(valor)
    except (ZoneInfoNotFoundError, ValueError):
        raise forms.ValidationError("Zona horaria desconocida.")
    return valor


class FormularioNegocio(forms.ModelForm):
    class Meta:
        model = Negocio
        fields = ["nombre", "instrucciones_pago", "zona_horaria", "sede", "ranuras", "longitud_matricula"]
        labels = {
            "nombre": "Nombre del negocio",
            "instrucciones_pago": "Instrucciones de pago (cuenta, banco, CLABE; aparecen en la ficha)",
            "zona_horaria": "Zona horaria",
            "sede": "Número de sede",
            "ranuras": "Ranuras (sedes posibles)",
            "longitud_matricula": "Longitud de la matrícula",
        }
        widgets = {"instrucciones_pago": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.matriculas_emitidas:
            for campo in ("sede", "ranuras", "longitud_matricula"):
                self.fields[campo].disabled = True
                self.fields[campo].help_text = "Ya se emitieron matrículas; no se puede cambiar."

    def clean_zona_horaria(self):
        return validar_zona(self.cleaned_data["zona_horaria"])

    def clean(self):
        datos = super().clean()
        longitud, sede, ranuras = datos.get("longitud_matricula"), datos.get("sede"), datos.get("ranuras")
        if longitud is not None and not LONGITUD_MIN <= longitud <= LONGITUD_MAX:
            raise forms.ValidationError(f"La longitud debe estar entre {LONGITUD_MIN} y {LONGITUD_MAX}.")
        if ranuras is not None and ranuras < 1:
            raise forms.ValidationError("Debe haber al menos una ranura.")
        if sede is not None and ranuras is not None and sede >= ranuras:
            raise forms.ValidationError("La sede debe ser menor que el número de ranuras.")
        return datos


class FormularioVocabulario(forms.Form):
    def __init__(self, *args, textos=None, **kwargs):
        super().__init__(*args, **kwargs)
        etiquetas = {
            "titular": "Cómo se llama a cada titular (singular)",
            "titulares": "Plural",
            "matricula": "Cómo se llama la matrícula",
            "agrupacion": "Cómo se llama una agrupación (singular)",
            "agrupaciones": "Plural",
        }
        for clave in VOCABULARIO_BASE:
            self.fields[clave] = forms.CharField(label=etiquetas[clave], max_length=60, initial=(textos or VOCABULARIO_BASE)[clave])


class FormularioParametros(forms.Form):
    def __init__(self, *args, valores=None, **kwargs):
        super().__init__(*args, **kwargs)
        for clave, (defecto, descripcion) in PARAMETROS.items():
            self.fields[clave] = forms.IntegerField(label=descripcion, min_value=0, max_value=100000, initial=(valores or {}).get(clave, defecto))


class FormularioAgrupacion(forms.ModelForm):
    class Meta:
        model = Agrupacion
        fields = ["nombre", "activa"]


class FormularioMotivo(forms.ModelForm):
    class Meta:
        model = MotivoBaja
        fields = ["nombre", "activo"]


class FormularioRelacion(forms.ModelForm):
    class Meta:
        model = RelacionContacto
        fields = ["nombre", "activa"]


class FormularioCampoContacto(forms.ModelForm):
    class Meta:
        model = CampoContacto
        fields = ["etiqueta", "tipo", "obligatorio", "principal", "orden", "activo"]
        labels = {"obligatorio": "Obligatorio en el alta", "principal": "Medio principal para avisos"}

    def clean(self):
        datos = super().clean()
        if datos.get("principal") and not datos.get("activo"):
            raise forms.ValidationError("El medio principal debe estar activo.")
        if datos.get("obligatorio") and not datos.get("activo"):
            raise forms.ValidationError("Un campo obligatorio debe estar activo.")
        return datos


class FormularioAsistenteNegocio(FormularioNegocio):
    token = forms.CharField(label="Token de instalación (lo mostró el comando inicializar)", max_length=200, widget=forms.PasswordInput)
    plantilla = forms.ChoiceField(label="Plantilla inicial")

    class Meta(FormularioNegocio.Meta):
        pass

    def __init__(self, *args, plantillas=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plantilla"].choices = list((plantillas or {}).items())
        self.order_fields(["token", "nombre", "plantilla", "instrucciones_pago", "zona_horaria", "sede", "ranuras", "longitud_matricula"])


class FormularioAsistenteConceptos(forms.Form):
    def __init__(self, *args, conceptos=(), con_recargo=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.conceptos = list(conceptos)
        for concepto in self.conceptos:
            self.fields[f"importe_{concepto.pk}"] = CampoImporte(label=f"{concepto.nombre}: importe", required=False)
            if concepto.tipo == "recurrente":
                self.fields[f"dia_{concepto.pk}"] = forms.IntegerField(label=f"{concepto.nombre}: día de vencimiento (1 a 28)", min_value=1, max_value=28, required=False)
            if concepto.nombre in con_recargo:
                self.fields[f"recargo_tipo_{concepto.pk}"] = forms.ChoiceField(label=f"{concepto.nombre}: tipo de recargo", choices=ReglaRecargo.TIPOS)
                self.fields[f"recargo_valor_{concepto.pk}"] = CampoImporte(label=f"{concepto.nombre}: valor del recargo (importe o porcentaje)", required=False)
                self.fields[f"recargo_gracia_{concepto.pk}"] = forms.IntegerField(label=f"{concepto.nombre}: días de gracia", min_value=0, max_value=60, required=False)


class FormularioAsistenteUsuario(ContrasenaNueva):
    usuario = forms.RegexField(label="Usuario", max_length=60, regex=r"^[a-zA-Z0-9_.-]+$")
    nombre = forms.CharField(label="Nombre completo", max_length=150)
    field_order = ["usuario", "nombre", "contrasena1", "contrasena2"]
