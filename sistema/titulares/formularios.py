from django import forms

from cobros.models import ConceptoCobro
from configuracion.models import parametro, vocabulario
from proyecto.dependencias import ConDependencias, depende

from .contactos import FormularioContacto
from .models import Agrupacion, CampoContacto, Familia, MotivoBaja, Titular


MAXIMO_NOTAS = 2000


class FormularioTitular(forms.ModelForm):
    notas = forms.CharField(label="Notas", max_length=MAXIMO_NOTAS, required=False, widget=forms.Textarea(attrs={"rows": 3}))

    class Meta:
        model = Titular
        fields = ["nombre", "apellidos", "agrupacion", "notas"]
        widgets = {"notas": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, voc=None, **kwargs):
        super().__init__(*args, **kwargs)
        voc = voc or vocabulario()
        self.fields["agrupacion"].queryset = Agrupacion.objects.filter(activa=True)
        self.fields["agrupacion"].required = False
        self.fields["agrupacion"].label = voc["agrupacion"]
        self.fields["apellidos"].required = bool(parametro("apellidos_obligatorios"))


class FormularioAlta(FormularioContacto):
    nombre = forms.CharField(label="Nombre", max_length=100)
    apellidos = forms.CharField(label="Apellidos", max_length=150)
    agrupacion = forms.ModelChoiceField(label="Grupo", queryset=Agrupacion.objects.none(), required=False)
    conceptos = forms.ModelMultipleChoiceField(label="Conceptos iniciales", queryset=ConceptoCobro.objects.none(), required=False, widget=forms.CheckboxSelectMultiple)
    familia = forms.ModelChoiceField(label="Cuenta compartida (opcional)", queryset=Familia.objects.none(), required=False)
    familia_nueva = forms.CharField(label="O crear una nueva con este nombre", max_length=100, required=False)
    notas = forms.CharField(label="Notas", max_length=MAXIMO_NOTAS, required=False, widget=forms.Textarea(attrs={"rows": 3}))
    constancia_consentimiento = forms.BooleanField(label="Consentimiento", required=True)

    def __init__(self, *args, voc=None, **kwargs):
        super().__init__(*args, exigir_obligatorios=True, **kwargs)
        voc = voc or vocabulario()
        self.voc = voc
        self.fields["agrupacion"].queryset = Agrupacion.objects.filter(activa=True)
        self.fields["conceptos"].queryset = ConceptoCobro.objects.filter(activo=True)
        self.fields["familia"].queryset = Familia.objects.filter(activa=True)
        self.fields["agrupacion"].label = voc["agrupacion"]
        self.fields["familia"].label = f"{voc['familia']} (opcional)"
        self.fields["familia_nueva"].label = f"O crear {voc['familia_min']} con este nombre"
        self.fields["apellidos"].required = bool(parametro("apellidos_obligatorios"))
        if parametro("pedir_consentimiento"):
            self.fields["constancia_consentimiento"].label = str(parametro("texto_consentimiento")).strip() or "Consentimiento"
        else:
            del self.fields["constancia_consentimiento"]
        orden = ["nombre", "apellidos", "agrupacion", "familia", "familia_nueva", "contacto_nombre", "contacto_relacion"]
        orden += [c.clave for c in self.campos]
        orden += ["conceptos", "notas", "constancia_consentimiento"]
        self.order_fields(orden)

    def clean(self):
        datos = super().clean()
        if datos.get("familia") and (datos.get("familia_nueva") or "").strip():
            raise forms.ValidationError(f"{self.voc['familia']}: elige una existente o escribe una nueva, no ambas.")
        return datos

    def datos_titular(self):
        datos = self.cleaned_data
        return {
            "nombre": datos["nombre"],
            "apellidos": datos.get("apellidos") or "",
            "agrupacion": datos.get("agrupacion"),
            "familia": datos.get("familia"),
            "notas": datos.get("notas", ""),
            "constancia_consentimiento": bool(datos.get("constancia_consentimiento")),
        }

    def datos_contacto(self):
        return {"nombre": self.cleaned_data["contacto_nombre"], "relacion": self.cleaned_data.get("contacto_relacion"), "valores": self.valores()}


class FormularioEditarContacto(FormularioContacto):
    contacto_principal = forms.BooleanField(label="Contacto principal", required=False)
    acepta_whatsapp = forms.BooleanField(label="Aceptó recibir mensajes por WhatsApp", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, exigir_obligatorios=True, **kwargs)
        self.order_fields(self._orden_con_casilla_junto_al_telefono())

    def _orden_con_casilla_junto_al_telefono(self):
        orden = [n for n in self.fields if n != "acepta_whatsapp"]
        telefonos = [c.clave for c in self.campos if c.tipo == CampoContacto.TELEFONO]
        orden.insert(orden.index(telefonos[0]) + 1 if telefonos else len(orden), "acepta_whatsapp")
        return orden

    def datos_contacto(self):
        return {
            "nombre": self.cleaned_data["contacto_nombre"],
            "relacion": self.cleaned_data.get("contacto_relacion"),
            "valores": self.valores(),
            "acepta_whatsapp": self.cleaned_data["acepta_whatsapp"],
        }


class FormularioCambioFamilia(ConDependencias, forms.Form):
    modo = forms.ChoiceField(label="Qué hacer", choices=[("ligar", "Ligar a una existente"), ("crear", "Crear una nueva y ligar"), ("desligar", "Desligar")], widget=forms.RadioSelect)
    familia = forms.ModelChoiceField(label="Existente", queryset=Familia.objects.none(), required=False)
    nombre = forms.CharField(label="Nombre de la nueva", max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["familia"].queryset = Familia.objects.filter(activa=True)
        self.fields["familia"].label = f"{vocabulario()['familia']} existente"
        depende(self, "familia", "modo", ["ligar"])
        depende(self, "nombre", "modo", ["crear"])

    def datos(self):
        datos = self.cleaned_data
        return {"modo": datos["modo"], "familia": datos["familia"].pk if datos.get("familia") else None, "nombre": (datos.get("nombre") or "").strip()}


class FormularioBaja(forms.Form):
    motivo = forms.ModelChoiceField(label="Motivo", queryset=MotivoBaja.objects.none())
    nota = forms.CharField(label="Nota", max_length=300, required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["motivo"].queryset = MotivoBaja.objects.filter(activo=True)


class FormularioNota(forms.Form):
    nota = forms.CharField(label="Nota", max_length=300, required=False, widget=forms.Textarea(attrs={"rows": 3}))
