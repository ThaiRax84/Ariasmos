from django import forms

from configuracion.models import vocabulario
from titulares.models import Agrupacion

from . import gestion_avisos, variables
from .models import Aviso, PlantillaMensaje


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


class FormularioAviso(forms.Form):
    momento = forms.ChoiceField(label="¿Cuándo se manda?", choices=Aviso.MOMENTOS)
    dias = forms.IntegerField(
        label="Días (de atraso o que faltan)", min_value=1, required=False
    )
    plantilla = forms.ModelChoiceField(
        label="¿Qué mensaje?", queryset=PlantillaMensaje.objects.all(), empty_label=None
    )
    agrupaciones = forms.ModelMultipleChoiceField(
        queryset=Agrupacion.objects.filter(activa=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, aviso=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.aviso = aviso
        self.fields["agrupaciones"].label = f"¿A qué {vocabulario()['agrupaciones_min']}? Si no marcas ninguna, a todos"
        if aviso is None:
            if Aviso.objects.filter(momento=Aviso.PAGO).exists():
                self.fields["momento"].choices = [
                    m for m in Aviso.MOMENTOS if m[0] != Aviso.PAGO
                ]
        elif aviso.momento == Aviso.PAGO:
            for campo in ("momento", "dias", "agrupaciones"):
                del self.fields[campo]
        else:
            del self.fields["momento"]
            self.initial = {
                "dias": aviso.dias,
                "plantilla": aviso.plantilla_id,
                "agrupaciones": [a.pk for a in aviso.agrupaciones.all()],
            }

    @property
    def momento_elegido(self):
        return self.aviso.momento if self.aviso else self.cleaned_data.get("momento")

    def clean(self):
        datos = super().clean()
        maximo = Aviso.MAXIMO_DIAS.get(self.momento_elegido)
        if maximo and not 1 <= (datos.get("dias") or 0) <= maximo:
            self.add_error("dias", f"Escribe un número de días entre 1 y {maximo}.")
        return datos


class FormularioLimites(forms.Form):
    inicio = forms.TimeField(
        label="Desde las",
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
    )
    fin = forms.TimeField(
        label="Hasta las",
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
    )
    maximo = forms.IntegerField(
        label="Máximo de avisos por persona en una semana", min_value=1, max_value=14
    )
    dias_sin_envio = forms.MultipleChoiceField(
        label="Días sin envíos",
        choices=list(enumerate(gestion_avisos.DIAS_DE_LA_SEMANA)),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def clean(self):
        datos = super().clean()
        if {"inicio", "fin"} <= datos.keys() and datos["inicio"] >= datos["fin"]:
            self.add_error("fin", "La hora final debe ser después de la inicial.")
        return datos

    def clean_dias_sin_envio(self):
        return [int(d) for d in self.cleaned_data["dias_sin_envio"]]
