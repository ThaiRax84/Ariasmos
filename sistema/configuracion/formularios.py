import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django import forms

from banco.models import MedioPago
from caja.models import Caja, Denominacion
from cobros.formularios import MAXIMO_ABSURDO, CampoImporte, CampoImportePositivo, CampoPorcentaje, valor_de_recargo
from cobros.libro import ErrorLibro, validar_orden
from cobros.models import ConceptoCobro, ReglaRecargo
from cuentas.formularios import ContrasenaNueva
from nucleo.dinero import ErrorImporte, a_centavos
from proyecto.captura import CampoContrasena, CampoGuiadoTexto, CampoUsuario
from proyecto.carpetas import con_carpetas
from proyecto.dependencias import ConDependencias, depende
from proyecto.plegables import ConPlegables, plegar
from nucleo.matricula import LONGITUD_MAX, LONGITUD_MIN
from titulares.models import Agrupacion, CampoContacto, MotivoBaja, RelacionContacto

from . import moneda, zonas
from .grupos import MAXIMO_GRUPOS, clave_de_nombre, nombre_limpio
from .models import ESPECIALES, PARAMETROS, VOCABULARIO_BASE, Negocio, con_vocabulario, descripcion_parametro, opciones_vocabulario, vocabulario


ETIQUETAS_VOCABULARIO = {
    "titular": "Cómo se llama a cada quien se le cobra (singular)",
    "titulares": "Plural",
    "matricula": "Cómo se llama el número único de cada uno, el que se escribe al pagar en el banco",
    "agrupacion": "Cómo se llama un grupo de ellos (singular)",
    "agrupaciones": "Plural",
    "familia": "Cómo se llama a quienes paga la misma persona (singular)",
    "familias": "Plural",
    "padron": "Cómo se llama la lista de todos ellos",
    "descuento": "Cómo se llama una reducción en porcentaje autorizada a alguien",
    "publico": "Cómo se llama a quien compra sin estar registrado",
}

OPCIONALES_VOCABULARIO = ("padron", "descuento", "publico")


def validar_zona(valor, actual=""):
    if valor not in zonas.validas(actual):
        raise forms.ValidationError("Elige una zona horaria de la lista.")
    try:
        ZoneInfo(valor)
    except (ZoneInfoNotFoundError, ValueError):
        raise forms.ValidationError("Elige una zona horaria de la lista.")
    return valor


