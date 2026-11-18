def plegar(formulario, *nombres):
    for nombre in nombres:
        if nombre in formulario.fields:
            formulario.fields[nombre].avanzado = True


def segun(formulario, control, valores):
    for nombre, (valor, corta) in valores.items():
        if nombre in formulario.fields:
            formulario.fields[nombre].mostrar_si = (formulario.add_prefix(control), valor)
            formulario.fields[nombre].etiqueta_js = corta


class ConPlegables:
    ayuda_avanzados = ""

    @property
    def hay_avanzados(self):
        return any(getattr(campo, "avanzado", False) for campo in self.fields.values())

    @property
    def avanzados_con_error(self):
        return any(getattr(campo, "avanzado", False) and nombre in self.errors for nombre, campo in self.fields.items())
