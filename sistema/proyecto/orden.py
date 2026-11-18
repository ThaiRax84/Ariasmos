from dataclasses import dataclass, field

from configuracion.models import vocabulario

SENTIDOS = (("asc", "Ascendente (A→Z, 0→9)"), ("desc", "Descendente (Z→A, 9→0)"))


def _titulares(voc):
    return {
        "nombre": ("Nombre", ("nombre", "apellidos", "id")),
        "apellidos": ("Apellidos", ("apellidos", "nombre", "id")),
        "matricula": (voc["matricula"], ("matricula", "id")),
        "agrupacion": (voc["agrupacion"], ("agrupacion__nombre", "apellidos", "nombre", "id")),
        "familia": (voc["familia"], ("familia__nombre", "apellidos", "nombre", "id")),
    }


def _articulos(voc):
    return {
        "nombre": ("Nombre", ("nombre", "clave")),
        "clave": ("Clave", ("clave",)),
        "precio": ("Precio", ("precio", "nombre")),
        "activos": ("Activos primero", ("-activo", "nombre")),
    }


def _usuarios(voc):
    return {
        "nombre": ("Nombre", ("nombre", "id")),
        "usuario": ("Usuario", ("usuario",)),
        "rol": ("Rol", ("rol__nivel", "rol__nombre", "nombre")),
        "alta": ("Fecha de alta", ("creado", "id")),
    }


def _solicitudes(voc):
    return {
        "fecha": ("Fecha", ("creada", "id")),
        "accion": ("Tipo de solicitud", ("accion", "creada", "id")),
        "estado": ("Estado", ("estado", "creada", "id")),
    }


def _cortes(voc):
    return {
        "fecha": ("Fecha", ("fecha", "numero", "id")),
        "tipo": ("Tipo de corte", ("tipo", "fecha", "id")),
        "caja": ("Caja", ("caja__nombre", "fecha", "id")),
        "estado": ("Estado", ("estado", "fecha", "id")),
    }


LISTAS = {
    "padron": (_titulares, "apellidos", False),
    "cobrar": (_titulares, "apellidos", False),
    "vender": (_titulares, "apellidos", False),
    "conciliar": (_titulares, "apellidos", False),
    "articulos": (_articulos, "activos", False),
    "usuarios": (_usuarios, "nombre", False),
    "solicitudes_pendientes": (_solicitudes, "fecha", False),
    "solicitudes_propias": (_solicitudes, "fecha", True),
    "cortes": (_cortes, "fecha", True),
}


def _invertir(campo):
    return campo[1:] if campo.startswith("-") else f"-{campo}"


@dataclass
class Orden:
    lista: str
    clave: str
    descendente: bool
    opciones: list = field(default_factory=list)
    base: tuple = ()
    parametro: str = "orden"
    parametro_sentido: str = "sentido"

    @property
    def campos(self):
        return tuple(_invertir(c) if self.descendente else c for c in self.base)

    @property
    def sentido(self):
        return "desc" if self.descendente else "asc"

    @property
    def sentidos(self):
        return SENTIDOS

    @property
    def etiqueta(self):
        return dict(self.opciones).get(self.clave, "")


def preparar(lista, clave=None, descendente=None, prefijo=""):
    construir, defecto, desc_defecto = LISTAS[lista]
    opciones = construir(vocabulario())
    clave = clave if clave in opciones else defecto
    descendente = desc_defecto if descendente is None else bool(descendente)
    parametro = f"{prefijo}orden" if prefijo else "orden"
    sentido = f"{prefijo}sentido" if prefijo else "sentido"
    return Orden(lista, clave, descendente, [(k, v[0]) for k, v in opciones.items()], opciones[clave][1], parametro, sentido)


def elegir(request, lista, prefijo=""):
    from cuentas.models import PreferenciaOrden

    construir, defecto, desc_defecto = LISTAS[lista]
    opciones = construir(vocabulario())
    usuario = request.user if getattr(request.user, "is_authenticated", False) else None
    guardada = PreferenciaOrden.objects.filter(usuario=usuario, lista=lista).first() if usuario else None
    clave, descendente = defecto, desc_defecto
    if guardada is not None and guardada.clave in opciones:
        clave, descendente = guardada.clave, guardada.descendente
    pedida = request.GET.get(f"{prefijo}orden")
    sentido = request.GET.get(f"{prefijo}sentido")
    if pedida in opciones or sentido in ("asc", "desc"):
        if pedida in opciones:
            clave = pedida
        if sentido in ("asc", "desc"):
            descendente = sentido == "desc"
        if usuario is not None and (guardada is None or (guardada.clave, guardada.descendente) != (clave, descendente)):
            PreferenciaOrden.objects.update_or_create(usuario=usuario, lista=lista, defaults={"clave": clave, "descendente": descendente})
    return preparar(lista, clave, descendente, prefijo)
