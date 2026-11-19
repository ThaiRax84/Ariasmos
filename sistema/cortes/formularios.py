from django import forms

from proyecto.carpetas import con_carpetas
from proyecto.dependencias import ConDependencias, depende

from . import entrega
from .models import TIPOS, Destino, ReglaDestino, nombre_de_tipo
from .models import niveles as opciones_nivel


@con_carpetas("ruta")
class FormularioDestino(ConDependencias, forms.Form):
    nombre = forms.CharField(label="Nombre del destino", max_length=60, initial="Carpeta de cortes")
    ruta = forms.CharField(label="Carpeta (ruta absoluta; puede ser una carpeta sincronizada con la nube)", max_length=400)
    activo = forms.BooleanField(label="Activo", required=False, initial=True)

    def __init__(self, *args, destino=None, niveles=None, **kwargs):
        super().__init__(*args, **kwargs)
        reglas = {r.tipo: r for r in destino.reglas.all()} if destino is not None else {}
        opciones = opciones_nivel()
        for tipo, _ in TIPOS:
            nombre = nombre_de_tipo(tipo)
            regla = reglas.get(tipo)
            self.fields[f"entregar_{tipo}"] = forms.BooleanField(label=f"Entregar: {nombre}", required=False, initial=regla.entregar if regla else True)
            self.fields[f"nivel_{tipo}"] = forms.ChoiceField(label=f"Nivel de detalle: {nombre}", choices=opciones, initial=regla.nivel if regla else (niveles or {}).get(tipo, "solo_nombres"))
            depende(self, f"nivel_{tipo}", f"entregar_{tipo}")
        if destino is not None:
            self.initial.setdefault("nombre", destino.nombre)
            self.initial.setdefault("ruta", destino.ruta)
            self.initial.setdefault("activo", destino.activo)

    def clean_ruta(self):
        try:
            return entrega.validar_ruta(self.cleaned_data["ruta"])
        except entrega.ErrorEntrega as error:
            raise forms.ValidationError(str(error))

    def clean(self):
        datos = super().clean()
        for tipo, _ in TIPOS:
            if not datos.get(f"nivel_{tipo}"):
                datos[f"nivel_{tipo}"] = self.fields[f"nivel_{tipo}"].initial
        return datos

    def guardar(self, destino=None):
        datos = self.cleaned_data
        destino = destino or Destino()
        destino.nombre, destino.ruta, destino.activo = datos["nombre"], datos["ruta"], datos["activo"]
        destino.save()
        for tipo, _ in TIPOS:
            ReglaDestino.objects.update_or_create(destino=destino, tipo=tipo, defaults={"entregar": datos[f"entregar_{tipo}"], "nivel": datos[f"nivel_{tipo}"]})
        return destino
