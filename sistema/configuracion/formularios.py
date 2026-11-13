import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django import forms

from banco.models import MedioPago
from caja.models import Caja, Denominacion
from cobros.formularios import CampoImporte, CampoPorcentaje, valor_de_recargo
from cobros.libro import ErrorLibro, validar_orden
from cobros.models import ConceptoCobro, ReglaRecargo
from cuentas.formularios import ContrasenaNueva
from proyecto.captura import CampoContrasena, CampoUsuario
from nucleo.matricula import LONGITUD_MAX, LONGITUD_MIN
from titulares.models import Agrupacion, CampoContacto, MotivoBaja, RelacionContacto

from . import moneda
from .models import PARAMETROS, VOCABULARIO_BASE, Negocio


ETIQUETAS_VOCABULARIO = {
    "titular": "Cómo se llama a cada titular (singular)",
    "titulares": "Plural",
    "matricula": "Cómo se llama la matrícula",
    "agrupacion": "Cómo se llama una agrupación (singular)",
    "agrupaciones": "Plural",
    "familia": "Cómo se llama a quienes paga la misma persona (singular)",
    "familias": "Plural",
}


def validar_zona(valor):
    try:
        ZoneInfo(valor)
    except (ZoneInfoNotFoundError, ValueError):
        raise forms.ValidationError("Zona horaria desconocida.")
    return valor


class FormularioNegocio(forms.ModelForm):
    nota_ficha = forms.CharField(label="Nota de la ficha mientras no haya cuenta principal", max_length=1000, required=False, widget=forms.Textarea(attrs={"rows": 3}))

    class Meta:
        model = Negocio
        fields = ["nombre", "zona_horaria", "nota_ficha"]
        labels = {
            "nombre": "Nombre del negocio",
            "zona_horaria": "Zona horaria",
            "nota_ficha": "Nota de la ficha mientras no haya cuenta principal",
        }
        widgets = {"nota_ficha": forms.Textarea(attrs={"rows": 3})}

    def clean_zona_horaria(self):
        return validar_zona(self.cleaned_data["zona_horaria"])


