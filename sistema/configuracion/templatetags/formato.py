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


@register.filter
def cifra(centavos):
    from django.utils.html import format_html

    from configuracion.moneda import actual
    from nucleo import dinero as nucleo_dinero

    if centavos is None or centavos == "":
        return ""
    moneda = actual()
    return format_html('{}<span class="moneda">{}</span>', nucleo_dinero.formatear(int(centavos), moneda["simbolo"], ""), moneda["codigo"])


@register.filter
def denominacion_corta(etiqueta):
    from configuracion.moneda import actual

    texto = str(etiqueta)
    for prefijo in ("Recibí: piezas de", "Entrego de cambio: piezas de", "Entrego: piezas de", "Piezas de", "piezas de"):
        texto = texto.replace(prefijo, "")
    texto = texto.replace(actual()["codigo"], "").strip()
    return texto[:-3] if texto.endswith(".00") else texto
