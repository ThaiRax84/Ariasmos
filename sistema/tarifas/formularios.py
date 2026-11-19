from django import forms

from cobros.formularios import CampoImportePositivo, maximo_dia
from cobros.models import ConceptoCobro
from configuracion.models import vocabulario
from proyecto.dependencias import ConDependencias, depende
from titulares.models import Agrupacion

from .models import CANTIDAD_TOPE, TarifaAgrupacion

ETIQUETA_DIA = {"semanal": "1 lunes a 7 domingo", "quincenal": "1 a 15", "": "1 a 28"}


class FormularioOpciones(ConDependencias, forms.Form):
    por_cantidad = forms.BooleanField(label="Se cobra por cantidad (al cargarlo se pide cuántos y el importe es cantidad × tarifa)", required=False)
    cantidad_maxima = forms.IntegerField(label="Cantidad máxima en un cargo", min_value=1, max_value=CANTIDAD_TOPE, initial=20)
    solo_con_tarifa = forms.BooleanField(label="", required=False)

    def __init__(self, *args, concepto=None, **kwargs):
        super().__init__(*args, **kwargs)
        voc = vocabulario()
        self.concepto = concepto
        self.fields["solo_con_tarifa"].label = f"Solo con tarifa: si su {voc['agrupacion_min']} no tiene tarifa activa, no se le cobra"
        if concepto is not None and concepto.tipo != ConceptoCobro.POR_EVENTO:
            self.fields.pop("por_cantidad")
            self.fields.pop("cantidad_maxima")
        depende(self, "cantidad_maxima", "por_cantidad")

    def clean(self):
        datos = super().clean()
        datos.setdefault("por_cantidad", False)
        if not datos.get("por_cantidad"):
            datos["cantidad_maxima"] = 1
            self.errors.pop("cantidad_maxima", None)
        return datos


class FormularioTarifa(ConDependencias, forms.Form):
    agrupacion = forms.ModelChoiceField(label="", queryset=Agrupacion.objects.none())
    importe_centavos = CampoImportePositivo(label="Importe")
    periodicidad = forms.ChoiceField(label="Periodicidad propia (vacío: la del concepto)", required=False)
    dia_vencimiento = forms.IntegerField(label="Día de vencimiento propio (vacío: el del concepto)", required=False, min_value=1, max_value=28)
    activa = forms.BooleanField(label="Activa", required=False, initial=True)

    def __init__(self, *args, concepto=None, tarifa=None, **kwargs):
        super().__init__(*args, **kwargs)
        voc = vocabulario()
        self.concepto = concepto
        self.tarifa = tarifa
        campo = self.fields["agrupacion"]
        campo.label = voc["agrupacion"]
        usadas = TarifaAgrupacion.objects.filter(concepto=concepto).values_list("agrupacion_id", flat=True)
        campo.queryset = Agrupacion.objects.filter(activa=True).exclude(pk__in=usadas)
        if tarifa is not None:
            self.fields.pop("agrupacion")
            self.initial.update({"importe_centavos": tarifa.importe_centavos, "periodicidad": tarifa.periodicidad, "dia_vencimiento": tarifa.dia_vencimiento, "activa": tarifa.activa})
        if concepto.tipo == ConceptoCobro.RECURRENTE:
            self.fields["periodicidad"].choices = [("", "La del concepto")] + list(ConceptoCobro.PERIODICIDADES)
        else:
            self.fields.pop("periodicidad")
            self.fields["dia_vencimiento"].widget = forms.HiddenInput()
        if "periodicidad" in self.fields:
            propia = concepto.periodicidad
            maximos = {clave: maximo_dia(clave) for clave, _ in ConceptoCobro.PERIODICIDADES}
            maximos[""] = maximo_dia(propia)
            etiquetas = {clave: f"Día de vencimiento propio ({ETIQUETA_DIA.get(clave, ETIQUETA_DIA[''])}; vacío: el del concepto)" for clave in maximos}
            etiquetas[""] = f"Día de vencimiento propio ({ETIQUETA_DIA.get(propia, ETIQUETA_DIA[''])}; vacío: el del concepto)"
            depende(self, "dia_vencimiento", "periodicidad", etiquetas=etiquetas, maximos=maximos)

    def clean(self):
        datos = super().clean()
        datos.setdefault("periodicidad", "")
        if self.concepto.tipo != ConceptoCobro.RECURRENTE:
            datos["dia_vencimiento"] = None
        periodicidad = datos.get("periodicidad") or self.concepto.periodicidad
        dia = datos.get("dia_vencimiento")
        if dia is not None and not 1 <= dia <= maximo_dia(periodicidad):
            self.add_error("dia_vencimiento", f"El día de vencimiento debe estar entre 1 y {maximo_dia(periodicidad)}.")
        return datos
