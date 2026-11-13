from django import forms

from caja import piezas as control_piezas
from caja.comprobantes import LIMITE as LIMITE_COMPROBANTE
from cobros.formularios import CampoImportePositivo
from cobros.models import ConceptoCobro
from proyecto.captura import CampoGuiadoTexto

from .models import MAXIMO_CANTIDAD, MAXIMO_CONTEO, OBSERVADO, REVISADO, Articulo, Devolucion, RegistroInventario, Venta
from .servicios import CLAVE, LIMITE_CONTEO

RENGLONES_VENTA = 8


class FormularioArticulo(forms.ModelForm):
    precio = CampoImportePositivo(label="Precio")

    class Meta:
        model = Articulo
        fields = ["clave", "nombre", "precio", "minimo", "concepto", "activo"]
        labels = {"clave": "Clave (letras mayúsculas, números, punto, guion)", "nombre": "Nombre", "minimo": "Existencia mínima", "concepto": "Concepto de cobro al que pertenece", "activo": "Activo"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["concepto"].queryset = ConceptoCobro.objects.filter(activo=True)
        self.fields["minimo"].min_value = 0
        self.fields["minimo"].max_value = MAXIMO_CONTEO
        self.fields["minimo"].widget.attrs.update({"min": 0, "max": MAXIMO_CONTEO})

    def clean_clave(self):
        clave = (self.cleaned_data.get("clave") or "").strip().upper()
        if not CLAVE.match(clave):
            raise forms.ValidationError("Usa de 1 a 30 letras mayúsculas, números, punto, guion o guion bajo; empieza con letra o número.")
        return clave

    def clean_nombre(self):
        return " ".join(self.cleaned_data.get("nombre", "").split())


class FormularioVenta(forms.Form):
    def __init__(self, *args, con_modo=True, **kwargs):
        super().__init__(*args, **kwargs)
        articulos = Articulo.objects.filter(activo=True).order_by("nombre")
        self.lineas = []
        for numero in range(RENGLONES_VENTA):
            self.fields[f"articulo_{numero}"] = forms.ModelChoiceField(label=f"Artículo {numero + 1}", queryset=articulos, required=False)
            self.fields[f"cantidad_{numero}"] = forms.IntegerField(label="Cantidad", min_value=1, max_value=MAXIMO_CANTIDAD, required=False)
            self.lineas.append((f"articulo_{numero}", f"cantidad_{numero}"))
        if con_modo:
            self.fields["modo"] = forms.ChoiceField(label="¿Cómo se paga?", choices=Venta.MODOS, widget=forms.RadioSelect, initial=Venta.AHORA)

    def clean(self):
        datos = super().clean()
        renglones = []
        for campo_articulo, campo_cantidad in self.lineas:
            articulo, cantidad = datos.get(campo_articulo), datos.get(campo_cantidad)
            if articulo is None and cantidad is None:
                continue
            if articulo is None or cantidad is None:
                raise forms.ValidationError("Cada renglón lleva artículo y cantidad.")
            renglones.append((articulo.pk, cantidad))
        if not renglones:
            raise forms.ValidationError("Agrega al menos un artículo.")
        datos["renglones"] = renglones
        return datos


class FormularioBuscarVenta(forms.Form):
    venta = CampoGuiadoTexto(label="Número de venta (por ejemplo V-12)", max_length=16, required=False, acepta="folio", maximo_tecleo=16)
    codigo = CampoGuiadoTexto(label="O el código de verificación o texto del QR del recibo", max_length=60, required=False, acepta="recibo", maximo_tecleo=60)
    folio = CampoGuiadoTexto(label="Folio del recibo (serie-número; no hace falta si leíste el QR)", max_length=24, required=False, acepta="folio", maximo_tecleo=24)


class FormularioDevolucion(forms.Form):
    medio = forms.ChoiceField(label="¿Cómo regresa lo ya pagado?", choices=[(Devolucion.SALDO, "Saldo a favor (al momento; Supervisión lo revisa)"), (Devolucion.EFECTIVO, "Efectivo (se solicita y lo autoriza otra persona)")], widget=forms.RadioSelect, initial=Devolucion.SALDO)
    motivo = forms.CharField(label="Motivo de la devolución", max_length=300)

    def __init__(self, *args, renglones=(), disponibles=None, publico=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.renglones = []
        for renglon in renglones:
            libre = (disponibles or {}).get(renglon.pk, 0)
            if libre <= 0:
                continue
            self.fields[f"cantidad_{renglon.pk}"] = forms.IntegerField(label=f"{renglon.articulo.nombre}: cuántos regresan (de {libre})", min_value=0, max_value=libre, required=False, initial=0)
            self.fields[f"mal_{renglon.pk}"] = forms.BooleanField(label=f"{renglon.articulo.nombre}: regresa en mal estado (sale como merma)", required=False)
            self.renglones.append(renglon)
        if publico:
            self.fields["medio"].choices = [(Devolucion.EFECTIVO, "Efectivo (se solicita y lo autoriza otra persona)")]
            self.fields["medio"].initial = Devolucion.EFECTIVO
        self.nombres_piezas = control_piezas.campos(self, "p_", "Piezas que entregas (solo si es en efectivo):") if control_piezas.activo() else []

    def clean(self):
        datos = super().clean()
        cantidades = {}
        for renglon in self.renglones:
            cantidad = datos.get(f"cantidad_{renglon.pk}") or 0
            if cantidad:
                cantidades[str(renglon.pk)] = [cantidad, not datos.get(f"mal_{renglon.pk}")]
        if not cantidades:
            raise forms.ValidationError("Indica cuántos artículos regresan.")
        datos["cantidades"] = cantidades
        return datos

    def piezas(self):
        if not self.nombres_piezas:
            return None
        return control_piezas.leer(self.cleaned_data, self.nombres_piezas)


class FormularioRegistro(forms.Form):
    tipo = forms.ChoiceField(label="Tipo", choices=RegistroInventario.TIPOS, widget=forms.RadioSelect, initial=RegistroInventario.ENTRADA)
    articulo = forms.ModelChoiceField(label="Artículo", queryset=Articulo.objects.none())
    cantidad = forms.IntegerField(label="Cantidad", min_value=1, max_value=MAXIMO_CANTIDAD)
    motivo = forms.CharField(label="Motivo (compra, daño, pérdida…)", max_length=150)
    nota = forms.CharField(label="Nota (opcional)", max_length=300, required=False)
    comprobante = forms.FileField(label="Comprobante (opcional): foto JPEG o PNG, o PDF, hasta 5 MB", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["articulo"].queryset = Articulo.objects.filter(activo=True).order_by("nombre")

    def clean_comprobante(self):
        archivo = self.cleaned_data.get("comprobante")
        if archivo is not None and archivo.size > LIMITE_COMPROBANTE:
            raise forms.ValidationError("El comprobante pasa de 5 MB.")
        return archivo


class FormularioComprobante(forms.Form):
    archivo = forms.FileField(label="Comprobante: foto JPEG o PNG, o PDF, hasta 5 MB")


class FormularioRevision(forms.Form):
    resultado = forms.ChoiceField(label="Resultado", choices=[(REVISADO, "Revisado"), (OBSERVADO, "Observado")])
    nota = forms.CharField(label="Nota (obligatoria si queda observado)", max_length=300, required=False)


class FormularioSubirConteo(forms.Form):
    archivo = forms.FileField(label="Conteo en Excel (.xlsx) o CSV con las columnas «clave» y «cantidad», hasta 1 MB")

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        if archivo is not None and archivo.size > LIMITE_CONTEO:
            raise forms.ValidationError("El archivo pasa de 1 MB.")
        return archivo


class FormularioCapturaConteo(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.articulos = list(Articulo.objects.filter(activo=True).order_by("clave"))
        for articulo in self.articulos:
            self.fields[f"c_{articulo.pk}"] = forms.IntegerField(label=f"{articulo.clave} · {articulo.nombre}", min_value=0, max_value=MAXIMO_CONTEO, required=False)

    def clean(self):
        datos = super().clean()
        cantidades = {a.pk: datos[f"c_{a.pk}"] for a in self.articulos if datos.get(f"c_{a.pk}") is not None}
        if not cantidades:
            raise forms.ValidationError("Captura al menos un artículo contado.")
        datos["cantidades"] = cantidades
        return datos


class FormularioConfiguracion(forms.Form):
    modulo_inventario = forms.BooleanField(label="Llevar inventario de artículos", required=False)
    devoluciones_inventario = forms.BooleanField(label="Aceptar devoluciones de artículos vendidos", required=False)
    dias_devolucion = forms.IntegerField(label="Días después de la venta en que se acepta una devolución", min_value=0, max_value=365)
    dias_conteo_sin_aprobar = forms.IntegerField(label="Días que un conteo puede esperar aprobación antes de avisar a Dirección", min_value=1, max_value=60)
    porcentaje_existencia_baja = forms.IntegerField(label="Porcentaje de existencia baja: se marca «pocas» cuando quedan este porcentaje o menos de lo que había tras la última entrada o conteo", min_value=1, max_value=99, required=False)
