from .dependencias import ConDependencias


def plegar(formulario, *nombres):
    for nombre in nombres:
        if nombre in formulario.fields:
            formulario.fields[nombre].avanzado = True


class ConPlegables(ConDependencias):
    ayuda_avanzados = ""

    @property
    def hay_avanzados(self):
        return any(getattr(campo, "avanzado", False) for campo in self.fields.values())

    @property
    def avanzados_con_error(self):
        return any(getattr(campo, "avanzado", False) and nombre in self.errors for nombre, campo in self.fields.items())
