from django import forms

from . import entrega
from .models import NIVELES, TIPOS, Destino, ReglaDestino


class FormularioDestino(forms.Form):
    nombre = forms.CharField(label="Nombre del destino", max_length=60, initial="Carpeta de cortes")
    ruta = forms.CharField(label="Carpeta (ruta absoluta; puede ser una carpeta sincronizada con la nube)", max_length=400)
    activo = forms.BooleanField(label="Activo", required=False, initial=True)

    def __init__(self, *args, destino=None, niveles=None, **kwargs):
        super().__init__(*args, **kwargs)
        reglas = {r.tipo: r for r in destino.reglas.all()} if destino is not None else {}
        for tipo, nombre in TIPOS:
            regla = reglas.get(tipo)
            self.fields[f"entregar_{tipo}"] = forms.BooleanField(label=f"Entregar: {nombre}", required=False, initial=regla.entregar if regla else True)
            self.fields[f"nivel_{tipo}"] = forms.ChoiceField(label=f"Nivel de detalle: {nombre}", choices=NIVELES, initial=regla.nivel if regla else (niveles or {}).get(tipo, "solo_nombres"))
        if destino is not None:
            self.initial.setdefault("nombre", destino.nombre)
            self.initial.setdefault("ruta", destino.ruta)
            self.initial.setdefault("activo", destino.activo)

    def clean_ruta(self):
        try:
            return entrega.validar_ruta(self.cleaned_data["ruta"])
        except entrega.ErrorEntrega as error:
            raise forms.ValidationError(str(error))

    def guardar(self, destino=None):
        datos = self.cleaned_data
        destino = destino or Destino()
        destino.nombre, destino.ruta, destino.activo = datos["nombre"], datos["ruta"], datos["activo"]
        destino.save()
        for tipo, _ in TIPOS:
            ReglaDestino.objects.update_or_create(destino=destino, tipo=tipo, defaults={"entregar": datos[f"entregar_{tipo}"], "nivel": datos[f"nivel_{tipo}"]})
        return destino
