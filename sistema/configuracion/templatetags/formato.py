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


@register.filter
def iniciales(texto):
    palabras = [p for p in str(texto or "").split() if p[:1].isalpha()]
    if not palabras:
        return ""
    if len(palabras) == 1:
        return palabras[0][:1].upper()
    return (palabras[0][:1] + palabras[-1][:1]).upper() if len(palabras) == 2 else (palabras[0][:1] + palabras[-2][:1]).upper()


@register.filter
def centavos(valor):
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0


@register.filter
def dinero_plano(valor):
    try:
        valor = int(valor or 0)
    except (TypeError, ValueError):
        return ""
    return f"{valor // 100}.{valor % 100:02d}" if valor >= 0 else ""


@register.simple_tag(takes_context=True)
def pasos_como(context, clave):
    from proyecto.ayuda import pasos

    return pasos(clave, context.get("voc"))


@register.filter
def piezas_texto(campos):
    partes = []
    for campo in campos:
        valor = campo.value()
        if valor not in (None, "", "0", 0):
            partes.append(f"{valor} × {denominacion_corta(campo.label)}")
    return " · ".join(partes)
