from django import forms

from banco.models import CuentaBancaria
from cobros.formularios import CampoImporte, CampoImportePositivo
from cuentas.models import Usuario

from .models import Caja, Denominacion, Turno


class FormularioAbrir(forms.Form):
    caja = forms.ModelChoiceField(label="Caja", queryset=Caja.objects.none())
    fondo_inicial = CampoImporte(label="Fondo inicial (cambio en la caja)", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ocupadas = Turno.objects.filter(estado=Turno.ABIERTO).values("caja")
        self.fields["caja"].queryset = Caja.objects.filter(activa=True).exclude(pk__in=ocupadas)


class FormularioArqueo(forms.Form):
    nota = forms.CharField(label="Nota (obligatoria si la diferencia supera el umbral)", max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.denominaciones = list(Denominacion.objects.filter(activa=True))
        campos = {}
        for denominacion in self.denominaciones:
            campos[f"d_{denominacion.valor}"] = forms.IntegerField(label=f"Piezas de {denominacion}", min_value=0, max_value=100000, required=False, initial=0)
        campos.update(self.fields)
        self.fields = campos

    def conteo(self):
        return {str(d.valor): self.cleaned_data.get(f"d_{d.valor}") or 0 for d in self.denominaciones}


class FormularioEntrega(forms.Form):
    destino = forms.ModelChoiceField(label="Entregar a", queryset=Usuario.objects.none())
    importe = CampoImportePositivo(label="Importe")
    nota = forms.CharField(label="Nota", max_length=300, required=False)

    def __init__(self, *args, origen=None, **kwargs):
        super().__init__(*args, **kwargs)
        candidatos = [u.pk for u in Usuario.objects.filter(activo=True).exclude(pk=origen.pk).select_related("rol") if u.tiene_permiso_de_rol("recibir_efectivo")]
        self.fields["destino"].queryset = Usuario.objects.filter(pk__in=candidatos)


class FormularioDeposito(forms.Form):
    cuenta = forms.ModelChoiceField(label="Cuenta bancaria", queryset=CuentaBancaria.objects.filter(activa=True))
    importe = CampoImportePositivo(label="Importe depositado")
    fecha = forms.DateField(label="Fecha del depósito", widget=forms.DateInput(attrs={"type": "date"}))
    referencia = forms.CharField(label="Referencia o folio del depósito", max_length=60)


class FormularioConfirmar(forms.Form):
    importe = CampoImportePositivo(label="Importe que recibiste")


class FormularioRechazar(forms.Form):
    nota = forms.CharField(label="Motivo", max_length=300)
