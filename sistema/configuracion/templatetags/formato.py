import re

from django import template

from cuentas.permisos import PERMISOS, etiqueta
from configuracion.moneda import formatear

register = template.Library()


@register.filter
def dinero(centavos):
    if centavos is None or centavos == "":
        return ""
    return formatear(int(centavos))


@register.filter
def nombre_permiso(codigo):
    return etiqueta(codigo) if codigo in PERMISOS else codigo


@register.filter
def voc(texto):
    from configuracion.models import con_vocabulario

    return con_vocabulario(texto)


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

    texto = re.sub(r"^.*(piezas de|:)\s*", "", str(etiqueta), count=1, flags=re.IGNORECASE)
    texto = texto.replace(actual()["codigo"], "").strip()
    return texto[:-3] if texto.endswith(".00") else texto


@register.filter
def dinero_texto(valor):
    from nucleo.dinero import ErrorImporte, a_centavos

    if isinstance(valor, int):
        return formatear(valor)
    try:
        return formatear(a_centavos(str(valor or "0")))
    except (ErrorImporte, ValueError):
        return ""


@register.filter
def dependencia(campo):
    from proyecto.dependencias import atributos

    return atributos(getattr(campo, "depende", None))


@register.filter
def nota_dependencia(campo):
    from proyecto.dependencias import nota

    return nota(getattr(campo, "depende", None))


@register.filter
def piezas_de(formulario):
    return [formulario[nombre] for nombre, campo in formulario.fields.items() if getattr(campo, "pieza", None)]
