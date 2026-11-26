from io import BytesIO

from reportlab.pdfgen import canvas

from configuracion import hoja as tamano_hoja
from configuracion.models import vocabulario
from configuracion.moneda import formatear

from . import libro, qr


def resumen(recibo):
    pago = recibo.pago
    aplicaciones = list(
        pago.aplicaciones.select_related("cargo__titular", "cargo__concepto")
    )
    return {
        "recibo": recibo,
        "pago": pago,
        "titular": pago.titular,
        "aplicaciones": aplicaciones,
        "a_favor": pago.importe - sum(a.importe for a in aplicaciones),
        "cancelado": hasattr(pago, "reversion"),
    }


MARGEN_INFERIOR_RECIBO = 40
ALTO_CIERRE_RECIBO = 190
ALTO_CANCELADO_RECIBO = 24


def _colores_recibo():
    from configuracion import marca as marca_negocio

    actual = marca_negocio.actual()
    if actual is not None and actual.con_colores:
        valores = marca_negocio.variables(actual.color_principal, actual.color_acento)
        return (
            actual,
            valores["--tinta"],
            valores["--suave"],
            valores["--acento"],
            valores["--tinte"],
            valores["--borde"],
        )
    return actual, "#1F1813", "#5C5047", "#C4662E", "#F6E3D6", "#E2D6C6"


def _logo_recibo(actual):
    from reportlab.lib.utils import ImageReader

    from caja import comprobantes
    from configuracion import marca as marca_negocio

    try:
        contenido = marca_negocio.leer_logo(actual)
    except (OSError, comprobantes.ComprobanteInvalido, marca_negocio.MarcaInvalida):
        return None
    return ImageReader(BytesIO(contenido)) if contenido else None


def generar(objeto, negocio):
    from reportlab.lib.colors import HexColor

    datos = resumen(objeto)
    voc = vocabulario()
    marca_actual, *colores = _colores_recibo()
    tinta, suave, acento, tinte, borde = (HexColor(c) for c in colores)
    memoria = BytesIO()
    tamano = tamano_hoja.tamano()
    hoja = canvas.Canvas(memoria, pagesize=tamano)
    ancho, alto = tamano
    izquierda, derecha = 90, ancho - 90
    y = alto - 80
    logo = _logo_recibo(marca_actual)
    texto_x = izquierda
    if logo is not None:
        hoja.drawImage(
            logo,
            izquierda,
            y - 38,
            width=48,
            height=48,
            preserveAspectRatio=True,
            mask="auto",
        )
        texto_x = izquierda + 60
    hoja.setFillColor(tinta)
    hoja.setFont("Helvetica-Bold", 15)
    hoja.drawString(texto_x, y - 6, (negocio.nombre if negocio else "")[:48])
    hoja.setFont("Helvetica", 9)
    hoja.setFillColor(suave)
    hoja.drawString(texto_x, y - 22, "Recibo de pago")
    hoja.drawRightString(derecha, y + 2, "Recibo")
    hoja.setFillColor(tinta)
    hoja.setFont("Helvetica-Bold", 15)
    hoja.drawRightString(derecha, y - 16, f"{objeto}")
    y -= 52
    hoja.setStrokeColor(acento)
    hoja.setLineWidth(2)
    hoja.line(izquierda, y, derecha, y)
    y -= 26

    def reservar(espacio):
        nonlocal y
        if y - espacio < MARGEN_INFERIOR_RECIBO:
            hoja.showPage()
            y = alto - 80

    def renglon(etiqueta, valor, negritas=True):
        nonlocal y
        reservar(26)
        hoja.setFont("Helvetica", 10)
        hoja.setFillColor(suave)
        hoja.drawString(izquierda, y, etiqueta[:70])
        hoja.setFont("Helvetica-Bold" if negritas else "Helvetica", 10)
        hoja.setFillColor(tinta)
        hoja.drawRightString(derecha, y, valor[:60])
        hoja.setStrokeColor(borde)
        hoja.setLineWidth(0.6)
        hoja.line(izquierda, y - 8, derecha, y - 8)
        y -= 26

    renglon("Fecha", libro.fecha_local(datos["pago"].fecha).strftime("%d/%m/%Y"))
    renglon(voc["titular"], datos["titular"].nombre_completo)
    if not datos["titular"].interno:
        renglon(voc["matricula"], datos["titular"].matricula_formateada)
    renglon("Forma de pago", datos["pago"].get_medio_display().capitalize())
    y -= 6
    reservar(46)
    hoja.setFont("Helvetica-Bold", 9)
    hoja.setFillColor(suave)
    hoja.drawString(izquierda, y, "Aplicado a")
    y -= 20
    for aplicacion in datos["aplicaciones"]:
        etiqueta = f"{aplicacion.cargo}"
        if aplicacion.cargo.titular_id != datos["titular"].pk:
            etiqueta += f" ({aplicacion.cargo.titular.nombre_completo})"
        renglon(etiqueta, formatear(aplicacion.importe, pdf=True), negritas=False)
    if datos["a_favor"]:
        renglon("Queda a favor", formatear(datos["a_favor"], pdf=True), negritas=False)
    y -= 8
    reservar(ALTO_CIERRE_RECIBO + (ALTO_CANCELADO_RECIBO if datos["cancelado"] else 0))
    hoja.setFillColor(tinte)
    hoja.roundRect(izquierda, y - 26, derecha - izquierda, 44, 10, fill=1, stroke=0)
    hoja.setFillColor(tinta)
    hoja.setFont("Helvetica-Bold", 11)
    hoja.drawString(izquierda + 14, y - 8, "Importe recibido")
    hoja.setFont("Helvetica-Bold", 17)
    hoja.drawRightString(
        derecha - 14, y - 10, formatear(datos["pago"].importe, pdf=True)
    )
    y -= 60
    if datos["cancelado"]:
        hoja.setFillColor(HexColor("#A1281C"))
        hoja.setFont("Helvetica-Bold", 18)
        hoja.drawString(izquierda, y, "CANCELADO")
        y -= 24
    lado = qr.dibujar(hoja, objeto, izquierda, y - 78, modulo=2)
    hoja.setFillColor(suave)
    hoja.setFont("Helvetica", 9)
    hoja.drawString(izquierda + lado + 18, y - 14, "Código de verificación")
    hoja.setFillColor(tinta)
    hoja.setFont("Helvetica-Bold", 15)
    hoja.drawString(izquierda + lado + 18, y - 34, objeto.codigo)
    hoja.setFont("Helvetica", 9)
    hoja.setFillColor(suave)
    hoja.drawString(
        izquierda + lado + 18,
        y - 52,
        f"Recibió: {datos['pago'].registrado_por or 'importación automática del banco'}"[
            :70
        ],
    )
    y -= max(lado, 60) + 24
    hoja.setStrokeColor(borde)
    hoja.setDash(2, 2)
    hoja.line(izquierda, y, derecha, y)
    hoja.setDash()
    y -= 14
    hoja.setFont("Helvetica", 8)
    hoja.drawString(
        izquierda,
        y,
        "Escanea el QR en «Verificar recibo» o usa su código para comprobarlo.",
    )
    hoja.setFillColor(tinta)
    hoja.setFont("Times-Roman", 10)
    hoja.drawRightString(derecha, y, "A R I A S M O S")
    hoja.setFillColor(suave)
    hoja.setFont("Helvetica", 8)
    hoja.drawRightString(
        derecha - hoja.stringWidth("A R I A S M O S", "Times-Roman", 10) - 4,
        y,
        "Hecho con",
    )
    hoja.showPage()
    hoja.save()
    return memoria.getvalue()
