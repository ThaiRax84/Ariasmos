from django import forms

from banco.models import CuentaBancaria
from cobros.formularios import CampoImporte, CampoImportePositivo
from cuentas.models import Usuario

from . import piezas as control_piezas
from .comprobantes import LIMITE as LIMITE_COMPROBANTE
from .models import Caja, Denominacion, MotivoRetiro, RetiroCaja, Turno


class ConPiezas:
    prefijo = "p_"
    etiqueta = "Piezas de"
    piezas_requeridas = False

    def agregar_piezas(self):
        self.nombres_piezas = control_piezas.campos(self, self.prefijo, self.etiqueta) if control_piezas.activo() else []

    def piezas(self):
        if not self.nombres_piezas:
            return None
        return control_piezas.leer(self.cleaned_data, self.nombres_piezas)

    def campos_piezas(self):
        return [self[nombre] for nombre, _ in self.nombres_piezas]


class FormularioAbrir(ConPiezas, forms.Form):
    prefijo = "f_"
    etiqueta = "Fondo: piezas de"
    caja = forms.ModelChoiceField(label="Caja", queryset=Caja.objects.none())
    fondo_inicial = CampoImporte(label="Fondo inicial (cambio en la caja)", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ocupadas = Turno.objects.filter(estado=Turno.ABIERTO).values("caja")
        self.fields["caja"].queryset = Caja.objects.filter(activa=True).exclude(pk__in=ocupadas)
        self.agregar_piezas()
        if self.nombres_piezas:
            del self.fields["fondo_inicial"]


class FormularioArqueo(forms.Form):
    etiqueta_nota = "Nota (opcional)"
    nota_requerida = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.denominaciones = list(Denominacion.objects.filter(activa=True))
        for denominacion in self.denominaciones:
            self.fields[f"d_{denominacion.valor}"] = forms.IntegerField(label=f"Piezas de {denominacion}", min_value=0, max_value=100000, required=False, initial=0)
        self.fields["nota"] = forms.CharField(label=self.etiqueta_nota, max_length=500, required=self.nota_requerida, widget=forms.Textarea(attrs={"rows": 2}))

    def conteo(self):
        return {str(d.valor): self.cleaned_data.get(f"d_{d.valor}") or 0 for d in self.denominaciones}


class FormularioReconteo(FormularioArqueo):
    etiqueta_nota = "Nota que explica la diferencia (obligatoria)"
    nota_requerida = True


class FormularioCerrarConPrimero(forms.Form):
    nota = forms.CharField(label="Nota que explica la diferencia (obligatoria)", max_length=500, widget=forms.Textarea(attrs={"rows": 2}))


class FormularioEntrega(ConPiezas, forms.Form):
    destino = forms.ModelChoiceField(label="Entregar a", queryset=Usuario.objects.none())
    importe = CampoImportePositivo(label="Importe")
    nota = forms.CharField(label="Nota", max_length=300, required=False)

    def __init__(self, *args, origen=None, **kwargs):
        super().__init__(*args, **kwargs)
        candidatos = [u.pk for u in Usuario.objects.filter(activo=True).exclude(pk=origen.pk).select_related("rol") if u.tiene_permiso_de_rol("recibir_efectivo")]
        self.fields["destino"].queryset = Usuario.objects.filter(pk__in=candidatos)
        self.agregar_piezas()


class FormularioDeposito(ConPiezas, forms.Form):
    cuenta = forms.ModelChoiceField(label="Cuenta bancaria", queryset=CuentaBancaria.objects.filter(activa=True))
    importe = CampoImportePositivo(label="Importe depositado")
    fecha = forms.DateField(label="Fecha del depósito", widget=forms.DateInput(attrs={"type": "date"}))
    referencia = forms.CharField(label="Referencia o folio del depósito", max_length=60)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agregar_piezas()


class FormularioRetiro(ConPiezas, forms.Form):
    importe = CampoImportePositivo(label="Importe que sale de la caja")
    motivo = forms.ModelChoiceField(label="Motivo", queryset=MotivoRetiro.objects.none())
    nota = forms.CharField(label="Nota (en qué se gastó)", max_length=300, required=False)
    comprobante = forms.FileField(label="Comprobante: foto JPEG o PNG, o PDF, hasta 5 MB (puedes adjuntarlo después)", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["motivo"].queryset = MotivoRetiro.objects.filter(activo=True)
        self.agregar_piezas()

    def clean_comprobante(self):
        archivo = self.cleaned_data.get("comprobante")
        if archivo is not None and archivo.size > LIMITE_COMPROBANTE:
            raise forms.ValidationError("El comprobante pasa de 5 MB.")
        return archivo


class FormularioComprobante(forms.Form):
    archivo = forms.FileField(label="Comprobante: foto JPEG o PNG, o PDF, hasta 5 MB")


class FormularioSinComprobante(forms.Form):
    motivo = forms.CharField(label="Por qué no hay comprobante", max_length=300)


class FormularioRevision(forms.Form):
    resultado = forms.ChoiceField(label="Resultado", choices=[(RetiroCaja.REVISADO, "Revisado"), (RetiroCaja.OBSERVADO, "Observado")])
    nota = forms.CharField(label="Nota (obligatoria si queda observado)", max_length=300, required=False)


class FormularioRevertirRetiro(ConPiezas, forms.Form):
    etiqueta = "Piezas que regresan:"
    motivo = forms.CharField(label="Motivo de la reversión", max_length=300)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agregar_piezas()


class FormularioMotivoRetiro(forms.ModelForm):
    class Meta:
        model = MotivoRetiro
        fields = ["nombre", "activo"]


class FormularioConfirmar(forms.Form):
    importe = CampoImportePositivo(label="Importe que recibiste")


class FormularioRechazar(forms.Form):
    nota = forms.CharField(label="Motivo", max_length=300)


class FormularioPiezasCobro(forms.Form):
    def __init__(self, *args, con_cambio=False, propuesta=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.recibidas = control_piezas.campos(self, "r_", "Recibí: piezas de")
        self.cambio = control_piezas.campos(self, "c_", "Entrego de cambio: piezas de") if con_cambio else []
        for nombre, valor in self.cambio:
            self.fields[nombre].initial = (propuesta or {}).get(valor, 0)

    def piezas_recibidas(self):
        return control_piezas.leer(self.cleaned_data, self.recibidas)

    def piezas_cambio(self):
        return control_piezas.leer(self.cleaned_data, self.cambio)

    def campos_recibidas(self):
        return [self[nombre] for nombre, _ in self.recibidas]

    def campos_cambio(self):
        return [self[nombre] for nombre, _ in self.cambio]
