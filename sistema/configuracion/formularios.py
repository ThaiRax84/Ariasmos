from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django import forms

from banco.models import MedioPago
from cobros.formularios import CampoImporte
from cobros.models import ConceptoCobro, ReglaRecargo
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
        fields = ["nombre", "zona_horaria", "nota_ficha"]
        labels = {
            "nombre": "Nombre del negocio",
            "zona_horaria": "Zona horaria",
            "nota_ficha": "Nota de la ficha mientras no haya cuenta principal",
        }
        widgets = {"nota_ficha": forms.Textarea(attrs={"rows": 3})}

    def clean_zona_horaria(self):
        return validar_zona(self.cleaned_data["zona_horaria"])


class FormularioAjustesAvanzados(forms.ModelForm):
    class Meta:
        model = Negocio
        fields = ["longitud_matricula", "sede", "ranuras"]
        labels = {"longitud_matricula": "Longitud de la matrícula", "sede": "Número de sede", "ranuras": "Ranuras (sedes posibles)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.matriculas_emitidas:
            for campo in self.fields.values():
                campo.disabled = True

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


class FormularioMedioPago(forms.ModelForm):
    class Meta:
        model = MedioPago
        fields = ["nombre", "orden", "activo"]


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


IMPORTAR = "importar"


class FormularioAsistenteInicio(forms.Form):
    token = forms.CharField(label="Token de instalación (lo mostró el comando inicializar)", max_length=200, widget=forms.PasswordInput)
    nombre = forms.CharField(label="Nombre del negocio", max_length=150)
    zona_horaria = forms.CharField(label="Zona horaria", max_length=64, initial="America/Mexico_City")
    plantilla = forms.ChoiceField(label="Plantilla inicial", widget=forms.RadioSelect)
    archivo = forms.FileField(label="Archivo de plantilla (solo si eliges importar; JSON de hasta 256 KB)", required=False)

    def __init__(self, *args, plantillas=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plantilla"].choices = list((plantillas or {}).items()) + [(IMPORTAR, "Importar un archivo de plantilla")]

    def clean_zona_horaria(self):
        return validar_zona(self.cleaned_data["zona_horaria"])

    def clean(self):
        datos = super().clean()
        if datos.get("plantilla") == IMPORTAR and not datos.get("archivo"):
            self.add_error("archivo", "Elige el archivo de plantilla que quieres importar.")
        return datos


class FormularioPersonalizar(forms.Form):
    nuevo_nombre = forms.CharField(label="Agregar concepto: nombre", max_length=100, required=False)
    nuevo_tipo = forms.ChoiceField(label="Tipo", choices=ConceptoCobro.TIPOS, required=False)
    nuevo_periodicidad = forms.ChoiceField(label="Periodicidad (solo recurrentes)", choices=[("", "—")] + ConceptoCobro.PERIODICIDADES, required=False)
    nuevo_aplica_a = forms.ChoiceField(label="Aplica a", choices=[c for c in ConceptoCobro.APLICA if c[0] != ConceptoCobro.AGRUPACION], required=False)
    nuevo_recargo = forms.BooleanField(label="Con recargo por pago tardío", required=False)

    def __init__(self, *args, textos=None, conceptos=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.conceptos = list(conceptos)
        etiquetas = {
            "titular": "Cómo se llama a cada titular (singular)",
            "titulares": "Plural",
            "matricula": "Cómo se llama la matrícula",
            "agrupacion": "Cómo se llama una agrupación (singular)",
            "agrupaciones": "Plural",
        }
        campos = {}
        for clave in VOCABULARIO_BASE:
            campos[clave] = forms.CharField(label=etiquetas[clave], max_length=60, initial=(textos or VOCABULARIO_BASE)[clave])
        for concepto in self.conceptos:
            campos[f"quitar_{concepto.pk}"] = forms.BooleanField(label=f"Quitar «{concepto.nombre}» ({concepto.get_tipo_display().lower()})", required=False)
        campos.update(self.fields)
        self.fields = campos

    def clean(self):
        datos = super().clean()
        nombre = (datos.get("nuevo_nombre") or "").strip()
        if nombre:
            if ConceptoCobro.objects.filter(nombre__iexact=nombre).exists():
                self.add_error("nuevo_nombre", "Ya existe un concepto con ese nombre.")
            if not datos.get("nuevo_tipo"):
                self.add_error("nuevo_tipo", "Elige el tipo del concepto.")
            if datos.get("nuevo_tipo") == ConceptoCobro.RECURRENTE and not datos.get("nuevo_periodicidad"):
                self.add_error("nuevo_periodicidad", "Un concepto recurrente necesita periodicidad.")
        datos["nuevo_nombre"] = nombre
        return datos


class FormularioAsistenteConceptos(forms.Form):
    def __init__(self, *args, conceptos=(), con_recargo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.conceptos = list(conceptos)
        for concepto in self.conceptos:
            self.fields[f"importe_{concepto.pk}"] = CampoImporte(label=f"{concepto.nombre}: importe", required=False)
            if concepto.tipo == "recurrente":
                self.fields[f"dia_{concepto.pk}"] = forms.IntegerField(label=f"{concepto.nombre}: día de vencimiento (1 a 28)", min_value=1, max_value=28, required=False)
            if concepto.nombre in (con_recargo or {}):
                sugerido = (con_recargo or {})[concepto.nombre] or {}
                self.fields[f"recargo_tipo_{concepto.pk}"] = forms.ChoiceField(label=f"{concepto.nombre}: tipo de recargo", choices=ReglaRecargo.TIPOS, initial=sugerido.get("tipo", "fijo"), required=False)
                self.fields[f"recargo_valor_{concepto.pk}"] = CampoImporte(label=f"{concepto.nombre}: valor del recargo (importe o porcentaje)", required=False)
                self.fields[f"recargo_gracia_{concepto.pk}"] = forms.IntegerField(label=f"{concepto.nombre}: días de gracia", min_value=0, max_value=60, required=False, initial=sugerido.get("dias_gracia", 0))


class FormularioAsistenteUsuario(ContrasenaNueva):
    usuario = forms.RegexField(label="Usuario", max_length=60, regex=r"^[a-zA-Z0-9_.-]+$")
    nombre = forms.CharField(label="Nombre completo", max_length=150)
    field_order = ["usuario", "nombre", "contrasena1", "contrasena2"]