class FormularioMoneda(forms.Form):
    moneda = forms.ChoiceField(label="Moneda del negocio")

    def __init__(self, *args, bloqueada=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["moneda"].choices = moneda.opciones()
        if bloqueada:
            self.fields["moneda"].disabled = True

    def clean_moneda(self):
        try:
            return moneda.validar(self.cleaned_data["moneda"])
        except moneda.ErrorMoneda:
            raise forms.ValidationError("Elige una moneda del catálogo.")


class FormularioAjustesAvanzados(forms.ModelForm):
    class Meta:
        model = Negocio
        fields = ["longitud_matricula", "sede", "ranuras"]
        labels = {"longitud_matricula": "Longitud de la matrícula", "sede": "Número de sede", "ranuras": "Ranuras (sedes posibles)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.matriculas_emitidas:
            for campo in self.fields.values():
                campo.disabled = True

    def clean(self):
        datos = super().clean()
        longitud, sede, ranuras = datos.get("longitud_matricula"), datos.get("sede"), datos.get("ranuras")
        if longitud is not None and not LONGITUD_MIN <= longitud <= LONGITUD_MAX:
            raise forms.ValidationError(f"La longitud debe estar entre {LONGITUD_MIN} y {LONGITUD_MAX}.")
        if ranuras is not None and ranuras < 1:
            raise forms.ValidationError("Debe haber al menos una ranura.")
        if sede is not None and ranuras is not None and sede >= ranuras:
            raise forms.ValidationError("La sede debe ser menor que el número de ranuras.")
        return datos


class FormularioVocabulario(forms.Form):
    def __init__(self, *args, textos=None, **kwargs):
        super().__init__(*args, **kwargs)
        etiquetas = ETIQUETAS_VOCABULARIO
        for clave in VOCABULARIO_BASE:
            self.fields[clave] = forms.CharField(label=etiquetas[clave], max_length=60, initial=(textos or VOCABULARIO_BASE)[clave])


class FormularioParametros(forms.Form):
    def __init__(self, *args, valores=None, **kwargs):
        super().__init__(*args, **kwargs)
        for clave, (defecto, descripcion) in PARAMETROS.items():
            inicial = (valores or {}).get(clave, defecto)
            if isinstance(defecto, str):
                self.fields[clave] = forms.CharField(label=descripcion, max_length=200, initial=inicial)
            else:
                self.fields[clave] = forms.IntegerField(label=descripcion, min_value=0, max_value=10 ** 11, initial=inicial)

    def clean_orden_reparto(self):
        try:
            return validar_orden(self.cleaned_data["orden_reparto"])
        except ErrorLibro as error:
            raise forms.ValidationError(str(error))

    def _serie(self, clave):
        serie = self.cleaned_data[clave].strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,10}", serie):
            raise forms.ValidationError("Usa de 1 a 10 letras mayúsculas o números.")
        return serie

    def clean_serie_recibos_banco(self):
        return self._serie("serie_recibos_banco")

    def clean_serie_recibos_saldo_inicial(self):
        return self._serie("serie_recibos_saldo_inicial")

    def clean_aplicar_solo_por_pagador(self):
        valor = self.cleaned_data["aplicar_solo_por_pagador"]
        if valor not in (0, 1):
            raise forms.ValidationError("Escribe 0 o 1.")
        return valor

    def clean_confirmaciones_pagador_confiable(self):
        valor = self.cleaned_data["confirmaciones_pagador_confiable"]
        if valor < 1:
            raise forms.ValidationError("Debe ser al menos 1.")
        return valor

    def _hora(self, clave):
        texto = self.cleaned_data[clave].strip()
        if not re.fullmatch(r"([01][0-9]|2[0-3]):[0-5][0-9]", texto):
            raise forms.ValidationError("Escribe la hora como HH:MM, por ejemplo 18:00.")
        return texto

    def clean_hora_limite_corte_diario(self):
        return self._hora("hora_limite_corte_diario")

    def clean_hora_respaldo(self):
        return self._hora("hora_respaldo")

    def clean_dia_corte_mayor(self):
        dia = self.cleaned_data["dia_corte_mayor"]
        if not 1 <= dia <= 28:
            raise forms.ValidationError("El día va de 1 a 28.")
        return dia

    def clean_dia_semana_cobranza(self):
        dia = self.cleaned_data["dia_semana_cobranza"]
        if dia > 7:
            raise forms.ValidationError("Usa 1 (lunes) a 7 (domingo), o 0 para no generarla.")
        return dia

    def clean_dia_generacion_cargos(self):
        dia = self.cleaned_data["dia_generacion_cargos"]
        if not 1 <= dia <= 28:
            raise forms.ValidationError("El día va de 1 a 28.")
        return dia


class FormularioAgrupacion(forms.ModelForm):
    class Meta:
        model = Agrupacion
        fields = ["nombre", "activa"]


class FormularioMotivo(forms.ModelForm):
    class Meta:
        model = MotivoBaja
        fields = ["nombre", "activo"]


class FormularioRelacion(forms.ModelForm):
    class Meta:
        model = RelacionContacto
        fields = ["nombre", "activa"]


class FormularioCaja(forms.ModelForm):
    class Meta:
        model = Caja
        fields = ["nombre", "serie_recibos", "activa"]
        labels = {"serie_recibos": "Serie de los recibos (letras mayúsculas y números)"}

    def clean_serie_recibos(self):
        serie = self.cleaned_data["serie_recibos"].strip().upper()
        if not (serie.isascii() and serie.isalnum() and 1 <= len(serie) <= 10):
            raise forms.ValidationError("Solo letras y números, hasta 10.")
        if self.instance.pk and self.instance.serie_recibos != serie and self.instance.turnos.exists():
            raise forms.ValidationError("La caja ya emitió recibos: la serie no se cambia.")
        return serie


class FormularioDenominacion(forms.ModelForm):
    valor = CampoImporte(label="Valor")

    class Meta:
        model = Denominacion
        fields = ["valor", "activa"]

    def clean_valor(self):
        valor = self.cleaned_data["valor"]
        if not valor or valor <= 0:
            raise forms.ValidationError("El valor debe ser mayor que cero.")
        return valor


class FormularioMedioPago(forms.ModelForm):
    class Meta:
        model = MedioPago
        fields = ["nombre", "orden", "activo"]


class FormularioCampoContacto(forms.ModelForm):
    class Meta:
        model = CampoContacto
        fields = ["etiqueta", "tipo", "obligatorio", "principal", "orden", "activo"]
        labels = {"obligatorio": "Obligatorio en el alta", "principal": "Medio principal para avisos"}

    def clean(self):
        datos = super().clean()
        if datos.get("principal") and not datos.get("activo"):
            raise forms.ValidationError("El medio principal debe estar activo.")
        if datos.get("obligatorio") and not datos.get("activo"):
            raise forms.ValidationError("Un campo obligatorio debe estar activo.")
        return datos


IMPORTAR = "importar"


class FormularioAsistenteInicio(forms.Form):
    token = CampoContrasena(label="Token de instalación (lo mostró el comando inicializar)", max_length=200, autocompletar="off")
    nombre = forms.CharField(label="Nombre del negocio", max_length=150)
    zona_horaria = forms.CharField(label="Zona horaria", max_length=64, initial="America/Mexico_City")
    moneda = forms.ChoiceField(label="Moneda", initial=moneda.POR_DEFECTO, required=False)
    plantilla = forms.ChoiceField(label="Plantilla inicial", widget=forms.RadioSelect)
    archivo = forms.FileField(label="Archivo de plantilla (solo si eliges importar; JSON de hasta 256 KB)", required=False)

    def __init__(self, *args, plantillas=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plantilla"].choices = list((plantillas or {}).items()) + [(IMPORTAR, "Importar un archivo de plantilla")]
        self.fields["moneda"].choices = moneda.opciones()

    def clean_moneda(self):
        try:
            return moneda.validar(self.cleaned_data["moneda"] or moneda.POR_DEFECTO)
        except moneda.ErrorMoneda:
            raise forms.ValidationError("Elige una moneda del catálogo.")

    def clean_zona_horaria(self):
        return validar_zona(self.cleaned_data["zona_horaria"])

    def clean(self):
        datos = super().clean()
        if datos.get("plantilla") == IMPORTAR and not datos.get("archivo"):
            self.add_error("archivo", "Elige el archivo de plantilla que quieres importar.")
        return datos


class FormularioRevisarPlantilla(forms.Form):
    confirmo = forms.BooleanField(label="Leí las advertencias y quiero aplicar la plantilla así", required=False)

    def __init__(self, *args, advertencias=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.advertencias = advertencias
        if not advertencias:
            del self.fields["confirmo"]

    def clean(self):
        datos = super().clean()
        if self.advertencias and not datos.get("confirmo"):
            raise forms.ValidationError("La plantilla tiene advertencias: confirma explícitamente para aplicarla.")
        return datos


class FormularioPersonalizar(forms.Form):
    nuevo_nombre = forms.CharField(label="Agregar concepto: nombre", max_length=100, required=False)
    nuevo_tipo = forms.ChoiceField(label="Tipo", choices=ConceptoCobro.TIPOS, required=False)
    nuevo_periodicidad = forms.ChoiceField(label="Periodicidad (solo recurrentes)", choices=[("", "—")] + ConceptoCobro.PERIODICIDADES, required=False)
    nuevo_aplica_a = forms.ChoiceField(label="Aplica a", choices=[c for c in ConceptoCobro.APLICA if c[0] != ConceptoCobro.AGRUPACION], required=False)
    nuevo_recargo = forms.BooleanField(label="Con recargo por pago tardío", required=False)

    def __init__(self, *args, textos=None, conceptos=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.conceptos = list(conceptos)
        etiquetas = ETIQUETAS_VOCABULARIO
        campos = {}
        for clave in VOCABULARIO_BASE:
            campos[clave] = forms.CharField(label=etiquetas[clave], max_length=60, initial=(textos or VOCABULARIO_BASE)[clave])
        for concepto in self.conceptos:
            campos[f"quitar_{concepto.pk}"] = forms.BooleanField(label=f"Quitar «{concepto.nombre}» ({concepto.get_tipo_display().lower()})", required=False)
        campos.update(self.fields)
        self.fields = campos

    def clean(self):
        datos = super().clean()
        nombre = (datos.get("nuevo_nombre") or "").strip()
        if nombre:
            if ConceptoCobro.objects.filter(nombre__iexact=nombre).exists():
                self.add_error("nuevo_nombre", "Ya existe un concepto con ese nombre.")
            if not datos.get("nuevo_tipo"):
                self.add_error("nuevo_tipo", "Elige el tipo del concepto.")
            if datos.get("nuevo_tipo") == ConceptoCobro.RECURRENTE and not datos.get("nuevo_periodicidad"):
                self.add_error("nuevo_periodicidad", "Un concepto recurrente necesita periodicidad.")
        datos["nuevo_nombre"] = nombre
        return datos


class FormularioAsistenteConceptos(forms.Form):
    def __init__(self, *args, conceptos=(), con_recargo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.conceptos = list(conceptos)
        for concepto in self.conceptos:
            self.fields[f"importe_{concepto.pk}"] = CampoImporte(label=f"{concepto.nombre}: importe", required=False)
            if concepto.tipo == "recurrente":
                self.fields[f"dia_{concepto.pk}"] = forms.IntegerField(label=f"{concepto.nombre}: día de vencimiento (1 a 28)", min_value=1, max_value=28, required=False)
            if concepto.nombre in (con_recargo or {}):
                sugerido = (con_recargo or {})[concepto.nombre] or {}
                self.fields[f"recargo_tipo_{concepto.pk}"] = forms.ChoiceField(label=f"{concepto.nombre}: tipo de recargo", choices=ReglaRecargo.TIPOS, initial=sugerido.get("tipo", "fijo"), required=False)
                self.fields[f"recargo_importe_{concepto.pk}"] = CampoImporte(label=f"{concepto.nombre}: importe fijo del recargo (si el tipo es fijo)", required=False)
                self.fields[f"recargo_porcentaje_{concepto.pk}"] = CampoPorcentaje(label=f"{concepto.nombre}: porcentaje del recargo (si el tipo es porcentaje)", required=False)
                self.fields[f"recargo_gracia_{concepto.pk}"] = forms.IntegerField(label=f"{concepto.nombre}: días de gracia", min_value=0, max_value=60, required=False, initial=sugerido.get("dias_gracia", 0))

    def clean(self):
        datos = super().clean()
        for concepto in self.conceptos:
            clave_tipo = f"recargo_tipo_{concepto.pk}"
            if clave_tipo not in self.fields:
                continue
            importe, porcentaje = datos.get(f"recargo_importe_{concepto.pk}"), datos.get(f"recargo_porcentaje_{concepto.pk}")
            datos[f"recargo_valor_{concepto.pk}"] = None
            if importe is None and porcentaje is None:
                continue
            tipo = datos.get(clave_tipo) or ReglaRecargo.FIJO
            try:
                datos[f"recargo_valor_{concepto.pk}"] = valor_de_recargo(tipo, importe, porcentaje)
            except forms.ValidationError as error:
                self.add_error(f"recargo_porcentaje_{concepto.pk}" if tipo == ReglaRecargo.PORCENTAJE else f"recargo_importe_{concepto.pk}", error)
        return datos


class FormularioAsistenteUsuario(ContrasenaNueva):
    usuario = CampoUsuario(label="Usuario")
    nombre = forms.CharField(label="Nombre completo", max_length=150)
    field_order = ["usuario", "nombre", "contrasena1", "contrasena2"]
