from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from nucleo import clabe as nucleo_clabe
from nucleo import telefono
from proyecto.captura import CampoDigitos
from titulares.contactos import normalizar_telefono, prefijo

from .models import Banco, CuentaBancaria, MedioPago


def normalizar_contacto(valor):
    valor = (valor or "").strip()
    if not valor:
        return ""
    if "@" in valor:
        try:
            validate_email(valor)
        except ValidationError:
            raise ValidationError("Escribe un correo válido o un teléfono.")
        return valor.lower()
    return telefono.formatear(normalizar_telefono(valor), prefijo())


class FormularioCuenta(forms.Form):
    clabe = CampoDigitos(label="CLABE (18 dígitos)", max_length=30, maximo_tecleo=18, widget=forms.TextInput(attrs={"autocomplete": "off"}))
    banco = forms.ModelChoiceField(label="Banco", queryset=Banco.objects.none(), required=False, empty_label="Proponer según la CLABE")
    banco_otro = forms.CharField(label="Otro banco (solo si el prefijo de la CLABE no está en el catálogo)", max_length=80, required=False)
    beneficiario = forms.CharField(label="Beneficiario (como lo pide el banco)", max_length=150)
    numero_cuenta = forms.CharField(label="Número de cuenta (opcional)", max_length=30, required=False)
    convenio = forms.CharField(label="Convenio de cobranza referenciada (opcional)", max_length=30, required=False)
    medios = forms.ModelMultipleChoiceField(label="Medios aceptados", queryset=MedioPago.objects.none(), required=False, widget=forms.CheckboxSelectMultiple)
    referencia_en = forms.ChoiceField(label="Dónde se escribe la matrícula", choices=CuentaBancaria.REFERENCIA, initial=CuentaBancaria.AMBOS, widget=forms.RadioSelect)
    contacto_dudas = forms.CharField(label="Contacto para dudas (teléfono o correo)", max_length=150)
    nota_adicional = forms.CharField(label="Nota adicional (opcional)", max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 3}))
    principal = forms.BooleanField(label="Cuenta principal (la que aparece en la ficha de pago)", required=False)
    activa = forms.BooleanField(label="Activa", required=False, initial=True)

    def __init__(self, *args, cuenta=None, en_asistente=False, **kwargs):
        if cuenta is not None and "initial" not in kwargs:
            kwargs["initial"] = {
                "clabe": cuenta.clabe,
                "banco": cuenta.banco_id,
                "beneficiario": cuenta.beneficiario,
                "numero_cuenta": cuenta.numero_cuenta,
                "convenio": cuenta.convenio,
                "medios": list(cuenta.medios.values_list("pk", flat=True)),
                "referencia_en": cuenta.referencia_en,
                "contacto_dudas": cuenta.contacto_dudas,
                "nota_adicional": cuenta.nota_adicional,
                "principal": cuenta.principal,
                "activa": cuenta.activa,
            }
        elif cuenta is None and "initial" not in kwargs:
            kwargs["initial"] = {"medios": list(MedioPago.objects.filter(activo=True).values_list("pk", flat=True)), "activa": True, "principal": not CuentaBancaria.objects.filter(principal=True).exists()}
        super().__init__(*args, **kwargs)
        self.fields["banco"].queryset = Banco.objects.filter(activo=True)
        self.fields["medios"].queryset = MedioPago.objects.filter(activo=True)
        self.banco_propuesto = None
        self.banco_nuevo = None
        if en_asistente:
            del self.fields["principal"]
            del self.fields["activa"]

    def clean_numero_cuenta(self):
        valor = "".join(self.cleaned_data.get("numero_cuenta", "").split()).replace("-", "")
        if valor and not (valor.isascii() and valor.isdigit()):
            raise ValidationError("El número de cuenta solo lleva dígitos.")
        return valor

    def clean_convenio(self):
        valor = self.cleaned_data.get("convenio", "").strip()
        if valor and not (valor.isascii() and valor.replace(" ", "").isalnum()):
            raise ValidationError("El convenio solo lleva letras y números.")
        return valor

    def clean_contacto_dudas(self):
        return normalizar_contacto(self.cleaned_data.get("contacto_dudas"))

    def clean(self):
        datos = super().clean()
        if "clabe" not in datos:
            return datos
        try:
            analisis = nucleo_clabe.analizar(datos["clabe"])
        except nucleo_clabe.ErrorClabe as error:
            self.add_error("clabe", str(error))
            return datos
        datos["clabe"] = analisis["clabe"]
        clave = analisis["banco"]
        catalogo = Banco.objects.filter(clave=clave).first()
        elegido = datos.get("banco")
        otro = (datos.get("banco_otro") or "").strip()
        if elegido is not None:
            if elegido.clave != clave:
                destino = f"a {catalogo}" if catalogo else "a un banco que no está en el catálogo"
                self.add_error("banco", f"La CLABE empieza con {clave}, que corresponde {destino}; elegiste {elegido} (clave {elegido.clave}).")
                return datos
            datos["banco"] = elegido
        elif catalogo is not None:
            datos["banco"] = catalogo
            self.banco_propuesto = catalogo
        elif otro:
            datos["banco"] = None
            self.banco_nuevo = {"clave": clave, "nombre": otro}
        else:
            self.add_error("banco_otro", f"El prefijo {clave} de la CLABE no está en el catálogo de bancos. Escribe el nombre del banco en «Otro banco».")
            return datos
        if datos.get("principal") and "activa" in self.fields and not datos.get("activa"):
            self.add_error("principal", "La cuenta principal debe estar activa.")
        return datos
