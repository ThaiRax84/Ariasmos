from django import forms
from django.core.exceptions import ValidationError

from configuracion.models import parametro
from nucleo import telefono

from .models import CampoContacto, Contacto, RelacionContacto


def campos_activos():
    return list(CampoContacto.objects.filter(activo=True))


def prefijo():
    return str(parametro("prefijo_pais_telefono"))


def normalizar_telefono(texto):
    try:
        return telefono.normalizar(texto, prefijo(), parametro("digitos_telefono_nacional"))
    except telefono.TelefonoInvalido:
        raise ValidationError(
            f"Teléfono no válido: escribe {parametro('digitos_telefono_nacional')} dígitos, o el número completo con +{prefijo()}."
        )


class CampoTelefono(forms.CharField):
    def clean(self, valor):
        valor = super().clean(valor)
        if not valor:
            return ""
        return normalizar_telefono(valor)


def campo_formulario(campo, exigir_obligatorios):
    requerido = campo.obligatorio and exigir_obligatorios
    if campo.tipo == CampoContacto.TELEFONO:
        return CampoTelefono(label=campo.etiqueta, required=requerido, max_length=30, widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel"}))
    if campo.tipo == CampoContacto.CORREO:
        return forms.EmailField(label=campo.etiqueta, required=requerido, max_length=150)
    return forms.CharField(label=campo.etiqueta, required=requerido, max_length=200)


class FormularioContacto(forms.Form):
    contacto_nombre = forms.CharField(label="Nombre del contacto", max_length=150)
    contacto_relacion = forms.ModelChoiceField(label="Relación", queryset=RelacionContacto.objects.none(), required=False)

    def __init__(self, *args, exigir_obligatorios=True, inicial_contacto=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.campos = campos_activos()
        self.fields["contacto_relacion"].queryset = RelacionContacto.objects.filter(activa=True)
        for campo in self.campos:
            self.fields[campo.clave] = campo_formulario(campo, exigir_obligatorios)
        if inicial_contacto is not None:
            self.initial.setdefault("contacto_nombre", inicial_contacto.nombre)
            self.initial.setdefault("contacto_relacion", inicial_contacto.relacion_id)
            for campo in self.campos:
                self.initial.setdefault(campo.clave, inicial_contacto.valor(campo))

    def valores(self):
        return {str(c.pk): self.cleaned_data.get(c.clave, "") or "" for c in self.campos}


def mostrar_valor(campo, valor):
    if not valor:
        return ""
    if campo.tipo == CampoContacto.TELEFONO:
        return telefono.formatear(valor, prefijo())
    return valor


def detalle(contacto):
    filas = []
    for campo in CampoContacto.objects.all():
        valor = contacto.valor(campo)
        if valor:
            filas.append((campo.etiqueta, mostrar_valor(campo, valor), campo.principal))
    return filas


def principal(titular):
    return Contacto.objects.filter(titular=titular, principal=True).select_related("relacion").first()
