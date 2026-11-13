import segno
from django.utils.safestring import mark_safe

PREFIJO = "AR1"


def texto(recibo):
    return f"{PREFIJO}|{recibo.serie}|{recibo.folio}|{recibo.codigo}"


def codigo(recibo):
    return segno.make(texto(recibo), error="m", micro=False)


def svg(recibo):
    return mark_safe(codigo(recibo).svg_inline(scale=4, dark="#000", light="#fff", border=4))


def dibujar(hoja, recibo, x, y, modulo=2.5):
    matriz = list(codigo(recibo).matrix)
    lado = len(matriz) * modulo
    hoja.setFillColorRGB(0, 0, 0)
    for fila, renglon in enumerate(matriz):
        for columna, valor in enumerate(renglon):
            if valor:
                hoja.rect(x + columna * modulo, y + lado - (fila + 1) * modulo, modulo, modulo, fill=1, stroke=0)
    return lado
