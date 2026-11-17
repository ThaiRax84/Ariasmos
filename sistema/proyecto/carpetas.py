import secrets
from pathlib import Path

from django import forms

ATRIBUTO = "data-carpeta"
SIN_PERMISO = "data-sin-permiso"


class EntradaCarpeta(forms.TextInput):
    def __init__(self, attrs=None):
        base = {ATRIBUTO: "", "autocomplete": "off", "spellcheck": "false"}
        base.update(attrs or {})
        super().__init__(base)


def sin_permiso(texto):
    texto = str(texto or "").strip()
    if not texto or "\x00" in texto or len(texto) > 400 or texto.startswith(("\\\\", "//")):
        return False
    ruta = Path(texto)
    if not ruta.is_absolute():
        return False
    existente = ruta
    while not existente.exists():
        if existente.parent == existente:
            return False
        existente = existente.parent
    if not existente.is_dir():
        return False
    prueba = existente / f".prueba-permiso-{secrets.token_hex(6)}"
    try:
        prueba.write_bytes(b"")
    except PermissionError:
        return True
    except OSError:
        return False
    try:
        prueba.unlink()
    except OSError:
        pass
    return False


def con_carpetas(*nombres):
    def decorar(clase):
        for nombre in nombres:
            campo = clase.base_fields[nombre]
            campo.widget = EntradaCarpeta(attrs=dict(campo.widget.attrs))
        original = clase.full_clean

        def full_clean(self):
            original(self)
            for nombre in nombres:
                if nombre in self.fields and nombre in self._errors and sin_permiso(self.data.get(self.add_prefix(nombre))):
                    self.fields[nombre].widget.attrs[SIN_PERMISO] = ""

        clase.full_clean = full_clean
        return clase

    return decorar
