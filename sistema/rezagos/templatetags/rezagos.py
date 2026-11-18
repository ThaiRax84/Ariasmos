from django import template
from django.template.loader import render_to_string
from django.utils.html import format_html, format_html_join

from rezagos import calculo, presentacion, servicios
from rezagos.models import ExcepcionLimite, ReglaRezago

register = template.Library()
CLAVE = "rezagos_situaciones"


def _usuario(context):
    usuario = context.get("user")
    return usuario if usuario is not None and usuario.is_authenticated else None


@register.simple_tag(takes_context=True)
def avisos_rezago(context):
    usuario = _usuario(context)
    if usuario is None:
        return ""
    contexto = {"aviso": presentacion.aviso_para(usuario), "permisos": context.get("permisos", set()), "voc": context.get("voc")}
    if usuario.tiene_permiso("ver_auditoria"):
        contexto["cambios"] = presentacion.cambios_legibles(servicios.cambios_ajenos(usuario))
    return render_to_string("rezagos/_inicio.html", contexto)


def _situaciones(context, lista):
    cache = context.render_context
    if CLAVE not in cache:
        ids = [getattr(t, "pk", None) for t in lista or []]
        cache[CLAVE] = calculo.evaluar(ids=[i for i in ids if i is not None]) if ids else {}
    return cache[CLAVE]


@register.simple_tag(takes_context=True)
def marca_rezago(context, titular, lista=None):
    usuario = _usuario(context)
    if usuario is None or titular is None:
        return ""
    situacion = _situaciones(context, lista if lista is not None else [titular]).get(titular.pk)
    if situacion is None:
        return ""
    marcas = situacion.marcas(presentacion.ve_dirigidas(usuario))
    if not marcas:
        return ""
    return format_html(" {}", format_html_join(" ", '<span class="estado aviso" data-marca-rezago>{}</span>', ((m,) for m in marcas)))


@register.simple_tag(takes_context=True)
def ficha_rezago(context, titular):
    usuario = _usuario(context)
    if usuario is None or titular is None:
        return ""
    situacion = calculo.de(titular)
    permisos = context.get("permisos", set())
    contexto = {
        "titular": titular,
        "situacion": situacion,
        "permisos": permisos,
        "voc": context.get("voc"),
        "dirigidas": list(ReglaRezago.objects.filter(titular=titular)) if presentacion.ve_dirigidas(usuario) else [],
    }
    if situacion is not None:
        contexto["marcas"] = situacion.marcas(presentacion.ve_dirigidas(usuario))
        contexto["texto"] = situacion.texto_aviso(presentacion.ve_dirigidas(usuario))
        contexto["limite_importe"] = presentacion.efectivo_texto(situacion.limite_importe, True)
        contexto["limite_dias"] = presentacion.efectivo_texto(situacion.limite_dias, False)
    excepcion = ExcepcionLimite.objects.filter(titular=titular).first() if presentacion.ve_saldos(usuario) else None
    if excepcion is not None:
        contexto["excepcion"] = excepcion
        contexto["excepcion_importe"] = presentacion.texto_limite(excepcion.modo_importe, excepcion.importe_maximo, True)
        contexto["excepcion_dias"] = presentacion.texto_limite(excepcion.modo_dias, excepcion.dias_maximos, False)
    if situacion is None and not contexto.get("excepcion") and not contexto["dirigidas"] and "configurar_limites_adeudo" not in permisos:
        return ""
    return render_to_string("rezagos/_ficha.html", contexto)


@register.simple_tag(takes_context=True)
def cobro_rezago(context, titular):
    usuario = _usuario(context)
    if usuario is None or titular is None:
        return ""
    situacion = calculo.de(titular)
    if situacion is None:
        return ""
    dirigidas = presentacion.ve_dirigidas(usuario)
    contexto = {"situacion": situacion, "marcas": situacion.marcas(dirigidas), "texto": situacion.texto_aviso(dirigidas), "voc": context.get("voc")}
    return render_to_string("rezagos/_cobro.html", contexto)
