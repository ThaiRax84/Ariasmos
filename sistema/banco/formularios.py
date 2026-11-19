from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from nucleo import clabe as nucleo_clabe
from configuracion.models import vocabulario
from proyecto.captura import CampoDigitos
from proyecto.dependencias import depende
from proyecto.plegables import ConPlegables, plegar
from titulares.contactos import formatear_telefono, normalizar_telefono

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
    return formatear_telefono(normalizar_telefono(valor))


class FormularioCuenta(ConPlegables, forms.Form):
    tipo = forms.ChoiceField(label="Cómo se identifica la cuenta", choices=[(CuentaBancaria.CLABE, "CLABE de 18 dígitos (México)"), (CuentaBancaria.OTRA, "Otra cuenta: número y banco escritos")], initial=CuentaBancaria.CLABE, required=False, widget=forms.RadioSelect)
    clabe = CampoDigitos(label="CLABE (18 dígitos)", max_length=30, maximo_tecleo=18, required=False, widget=forms.TextInput(attrs={"autocomplete": "off"}))
    banco = forms.ModelChoiceField(label="Banco", queryset=Banco.objects.none(), required=False, empty_label="Proponer según la CLABE")
    banco_otro = forms.CharField(label="Nombre del banco", max_length=80, required=False, help_text="Con CLABE solo hace falta si su prefijo no está en el catálogo de bancos.")
    beneficiario = forms.CharField(label="Beneficiario (como lo pide el banco)", max_length=150)
    numero_cuenta = forms.CharField(label="Número de cuenta", max_length=34, required=False)
    convenio = forms.CharField(label="Convenio de cobranza referenciada (opcional)", max_length=30, required=False)
    medios = forms.ModelMultipleChoiceField(label="Medios aceptados", queryset=MedioPago.objects.none(), required=False, widget=forms.CheckboxSelectMultiple)
    referencia_en = forms.ChoiceField(label="Dónde se escribe el número de pago", choices=CuentaBancaria.REFERENCIA, initial=CuentaBancaria.AMBOS, widget=forms.RadioSelect)
    contacto_dudas = forms.CharField(label="Contacto para dudas (teléfono o correo)", max_length=150)
    nota_adicional = forms.CharField(label="Nota adicional (opcional)", max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 3}))
    principal = forms.BooleanField(label="Cuenta principal (la que aparece en la ficha de pago)", required=False)
    activa = forms.BooleanField(label="Activa", required=False, initial=True)

    def __init__(self, *args, cuenta=None, en_asistente=False, **kwargs):
        if cuenta is not None and "initial" not in kwargs:
            kwargs["initial"] = {
                "tipo": cuenta.tipo,
                "clabe": cuenta.clabe,
                "banco": cuenta.banco_id,
                "banco_otro": cuenta.banco_nombre,
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
        self.fields["referencia_en"].label = f"Dónde se escribe {vocabulario()['matricula_min']} al pagar"
        if en_asistente:
            del self.fields["principal"]
            del self.fields["activa"]
        self.fields["tipo"].en_fila = True
        depende(self, "clabe", "tipo", [CuentaBancaria.CLABE])
        depende(self, "banco", "tipo", [CuentaBancaria.CLABE])
        depende(self, "banco_otro", "tipo", etiquetas={CuentaBancaria.CLABE: "Otro banco", CuentaBancaria.OTRA: "Nombre del banco"})
        depende(self, "numero_cuenta", "tipo", etiquetas={CuentaBancaria.CLABE: "Número de cuenta (opcional)", CuentaBancaria.OTRA: "Número de cuenta"})
        plegar(self, "convenio", "nota_adicional", "referencia_en")

    def clean_numero_cuenta(self):
        valor = "".join(self.cleaned_data.get("numero_cuenta", "").split()).replace("-", "").upper()
        if valor and not (valor.isascii() and valor.isalnum()):
            raise ValidationError("El número de cuenta solo lleva letras y dígitos.")
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
        if datos.get("principal") and "activa" in self.fields and not datos.get("activa"):
            self.add_error("principal", "La cuenta principal debe estar activa.")
        datos["tipo"] = datos.get("tipo") or CuentaBancaria.CLABE
        if datos["tipo"] == CuentaBancaria.OTRA:
            datos["clabe"] = ""
            datos["banco"] = None
            if not datos.get("numero_cuenta"):
                self.add_error("numero_cuenta", "Escribe el número de la cuenta.")
            if not (datos.get("banco_otro") or "").strip():
                self.add_error("banco_otro", "Escribe el nombre del banco.")
            return datos
        if datos.get("numero_cuenta") and not datos["numero_cuenta"].isdigit():
            self.add_error("numero_cuenta", "El número de cuenta solo lleva dígitos.")
        if not datos.get("clabe"):
            if "clabe" not in self.errors:
                self.add_error("clabe", "Escribe la CLABE de 18 dígitos o elige «Otra cuenta».")
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
        return datos


NOMBRES_DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
MAXIMO_TOPE = 10 ** 11


def campos_topes():
    from cobros.formularios import CampoImporte

    from .conciliacion import ACUMULADO, DIAS_SEMANA

    campos = {}
    for numero, clave in enumerate(DIAS_SEMANA):
        campos[f"tope_{clave}"] = CampoImporte(label=f"{NOMBRES_DIAS[numero]}: lo máximo que se aplica solo en el día (en 0 se retiene todo ese día)", required=False, maximo=MAXIMO_TOPE)
    campos[f"tope_{ACUMULADO}"] = CampoImporte(
        label="Tope acumulado: lo máximo aplicado desde archivos editables que todavía no respalda un estado en PDF (en 0 se retiene todo archivo editable)", required=False, maximo=MAXIMO_TOPE
    )
    return campos


def topes_de(datos):
    from .conciliacion import CLAVES_TOPES

    return {clave: int(datos.get(f"tope_{clave}") or 0) for clave in CLAVES_TOPES}


def iniciales_topes(valores):
    return {f"tope_{clave}": valor for clave, valor in valores.items()}


class FormularioTopes(forms.Form):
    def __init__(self, *args, valores=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.update(campos_topes())
        for nombre, valor in iniciales_topes(valores or {}).items():
            self.initial.setdefault(nombre, valor)

    def topes(self):
        return topes_de(self.cleaned_data)
