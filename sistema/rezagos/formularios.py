from django import forms

from cobros.formularios import CampoImporte, CampoImportePositivo
from configuracion.models import hoy_negocio, opciones_vocabulario, vocabulario
from nucleo.matricula import normalizar
from titulares.models import Agrupacion, Titular

from . import tras_alta
from .models import LARGO_TEXTO, MODOS_EXCEPCION, MODOS_NEGOCIO, TOPE_DIAS, TOPE_IMPORTE, VALOR, ReglaRezago

ETIQUETAS_ACCIONES = {
    "aviso_inicio": "Aviso en el inicio de todos (el adeudo solo lo ve quien puede ver saldos)",
    "marca": "Marca con el texto de la regla en la ficha, en los buscadores y al cobrar",
    "sin_credito": "Sin crédito: ventas al adeudo, cargos manuales y prórrogas pasan a solicitud",
    "cobranza": "Entra en la lista de cobranza",
}


class _Limites(forms.Form):
    modos = MODOS_NEGOCIO
    modo_importe = forms.ChoiceField(label="Importe máximo de adeudo vencido", widget=forms.RadioSelect)
    importe_maximo = CampoImporte(label="Hasta cuánto (si elegiste un valor)", required=False, maximo=TOPE_IMPORTE)
    modo_dias = forms.ChoiceField(label="Días máximos de atraso (desde el vencimiento más antiguo con saldo)", widget=forms.RadioSelect)
    dias_maximos = forms.IntegerField(label="Hasta cuántos días (si elegiste un valor)", required=False, min_value=0, max_value=TOPE_DIAS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["modo_importe"].choices = self.modos
        self.fields["modo_dias"].choices = self.modos

    def clean(self):
        datos = super().clean()
        if datos.get("modo_importe") == VALOR and datos.get("importe_maximo") is None:
            self.add_error("importe_maximo", "Escribe el importe máximo o elige «Ilimitado».")
        if datos.get("modo_dias") == VALOR and datos.get("dias_maximos") is None:
            self.add_error("dias_maximos", "Escribe los días máximos o elige «Ilimitado».")
        datos["importe_maximo"] = datos.get("importe_maximo") or 0
        datos["dias_maximos"] = datos.get("dias_maximos") or 0
        return datos


class FormularioLimites(_Limites):
    pass


class FormularioExcepcion(_Limites):
    modos = MODOS_EXCEPCION
    motivo = forms.CharField(label="Motivo", max_length=300, required=False)
    vigente_hasta = forms.DateField(label="Vigente hasta (opcional; vacío: sin fin)", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    quitar = forms.BooleanField(label="Quitar la excepción (vuelve a valer el límite del negocio)", required=False)

    def __init__(self, *args, existente=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not existente:
            self.fields.pop("quitar")
        elif self.data.get("quitar"):
            for campo in self.fields.values():
                campo.required = False

    def clean(self):
        if self.data.get("quitar") and "quitar" in self.fields:
            return {"quitar": True}
        datos = super().clean()
        if not (datos.get("motivo") or "").strip():
            self.add_error("motivo", "Escribe el motivo de la excepción.")
        hasta = datos.get("vigente_hasta")
        if hasta is not None and hasta < hoy_negocio():
            self.add_error("vigente_hasta", "La vigencia no puede terminar antes de hoy.")
        datos["motivo"] = (datos.get("motivo") or "").strip()
        return datos


class FormularioRegla(forms.Form):
    nombre = forms.CharField(label="Nombre de la regla", max_length=100)
    texto = forms.CharField(label=f"Texto que se muestra (hasta {LARGO_TEXTO} caracteres; por ejemplo «No puede pasar»)", max_length=LARGO_TEXTO)
    alcance = forms.ChoiceField(label="A quién aplica", widget=forms.RadioSelect)
    agrupacion = forms.ModelChoiceField(label="", queryset=Agrupacion.objects.none(), required=False)
    matricula = forms.CharField(label="", max_length=20, required=False)
    dias_minimos = forms.IntegerField(label="A partir de cuántos días de atraso (opcional)", required=False, min_value=1, max_value=TOPE_DIAS)
    importe_minimo = CampoImportePositivo(label="A partir de qué importe vencido (opcional)", required=False)
    al_rebasar_limite = forms.BooleanField(label="Al rebasar el límite de adeudo", required=False)
    aviso_inicio = forms.BooleanField(label=ETIQUETAS_ACCIONES["aviso_inicio"], required=False)
    marca = forms.BooleanField(label=ETIQUETAS_ACCIONES["marca"], required=False)
    sin_credito = forms.BooleanField(label=ETIQUETAS_ACCIONES["sin_credito"], required=False)
    cobranza = forms.BooleanField(label=ETIQUETAS_ACCIONES["cobranza"], required=False)
    activa = forms.BooleanField(label="Activa", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        voc = vocabulario()
        self.fields["alcance"].choices = opciones_vocabulario(ReglaRezago.ALCANCES, voc)
        self.fields["alcance"].help_text = f"Las reglas por {voc['agrupacion_min']} o por persona mandan sobre las generales en la misma acción: sirven para ser más estricto o más tolerante con alguien."
        self.fields["agrupacion"].label = f"{voc['agrupacion']} (si aplica a una)"
        self.fields["agrupacion"].queryset = Agrupacion.objects.filter(activa=True)
        self.fields["matricula"].label = f"{voc['matricula']} (si aplica a una sola persona)"

    def clean(self):
        datos = super().clean()
        alcance = datos.get("alcance")
        datos["titular"] = None
        if alcance == ReglaRezago.AGRUPACION:
            if datos.get("agrupacion") is None:
                self.add_error("agrupacion", f"Elige a qué {vocabulario()['agrupacion_min']} aplica.")
        else:
            datos["agrupacion"] = None
        if alcance == ReglaRezago.TITULAR:
            digitos = normalizar(datos.get("matricula") or "")
            titular = Titular.objects.filter(matricula=digitos).exclude(estado=Titular.RECHAZADO).first() if digitos else None
            if titular is None:
                self.add_error("matricula", f"No hay nadie con esa {vocabulario()['matricula_min']}.")
            datos["titular"] = titular
        if datos.get("dias_minimos") is None and datos.get("importe_minimo") is None and not datos.get("al_rebasar_limite"):
            self.add_error(None, "Elige al menos una condición: días de atraso, importe vencido o rebasar el límite.")
        if not any(datos.get(accion) for accion in ReglaRezago.ACCIONES):
            self.add_error(None, "Elige al menos una acción.")
        datos["nombre"] = (datos.get("nombre") or "").strip()
        datos["texto"] = " ".join((datos.get("texto") or "").split())
        if not datos["texto"] and "texto" not in self.errors:
            self.add_error("texto", "Escribe el texto.")
        return datos


class FormularioRecargosAlta(forms.Form):
    recargos_tras_alta = forms.ChoiceField(label="Recargos por atraso de quien se acaba de dar de alta", choices=tras_alta.OPCIONES, widget=forms.RadioSelect)


ORDENES = {"dias": "Más días de atraso", "nombre": "Nombre", "matricula": "", "agrupacion": "", "adeudo": "Mayor adeudo"}


class FormularioOrden(forms.Form):
    orden = forms.ChoiceField(label="Ordenar por", required=False)

    def __init__(self, *args, ver_saldos=False, **kwargs):
        super().__init__(*args, **kwargs)
        voc = vocabulario()
        opciones = [("dias", ORDENES["dias"]), ("nombre", ORDENES["nombre"]), ("matricula", voc["matricula"]), ("agrupacion", voc["agrupacion"])]
        if ver_saldos:
            opciones.append(("adeudo", ORDENES["adeudo"]))
        self.fields["orden"].choices = opciones

    def elegido(self):
        if self.is_valid() and self.cleaned_data.get("orden"):
            return self.cleaned_data["orden"]
        return "dias"