class CampoZona(forms.ChoiceField):
    def __init__(self, *args, actual="", **kwargs):
        kwargs.setdefault("label", "Zona horaria")
        kwargs.setdefault("help_text", "Escribe arriba el nombre de una ciudad para encontrarla. Entre paréntesis va la diferencia con la hora universal de hoy.")
        kwargs.setdefault("widget", forms.Select(attrs={"data-buscar-zona": ""}))
        super().__init__(*args, choices=zonas.opciones(actual), **kwargs)
        self.error_messages["invalid_choice"] = "Elige una zona horaria de la lista."
        self.error_messages["required"] = "Elige la zona horaria del negocio."


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.zona_actual = self.instance.zona_horaria if self.instance.pk else ""
        self.fields["zona_horaria"] = CampoZona(actual=self.zona_actual)
        self.fields["nombre"].help_text = "Así aparece en los recibos y en las fichas de pago."
        self.fields["nota_ficha"].help_text = "Se imprime en la ficha mientras no registres la cuenta del banco."
        self.order_fields(["nombre", "zona_horaria", "nota_ficha"])

    def clean_zona_horaria(self):
        return validar_zona(self.cleaned_data["zona_horaria"], self.zona_actual)


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
        labels = {"sede": "Número de sede", "ranuras": "Ranuras (sedes posibles)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["longitud_matricula"].label = f"Dígitos de {vocabulario()['matricula_min']}"
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
            self.fields[clave] = forms.CharField(label=etiquetas[clave], max_length=60, initial=(textos or VOCABULARIO_BASE)[clave], required=clave not in OPCIONALES_VOCABULARIO)


ETIQUETAS_ORDEN = {
    "recargos": "Primero los recargos por atraso",
    "vencimiento": "Lo que vence antes",
    "prioridad": "Según la prioridad de cada concepto",
}


class FormularioParametros(forms.Form):
    def __init__(self, *args, valores=None, **kwargs):
        super().__init__(*args, **kwargs)
        for clave, (defecto, _) in PARAMETROS.items():
            if clave in ESPECIALES:
                continue
            descripcion = descripcion_parametro(clave)
            inicial = (valores or {}).get(clave, defecto)
            if isinstance(defecto, str):
                self.fields[clave] = forms.CharField(label=descripcion, max_length=200, initial=inicial)
            else:
                self.fields[clave] = forms.IntegerField(label=descripcion, min_value=0, max_value=10 ** 11, initial=inicial)
        if "orden_reparto" in self.fields:
            import json

            self.fields["orden_reparto"].widget.attrs["data-orden"] = json.dumps(ETIQUETAS_ORDEN, ensure_ascii=False)

    def clean_tramos_cartera(self):
        from cortes.calculo import MAXIMO_TRAMOS, limites_tramos

        dias = limites_tramos(self.cleaned_data["tramos_cartera"])
        if dias is None:
            raise forms.ValidationError(f"Escribe de 1 a {MAXIMO_TRAMOS} números de días entre 1 y 3650, separados por comas, por ejemplo 30,60,90.")
        return ",".join(str(d) for d in dias)

    def _entre(self, clave, minimo, maximo):
        valor = self.cleaned_data[clave]
        if not minimo <= valor <= maximo:
            raise forms.ValidationError(f"Escribe un número entre {minimo} y {maximo}.")
        return valor

    def clean_porcentaje_aviso_tope(self):
        return self._entre("porcentaje_aviso_tope", 1, 100)

    def clean_rechazos_antes_de_autorizar(self):
        return self._entre("rechazos_antes_de_autorizar", 1, 100)

    def clean_respaldos_diarios(self):
        return self._entre("respaldos_diarios", 1, 3650)

    def clean_respaldos_mensuales(self):
        return self._entre("respaldos_mensuales", 0, 1200)

    def clean_horas_alerta_respaldo(self):
        return self._entre("horas_alerta_respaldo", 1, 8760)

    def clean_dias_prueba_restauracion(self):
        return self._entre("dias_prueba_restauracion", 1, 365)

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

    def clean_serie_retiros(self):
        return self._serie("serie_retiros")

    def clean_serie_devoluciones(self):
        return self._serie("serie_devoluciones")

    def clean_dias_sin_respaldo_alerta(self):
        valor = self.cleaned_data["dias_sin_respaldo_alerta"]
        if valor < 1:
            raise forms.ValidationError("Debe ser al menos 1.")
        return valor

    def clean_intentos_verificar_recibo_por_hora(self):
        valor = self.cleaned_data["intentos_verificar_recibo_por_hora"]
        if valor < 1:
            raise forms.ValidationError("Debe ser al menos 1.")
        return valor

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
    tipo = forms.ChoiceField(label="¿Es billete o moneda?", choices=[("billete", "Billete"), ("moneda", "Moneda")], initial="billete", widget=forms.RadioSelect)

    class Meta:
        model = Denominacion
        fields = ["valor", "tipo", "activa"]

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


class FormularioAsistenteInicio(ConPlegables, forms.Form):
    token = CampoContrasena(label="Token de instalación", max_length=200, autocompletar="off", help_text="Lo mostró el instalador (el comando inicializar) al terminar.")
    nombre = forms.CharField(label="Nombre del negocio", max_length=150, help_text="Así aparece en los recibos y en las fichas de pago.")
    zona_horaria = CampoZona()
    moneda = forms.ChoiceField(label="Moneda", initial=moneda.POR_DEFECTO, required=False, help_text="La moneda no se cambia cuando ya hay cobros.")
    plantilla = forms.ChoiceField(label="Plantilla inicial", widget=forms.RadioSelect, help_text="Trae el vocabulario, los conceptos y los roles de un tipo de negocio. Todo se puede cambiar.")
    archivo = forms.FileField(label="Archivo de plantilla (JSON de hasta 256 KB)", required=False)
    inventario = forms.BooleanField(label="Llevar inventario de los artículos que vende el negocio; se puede cambiar después en Configuración", required=False)

    def __init__(self, *args, plantillas=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.zona_actual = (self.initial or {}).get("zona_horaria") or ""
        self.fields["zona_horaria"] = CampoZona(actual=self.zona_actual, widget=forms.Select(attrs={"data-buscar-zona": "", "data-proponer-local": ""}))
        self.fields["plantilla"].choices = list((plantillas or {}).items()) + [(IMPORTAR, "Importar un archivo de plantilla (una propia en JSON)")]
        self.fields["moneda"].choices = moneda.opciones()
        if self.initial.get("plantilla") not in dict(self.fields["plantilla"].choices):
            self.initial.pop("plantilla", None)
        depende(self, "archivo", "plantilla", [IMPORTAR])

    def clean_moneda(self):
        try:
            return moneda.validar(self.cleaned_data["moneda"] or moneda.POR_DEFECTO)
        except moneda.ErrorMoneda:
            raise forms.ValidationError("Elige una moneda del catálogo.")

    def clean_zona_horaria(self):
        return validar_zona(self.cleaned_data["zona_horaria"], self.zona_actual)

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


class FormularioPersonalizar(ConDependencias, forms.Form):
    nuevo_nombre = forms.CharField(label="Agregar concepto: nombre", max_length=100, required=False)
    nuevo_tipo = forms.ChoiceField(label="Tipo", choices=ConceptoCobro.TIPOS, required=False)
    nuevo_periodicidad = forms.ChoiceField(label="Periodicidad", choices=[("", "—")] + ConceptoCobro.PERIODICIDADES, required=False)
    nuevo_aplica_a = forms.ChoiceField(label="Aplica a", choices=[], required=False)
    nuevo_recargo = forms.BooleanField(label="Con recargo por pago tardío", required=False)

    def __init__(self, *args, textos=None, conceptos=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.conceptos = list(conceptos)
        self.fields["nuevo_aplica_a"].choices = [c for c in opciones_vocabulario(ConceptoCobro.APLICA) if c[0] != ConceptoCobro.AGRUPACION]
        etiquetas = ETIQUETAS_VOCABULARIO
        campos = {}
        for clave in VOCABULARIO_BASE:
            campos[clave] = forms.CharField(label=etiquetas[clave], max_length=60, initial=(textos or VOCABULARIO_BASE)[clave], required=clave not in OPCIONALES_VOCABULARIO)
        for concepto in self.conceptos:
            campos[f"quitar_{concepto.pk}"] = forms.BooleanField(label=f"Quitar «{concepto.nombre}» ({concepto.get_tipo_display().lower()})", required=False)
        campos.update(self.fields)
        self.fields = campos
        depende(self, "nuevo_periodicidad", "nuevo_tipo", [ConceptoCobro.RECURRENTE])

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


class FormularioAsistenteConceptos(ConDependencias, forms.Form):
    def __init__(self, *args, conceptos=(), con_recargo=None, agrupaciones=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.conceptos = list(conceptos)
        self.agrupaciones = list(agrupaciones)
        for concepto in self.conceptos:
            self._campos_de_importe(concepto)
            if concepto.tipo == "recurrente":
                maximo = {"semanal": 7, "quincenal": 15}.get(concepto.periodicidad, 28)
                ayuda = {"semanal": "día de la semana en que vence (1 lunes a 7 domingo)", "quincenal": "día en que vence la primera quincena (1 a 15); la segunda, quince días después"}.get(concepto.periodicidad, "día de vencimiento (1 a 28)")
                self.fields[f"dia_{concepto.pk}"] = forms.IntegerField(label=f"{concepto.nombre}: {ayuda}", min_value=1, max_value=maximo, required=False)
            if concepto.nombre in (con_recargo or {}):
                sugerido = (con_recargo or {})[concepto.nombre] or {}
                self.fields[f"recargo_tipo_{concepto.pk}"] = forms.ChoiceField(label=f"{concepto.nombre}: cómo se calcula el recargo", choices=ReglaRecargo.TIPOS, initial=sugerido.get("tipo", "fijo"), required=False, widget=forms.RadioSelect)
                self.fields[f"recargo_tipo_{concepto.pk}"].en_fila = True
                self.fields[f"recargo_importe_{concepto.pk}"] = CampoImporte(label=f"{concepto.nombre}: importe del recargo", required=False, help_text="Ejemplo: 150.00. Vacío, sin recargo.")
                self.fields[f"recargo_porcentaje_{concepto.pk}"] = CampoPorcentaje(label=f"{concepto.nombre}: porcentaje del recargo", required=False, help_text="Sobre el saldo del cargo. Ejemplo: 10. Vacío, sin recargo.")
                self.fields[f"recargo_gracia_{concepto.pk}"] = forms.IntegerField(label=f"{concepto.nombre}: días de gracia", min_value=0, max_value=60, required=False, initial=sugerido.get("dias_gracia", 0), help_text="Días después del vencimiento en que todavía no se cobra.")
                depende(self, f"recargo_importe_{concepto.pk}", f"recargo_tipo_{concepto.pk}", [ReglaRecargo.FIJO])
                depende(self, f"recargo_porcentaje_{concepto.pk}", f"recargo_tipo_{concepto.pk}", [ReglaRecargo.PORCENTAJE])

    def _campos_de_importe(self, concepto):
        etiqueta = "precio general" if self.agrupaciones else "importe"
        self.fields[f"importe_{concepto.pk}"] = CampoImporte(label=f"{concepto.nombre}: {etiqueta}", required=False, maximo=MAXIMO_ABSURDO - 1)
        for agrupacion in self.agrupaciones:
            self.fields[f"importe_{concepto.pk}_{agrupacion.pk}"] = CampoImportePositivo(label=f"{concepto.nombre}: {agrupacion.nombre}", required=False)

    def grupos(self):
        resultado = []
        for concepto in self.conceptos:
            candidatos = (f"dia_{concepto.pk}",) if self.agrupaciones else (f"importe_{concepto.pk}", f"dia_{concepto.pk}")
            nombres = [n for n in candidatos if n in self.fields]
            recargo = [n for n in (f"recargo_tipo_{concepto.pk}", f"recargo_importe_{concepto.pk}", f"recargo_porcentaje_{concepto.pk}", f"recargo_gracia_{concepto.pk}") if n in self.fields]
            celdas = [self[f"importe_{concepto.pk}_{a.pk}"] for a in self.agrupaciones]
            resultado.append({"concepto": concepto, "general": self[f"importe_{concepto.pk}"], "celdas": celdas, "campos": [self[n] for n in nombres], "recargo": [self[n] for n in recargo]})
        return resultado

    def _exigir_precio_general(self, concepto, datos):
        general = f"importe_{concepto.pk}"
        con_importe = any(datos.get(f"importe_{concepto.pk}_{a.pk}") is not None for a in self.agrupaciones)
        if con_importe and datos.get(general) is None and general not in self.errors:
            self.add_error(general, "Escribe también el precio general.")

    def importes_por_grupo(self):
        return {(c.pk, a.pk): self.cleaned_data.get(f"importe_{c.pk}_{a.pk}") for c in self.conceptos for a in self.agrupaciones}

    def clean(self):
        datos = super().clean()
        for concepto in self.conceptos:
            self._exigir_precio_general(concepto, datos)
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


OPCIONES_GRUPOS = (
    ("no", "No, todos pagan lo mismo", "Te pregunto un solo importe por concepto."),
    ("si", "Sí, cada {agrupacion_min} tiene sus precios", "Primero me dices tus {agrupaciones_min} y después el importe de cada uno."),
)
CASILLAS_NUEVAS = 3


class FormularioAsistenteGrupos(ConDependencias, forms.Form):
    por_grupo = forms.ChoiceField(widget=forms.RadioSelect, label="Cobro por grupo")

    def __init__(self, *args, textos=None, nombres=(), por_grupo=False, **kwargs):
        super().__init__(*args, **kwargs)
        textos = textos if textos is not None else vocabulario()
        self.textos = textos
        self.fields["por_grupo"].choices = [(valor, con_vocabulario(titulo, textos)) for valor, titulo, _ in OPCIONES_GRUPOS]
        self.initial["por_grupo"] = "si" if por_grupo else "no"
        for numero in range(1, MAXIMO_GRUPOS + 1):
            clave = f"grupo_{numero}"
            self.fields[clave] = forms.CharField(label=f"{textos['agrupacion']} {numero}", max_length=100, required=False)
            self.initial[clave] = nombres[numero - 1] if numero <= len(nombres) else ""
            depende(self, clave, "por_grupo", ["si"])

    def opciones(self):
        return [(opcion, con_vocabulario(detalle, self.textos)) for opcion, (_, _, detalle) in zip(self["por_grupo"], OPCIONES_GRUPOS)]

    def casillas(self):
        escritos = [n for n in range(1, MAXIMO_GRUPOS + 1) if (self[f"grupo_{n}"].value() or "").strip()]
        visibles = min(MAXIMO_GRUPOS, (escritos[-1] if escritos else 0) + CASILLAS_NUEVAS)
        return [self[f"grupo_{n}"] for n in range(1, visibles + 1)]

    def nombres(self):
        escritos = (nombre_limpio(self.cleaned_data[f"grupo_{n}"]) for n in range(1, MAXIMO_GRUPOS + 1))
        return [nombre for nombre in escritos if nombre]

    def clean(self):
        datos = super().clean()
        if datos.get("por_grupo") != "si" or self.errors:
            return datos
        vistos = set()
        for numero in range(1, MAXIMO_GRUPOS + 1):
            clave = clave_de_nombre(datos[f"grupo_{numero}"])
            if not clave:
                continue
            if clave in vistos:
                self.add_error(f"grupo_{numero}", "Ese grupo ya está escrito.")
            vistos.add(clave)
        if len(vistos) < 2 and not self.errors:
            self.add_error(None, con_vocabulario("Escribe al menos dos {agrupaciones_min}.", self.textos))
        return datos


class CampoHora(CampoGuiadoTexto):
    acepta = "hora"
    maximo_tecleo = 5

    def clean(self, valor):
        valor = super().clean(valor)
        if valor in ("", None):
            return ""
        texto = valor.strip()
        if not re.fullmatch(r"([01][0-9]|2[0-3]):[0-5][0-9]", texto):
            raise forms.ValidationError("Escribe la hora como HH:MM, por ejemplo 18:00.")
        return texto


class FormularioCajaCortes(ConPlegables, forms.Form):
    control_denominaciones = forms.BooleanField(label="¿Contar billetes y monedas en cada movimiento de efectivo?", required=False, initial=True, help_text="Sí: al abrir, cobrar, dar cambio, vender, retirar, devolver, entregar, depositar y cerrar se cuentan las piezas, y el programa propone el cambio. No: solo se escriben importes.")
    periodo_retiros = forms.ChoiceField(label="Los topes de retiros se cuentan por", choices=[("dia", "Día"), ("semana", "Semana (lunes a domingo)")], widget=forms.RadioSelect)
    tope_retiro_individual = CampoImporte(label="Importe máximo de un retiro", help_text="Arriba de esto el retiro se vuelve solicitud y otra persona lo autoriza. Ejemplo: 500.00")
    tope_retiros_periodo = CampoImporte(label="Importe máximo de retiros en el periodo, por caja", help_text="Suma de todos los retiros del día o de la semana. Ejemplo: 1500.00")
    maximo_retiros_periodo = forms.IntegerField(label="Número máximo de retiros en el periodo, por caja", min_value=0, max_value=10000, help_text="Ejemplo: 3")
    maximo_efectivo_caja = CampoImporte(label="Efectivo máximo en una caja antes de avisar que se entregue", help_text="Solo es un aviso; 0 para no avisar.")
    dias_retiro_sin_revisar = forms.IntegerField(label="Días que un retiro puede quedar sin revisar antes de avisar", min_value=1, max_value=365, help_text="Ejemplo: 3")

    def __init__(self, *args, valores=None, **kwargs):
        super().__init__(*args, **kwargs)
        from cortes import calendario

        valores = valores or {}
        dias = {}
        horario = valores.get("calendario_corte", calendario.PROPUESTO)
        self.nombres_dias = []
        for numero, nombre in enumerate(calendario.DIAS):
            dias[f"corte_{numero}"] = CampoHora(label=f"{nombre}: hora límite del corte (vacío si ese día no hay corte)", max_length=5, required=False, initial=horario.get(str(numero), ""), widget=forms.TextInput(attrs={"placeholder": "Sin corte"}))
            dias[f"corte_{numero}"].dia = nombre
            self.nombres_dias.append(f"corte_{numero}")
        dias.update(self.fields)
        self.fields = dias
        self.fields["periodo_retiros"].en_fila = True
        for clave in ("control_denominaciones", "periodo_retiros", "tope_retiro_individual", "tope_retiros_periodo", "maximo_retiros_periodo", "maximo_efectivo_caja", "dias_retiro_sin_revisar"):
            if clave in valores:
                self.fields[clave].initial = valores[clave]
        plegar(self, "maximo_efectivo_caja", "dias_retiro_sin_revisar")

    def dias_corte(self):
        return [self[nombre] for nombre in self.nombres_dias]

    def topes_retiro(self):
        return [self[nombre] for nombre in ("periodo_retiros", "tope_retiro_individual", "tope_retiros_periodo", "maximo_retiros_periodo")]

    def avanzados(self):
        return [self[nombre] for nombre in ("maximo_efectivo_caja", "dias_retiro_sin_revisar")]

    def clean(self):
        datos = super().clean()
        calendario = {str(numero): datos[f"corte_{numero}"] for numero in range(7) if datos.get(f"corte_{numero}")}
        if not calendario and Caja.objects.filter(activa=True).exists():
            raise forms.ValidationError("Elige al menos un día con corte de caja: el negocio tiene cajas activas.")
        datos["calendario_corte"] = calendario
        return datos

    def valores(self):
        datos = self.cleaned_data
        return {
            "calendario_corte": datos["calendario_corte"],
            "control_denominaciones": 1 if datos.get("control_denominaciones") else 0,
            "periodo_retiros": datos["periodo_retiros"],
            "tope_retiro_individual": datos.get("tope_retiro_individual") or 0,
            "tope_retiros_periodo": datos.get("tope_retiros_periodo") or 0,
            "maximo_retiros_periodo": datos.get("maximo_retiros_periodo") or 0,
            "maximo_efectivo_caja": datos.get("maximo_efectivo_caja") or 0,
            "dias_retiro_sin_revisar": datos.get("dias_retiro_sin_revisar") or 3,
        }


def valores_caja():
    from cortes import calendario

    from .models import parametro

    valores = {"calendario_corte": calendario.actual()}
    for clave in ("control_denominaciones", "periodo_retiros", "tope_retiro_individual", "tope_retiros_periodo", "maximo_retiros_periodo", "maximo_efectivo_caja", "dias_retiro_sin_revisar"):
        valores[clave] = parametro(clave)
    valores["control_denominaciones"] = bool(valores["control_denominaciones"])
    return valores


def guardar_caja(valores):
    from cortes import calendario

    from .models import Parametro

    for clave, valor in valores.items():
        texto = calendario.a_texto(valor) if clave == "calendario_corte" else str(valor)
        Parametro.objects.update_or_create(clave=clave, defaults={"valor": texto})


def denominaciones_de_texto(texto):
    valores = []
    for parte in str(texto or "").replace(";", ",").split(","):
        parte = parte.strip()
        if not parte:
            continue
        try:
            valor = a_centavos(parte)
        except (ErrorImporte, ValueError):
            raise forms.ValidationError(f"«{parte[:20]}» no es una denominación válida.")
        if valor <= 0 or valor > 100000000:
            raise forms.ValidationError(f"«{parte[:20]}» no es una denominación válida.")
        valores.append(valor)
    if len(set(valores)) != len(valores):
        raise forms.ValidationError("Hay denominaciones repetidas.")
    if len(valores) > 30:
        raise forms.ValidationError("Escribe a lo más 30 denominaciones.")
    return sorted(valores, reverse=True)


class FormularioDenominacionesMoneda(forms.Form):
    denominaciones = forms.CharField(label="Billetes y monedas de tu moneda, separados por comas (por ejemplo: 100, 50, 20, 10, 5, 1, 0.50)", max_length=300)
    monedas = forms.CharField(label="¿Cuáles de esos son monedas? Escríbelos igual, separados por comas; los demás se toman como billetes", max_length=300, required=False)

    def __init__(self, *args, codigo="", **kwargs):
        super().__init__(*args, **kwargs)
        if codigo:
            self.fields["denominaciones"].label = f"Billetes y monedas de {codigo}, separados por comas (por ejemplo: 100, 50, 20, 10, 5, 1, 0.50)"

    def clean_denominaciones(self):
        valores = denominaciones_de_texto(self.cleaned_data["denominaciones"])
        if not valores:
            raise forms.ValidationError("Escribe al menos una denominación.")
        return valores

    def clean_monedas(self):
        texto = self.cleaned_data.get("monedas", "")
        return denominaciones_de_texto(texto) if texto.strip() else []

    def clean(self):
        datos = super().clean()
        if datos.get("denominaciones") and set(datos.get("monedas") or []) - set(datos["denominaciones"]):
            self.add_error("monedas", "Escribe solo valores que estén en la lista de arriba.")
        return datos

    def piezas(self):
        monedas = set(self.cleaned_data.get("monedas") or [])
        return [(valor, "moneda" if valor in monedas else "billete") for valor in self.cleaned_data["denominaciones"]]


TAMANOS_HOJA = (("carta", "Carta"), ("a4", "A4"))
CLAVES_REGLAS = ("prefijo_pais_telefono", "digitos_telefono_nacional", "tamano_hoja", "apellidos_obligatorios", "pedir_consentimiento", "texto_consentimiento")


class FormularioReglas(ConPlegables, forms.Form):
    prefijo_pais_telefono = forms.IntegerField(label="Prefijo de país de los teléfonos", min_value=1, max_value=999, help_text="Ejemplo: 52 en México.")
    digitos_telefono_nacional = forms.IntegerField(label="Dígitos de un teléfono nacional sin el prefijo", min_value=4, max_value=15, help_text="Ejemplo: 10 en México.")
    tamano_hoja = forms.ChoiceField(label="Tamaño de hoja de los PDF", choices=TAMANOS_HOJA, widget=forms.RadioSelect)
    apellidos_obligatorios = forms.BooleanField(label="Pedir apellidos al dar de alta (quítalo si a veces das de alta empresas)", required=False)
    pedir_consentimiento = forms.BooleanField(label="Pedir la constancia de consentimiento de datos al dar de alta", required=False)
    texto_consentimiento = forms.CharField(label="Texto de la constancia de consentimiento", max_length=200, required=False, help_text="Es lo que dice la constancia que se pide al dar de alta.")

    def __init__(self, *args, valores=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.anteriores = dict(valores or {})
        for clave, valor in self.anteriores.items():
            if clave in self.fields:
                self.fields[clave].initial = bool(valor) if isinstance(self.fields[clave], forms.BooleanField) else valor
        self.fields["tamano_hoja"].en_fila = True
        depende(self, "texto_consentimiento", "pedir_consentimiento")

    def clean(self):
        datos = super().clean()
        if datos.get("pedir_consentimiento") and not (datos.get("texto_consentimiento") or "").strip():
            self.add_error("texto_consentimiento", "Escribe el texto de la constancia o deja de pedirla.")
        return datos

    def valores(self):
        datos = self.cleaned_data
        return {
            "prefijo_pais_telefono": datos["prefijo_pais_telefono"],
            "digitos_telefono_nacional": datos["digitos_telefono_nacional"],
            "tamano_hoja": datos["tamano_hoja"],
            "apellidos_obligatorios": 1 if datos.get("apellidos_obligatorios") else 0,
            "pedir_consentimiento": 1 if datos.get("pedir_consentimiento") else 0,
            "texto_consentimiento": (datos.get("texto_consentimiento") or "").strip() or self.anteriores.get("texto_consentimiento") or PARAMETROS["texto_consentimiento"][0],
        }


def valores_reglas():
    from .models import parametro

    return {clave: parametro(clave) for clave in CLAVES_REGLAS}


TOPES_CARPETA = ("tope_pago_carpeta",)


@con_carpetas("carpeta_banco")
class FormularioCarpetaBanco(ConPlegables, forms.Form):
    carpeta_banco = forms.CharField(label="Carpeta vigilada del banco (opcional; ruta absoluta donde se deja el archivo descargado del banco)", max_length=400, required=False, help_text="Deja ahí el archivo que descargas de la banca en línea: el programa lo revisa cada pocos minutos y lo importa solo. Vacía, no se vigila ninguna carpeta.")
    tope_pago_carpeta = CampoImporte(label="Importe máximo de un pago que se aplica solo desde un archivo editable (0 sin tope individual)", required=False, maximo=10 ** 11, help_text="Un pago más grande que llegue en Excel o CSV queda retenido hasta que alguien con permiso de conciliación lo libere.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        plegar(self, *TOPES_CARPETA)

    def topes(self):
        return {clave: self.cleaned_data.get(clave) or 0 for clave in TOPES_CARPETA}

    def clean_carpeta_banco(self):
        from banco.carpeta import ErrorCarpeta, validar_carpeta

        valor = self.cleaned_data.get("carpeta_banco", "").strip()
        if not valor:
            return ""
        try:
            return validar_carpeta(valor)
        except ErrorCarpeta as error:
            raise forms.ValidationError(str(error))


@con_carpetas("carpeta_entrega", "carpeta_respaldo")
class FormularioAsistenteCortes(FormularioCarpetaBanco):
    carpeta_entrega = forms.CharField(label="Carpeta donde se entregan los cortes (opcional; ruta absoluta)", max_length=400, required=False)
    carpeta_respaldo = forms.CharField(label="Carpeta de respaldo (opcional; de preferencia sincronizada con la nube o en un disco externo)", max_length=400, required=False)
    field_order = ["carpeta_entrega", "carpeta_respaldo", "carpeta_banco", "tope_pago_carpeta"]

    def __init__(self, *args, niveles=None, carpeta="", carpeta_banco="", pide_clave=False, topes=None, **kwargs):
        super().__init__(*args, **kwargs)
        from banco.formularios import campos_topes, iniciales_topes
        from cortes.models import TIPOS, nombre_de_tipo
        from cortes.models import niveles as opciones_nivel

        self.fields.update(campos_topes())
        for nombre, valor in iniciales_topes(topes or {}).items():
            self.initial.setdefault(nombre, valor)
        from actualizaciones import llaves

        if llaves.disponibles():
            self.fields["actualizaciones_activas"] = forms.BooleanField(label="Buscar actualizaciones del programa (opcional; se puede activar después en Configuración)", required=False)
            self.fields["repositorio_canal"] = forms.CharField(label="Repositorio del canal de versiones (propietario/nombre)", max_length=140, required=False)
            self.fields["clave_canal"] = forms.CharField(label="Clave de solo lectura del canal (se guarda cifrada y no se vuelve a mostrar)", max_length=300, required=False, widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}))

        opciones = opciones_nivel()
        for tipo, _ in TIPOS:
            self.fields[f"nivel_{tipo}"] = forms.ChoiceField(label=f"Nivel de detalle: {nombre_de_tipo(tipo)}", choices=opciones, initial=(niveles or {}).get(tipo, "solo_nombres"))
        self.initial.setdefault("carpeta_respaldo", carpeta)
        self.initial.setdefault("carpeta_banco", carpeta_banco)
        from .models import parametro

        for clave in TOPES_CARPETA:
            self.initial.setdefault(clave, int(parametro(clave)))
        if pide_clave:
            self.fields["guardada"] = forms.BooleanField(label="Ya imprimí la clave de recuperación y la guardé fuera de este equipo", required=True)
        self.fields["carpeta_entrega"].help_text = "Ahí se dejan el corte diario, el corte mayor de cada mes y la lista de cobranza, en PDF, CSV y JSON."
        self.fields["carpeta_respaldo"].help_text = "El respaldo diario va cifrado. Mejor si la carpeta está fuera de esta computadora."
        self.fields["carpeta_banco"].help_text = "Deja ahí el archivo que descargas de la banca en línea: el programa lo revisa cada pocos minutos y lo importa solo."
        self.ayuda_avanzados = "Un estado de cuenta en PDF que continúa al anterior aplica sus pagos de inmediato. Un Excel o CSV los aplica solo mientras no pase de los topes del día y del acumulado; lo que no cabe queda retenido hasta que alguien con permiso de conciliación lo libere. Con los topes en 0, todo Excel o CSV queda retenido."
        avanzados = [nombre for nombre in self.fields if nombre.startswith("tope_") or nombre.startswith("nivel_") or nombre in ("actualizaciones_activas", "repositorio_canal", "clave_canal")]
        plegar(self, *avanzados)
        depende(self, "repositorio_canal", "actualizaciones_activas")
        depende(self, "clave_canal", "actualizaciones_activas")

    def _ruta(self, clave):
        from cortes.entrega import ErrorEntrega, validar_ruta

        valor = self.cleaned_data.get(clave, "").strip()
        if not valor:
            return ""
        try:
            return validar_ruta(valor)
        except ErrorEntrega as error:
            raise forms.ValidationError(str(error))

    def clean(self):
        from actualizaciones.canales.github import clave_valida, repositorio_valido

        datos = super().clean()
        if "actualizaciones_activas" not in self.fields:
            return datos
        repositorio = (datos.get("repositorio_canal") or "").strip()
        clave = (datos.get("clave_canal") or "").strip()
        if repositorio and not repositorio_valido(repositorio):
            self.add_error("repositorio_canal", "Escribe el repositorio como propietario/nombre.")
        if clave and not clave_valida(clave):
            self.add_error("clave_canal", "No tiene el formato de una clave de GitHub.")
        if datos.get("actualizaciones_activas") and not (repositorio and clave):
            self.add_error("actualizaciones_activas", "Para activarlas escribe el repositorio y la clave del canal.")
        datos["repositorio_canal"], datos["clave_canal"] = repositorio, clave
        return datos

    def actualizaciones(self):
        if "actualizaciones_activas" not in self.fields:
            return None
        datos = self.cleaned_data
        if not (datos.get("actualizaciones_activas") or datos.get("repositorio_canal") or datos.get("clave_canal")):
            return None
        return {"activa": bool(datos.get("actualizaciones_activas")), "repositorio": datos.get("repositorio_canal", ""), "clave": datos.get("clave_canal", "")}

    def topes_banco(self):
        from banco.formularios import topes_de

        return topes_de(self.cleaned_data)

    def clean_carpeta_entrega(self):
        return self._ruta("carpeta_entrega")

    def clean_carpeta_respaldo(self):
        return self._ruta("carpeta_respaldo")


class FormularioAsistenteUsuario(ContrasenaNueva):
    usuario = CampoUsuario(label="Usuario")
    nombre = forms.CharField(label="Nombre completo", max_length=150)
    field_order = ["usuario", "nombre", "contrasena1", "contrasena2"]


class FormularioMarca(ConDependencias, forms.Form):
    color_principal = CampoGuiadoTexto(label="Color principal", max_length=7, required=False, acepta="color", maximo_tecleo=7, help_text="Botones, menú activo y, si es oscuro, el texto. Ejemplo: #1F1A4E")
    color_acento = CampoGuiadoTexto(label="Color de acento", max_length=7, required=False, acepta="color", maximo_tecleo=7, help_text="Franja superior, subrayados y fondos suaves. Ejemplo: #F58634")
    barra = forms.ChoiceField(label="Color de la barra superior", choices=[("principal", "El color principal de mi marca"), ("otro", "Otro color")], initial="principal", required=False, widget=forms.RadioSelect)
    color_barra = CampoGuiadoTexto(label="Color de la barra", max_length=7, required=False, acepta="color", maximo_tecleo=7, help_text="El texto de la barra se vuelve claro u oscuro solo. Ejemplo: #1F1A4E")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        depende(self, "color_barra", "barra", ["otro"])

    def clean(self):
        from .marca import MarcaInvalida, validar_color

        datos = super().clean()
        principal, acento = datos.get("color_principal") or "", datos.get("color_acento") or ""
        if bool(principal) != bool(acento):
            raise forms.ValidationError("Escribe los dos colores o deja los dos vacíos.")
        pedidos = [("color_principal", principal), ("color_acento", acento)]
        if datos.get("barra") == "otro":
            pedidos.append(("color_barra", datos.get("color_barra") or ""))
            if not pedidos[-1][1]:
                self.add_error("color_barra", "Elige el color de la barra o usa el principal.")
        for campo, valor in pedidos:
            if valor:
                try:
                    datos[campo] = validar_color(valor)
                except MarcaInvalida as error:
                    self.add_error(campo, str(error))
        return datos


class FormularioLogo(forms.Form):
    archivo = forms.FileField(label="Logo: imagen JPEG o PNG, hasta 1 MB", widget=forms.ClearableFileInput(attrs={"accept": "image/png,image/jpeg"}))
