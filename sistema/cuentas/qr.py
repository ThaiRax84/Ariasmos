import segno
from django.utils.safestring import mark_safe

from nucleo import totp


def agrupar(secreto):
    return " ".join(secreto[i:i + 4] for i in range(0, len(secreto), 4))


def svg(uri):
    return segno.make(uri, error="m", micro=False).svg_inline(scale=5, dark="#000", light="#fff", border=4)


def contexto(secreto, cuenta, emisor):
    uri = totp.uri(secreto, cuenta, emisor)
    return {
        "secreto": secreto,
        "secreto_agrupado": agrupar(secreto),
        "cuenta_sugerida": f"{emisor}: {cuenta}",
        "uri": uri,
        "qr": mark_safe(svg(uri)),
    }
