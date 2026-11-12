from django import forms

from nucleo.dinero import ErrorImporte, a_centavos, a_texto
from titulares.models import Agrupacion, Titular

from .models import ConceptoCobro, PlanCobro, ReglaRecargo


class CampoImporte(forms.CharField):
    def __init__(self, *args, maximo=None, **kwargs):
        kwargs.setdefault("max_length", 20)
        kwargs.setdefault("widget", forms.TextInput(attrs={"inputmode": "decimal"}))
        self.maximo = maximo
        super().__init__(*args, **kwargs)

    def prepare_value(self, valor):
        if isinstance(valor, int):
            return a_texto(valor)
        return valor

    def clean(self, valor):
        valor = super().clean(valor)
        if valor in ("", None):
            return None
        try:
            centavos = a_centavos(valor)
        except ErrorImporte:
            raise forms.ValidationError("Escribe una cantidad válida, por ejemplo 1250.50")
        if centavos < 0:
            raise forms.ValidationError("No se admiten cantidades negativas.")
        if self.maximo is not None and centavos > self.maximo:
            raise forms.ValidationError("La cantidad excede el máximo permitido.")
        return centavos


class FormularioRegla(forms.ModelForm):
    valor = CampoImporte(label="Valor (importe o porcentaje)")
    tope_centavos = CampoImporte(label="Tope (opcional)", required=False)

    class Meta:
        model = ReglaRecargo
        fields = ["nombre", "tipo", "valor", "dias_gracia", "se_repite", "tope_centavos", "activa"]
        labels = {"dias_gracia": "Días de gracia", "se_repite": "Se repite cada periodo", "activa": "Activa"}

    def clean(self):
        datos = super().clean()
        if datos.get("tipo") == ReglaRecargo.PORCENTAJE and (datos.get("valor") or 0) > 10000:
            raise forms.ValidationError("El porcentaje no puede pasar de 100.")
        return datos


class FormularioConcepto(forms.ModelForm):
    importe_centavos = CampoImporte(label="Importe por defecto")

    class Meta:
        model = ConceptoCobro
        fields = ["nombre", "tipo", "importe_centavos", "periodicidad", "dia_vencimiento", "regla_recargo", "aplica_a", "agrupacion", "prioridad", "activo"]
        labels = {
            "periodicidad": "Periodicidad (solo recurrentes)",
            "dia_vencimiento": "Día de vencimiento (1 a 28)",
            "regla_recargo": "Regla de recargo",
            "aplica_a": "Aplica a",
            "agrupacion": "Agrupación (si aplica a una)",
            "prioridad": "Prioridad de aplicación",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["agrupacion"].queryset = Agrupacion.objects.filter(activa=True)
        self.fields["regla_recargo"].queryset = ReglaRecargo.objects.filter(activa=True)

    def clean(self):
        datos = super().clean()
        if datos.get("tipo") == ConceptoCobro.RECURRENTE and not datos.get("periodicidad"):
            raise forms.ValidationError("Un concepto recurrente necesita periodicidad.")
        if datos.get("tipo") != ConceptoCobro.RECURRENTE:
            datos["periodicidad"] = ""
        if datos.get("aplica_a") == ConceptoCobro.AGRUPACION and not datos.get("agrupacion"):
            raise forms.ValidationError("Elige la agrupación a la que aplica.")
        dia = datos.get("dia_vencimiento")
        if dia is not None and not 1 <= dia <= 28:
            raise forms.ValidationError("El día de vencimiento debe estar entre 1 y 28.")
        return datos


class FormularioPlan(forms.ModelForm):
    importe_centavos = CampoImporte(label="Importe propio (opcional)", required=False)
    descuento_centesimas = CampoImporte(label="Descuento en porcentaje (opcional)", required=False, maximo=10000)

    class Meta:
        model = PlanCobro
        fields = ["titular", "concepto", "importe_centavos", "descuento_centesimas", "vigente_desde", "vigente_hasta", "activo", "nota"]
        widgets = {"vigente_desde": forms.DateInput(attrs={"type": "date"}), "vigente_hasta": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["concepto"].queryset = ConceptoCobro.objects.filter(tipo=ConceptoCobro.RECURRENTE)
        self.fields["titular"].queryset = Titular.objects.exclude(estado=Titular.RECHAZADO)

    def clean(self):
        datos = super().clean()
        if datos.get("importe_centavos") is not None and datos.get("descuento_centesimas") is not None:
            raise forms.ValidationError("Usa importe propio o descuento, no ambos.")
        desde, hasta = datos.get("vigente_desde"), datos.get("vigente_hasta")
        if desde and hasta and hasta < desde:
            raise forms.ValidationError("La vigencia termina antes de empezar.")
        return datos
