from django import template

from cuentas.permisos import PERMISOS
from configuracion.moneda import formatear

register = template.Library()


@register.filter
def dinero(centavos):
    if centavos is None or centavos == "":
        return ""
    return formatear(int(centavos))


@register.filter
def nombre_permiso(codigo):
    return PERMISOS.get(codigo, codigo)


@register.filter
def obtener(diccionario, clave):
    return diccionario.get(clave, "")
