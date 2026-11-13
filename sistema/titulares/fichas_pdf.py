from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from banco.ficha import datos_de_pago
from configuracion.models import vocabulario

from . import contactos


def _linea(hoja, x, y, texto, tamano=11, negrita=False):
    hoja.setFont("Helvetica-Bold" if negrita else "Helvetica", tamano)
    hoja.drawString(x, y, " ".join(str(texto or "").split())[:95])
    return y - tamano - 6


def generar(titulares, negocio):
    voc = vocabulario()
    pago = datos_de_pago()
    memoria = BytesIO()
    hoja = canvas.Canvas(memoria, pagesize=letter)
    ancho, alto = letter
    for titular in titulares:
        y = alto - 72
        y = _linea(hoja, 72, y, negocio.nombre if negocio else "", 16, True)
        y = _linea(hoja, 72, y, "Ficha de pago", 13)
        y -= 8
        y = _linea(hoja, 72, y, voc["matricula"], 11)
        y = _linea(hoja, 72, y, titular.matricula_formateada, 26, True)
        y -= 6
        y = _linea(hoja, 72, y, f"{voc['titular']}: {titular.nombre_completo}")
        if titular.agrupacion_id:
            y = _linea(hoja, 72, y, f"{voc['agrupacion']}: {titular.agrupacion}")
        contacto = contactos.principal(titular)
        if contacto is not None:
            y = _linea(hoja, 72, y, f"Contacto: {contacto.nombre}")
        y -= 8
        y = _linea(hoja, 72, y, "Cómo pagar", 13, True)
        if pago:
            cuenta = pago["cuenta"]
            for texto in (f"Banco: {cuenta.banco}", f"CLABE: {cuenta.clabe_formateada}", f"Beneficiario: {cuenta.beneficiario}"):
                y = _linea(hoja, 72, y, texto)
            if cuenta.convenio:
                y = _linea(hoja, 72, y, f"Convenio: {cuenta.convenio}")
            if pago["medios"]:
                y = _linea(hoja, 72, y, "Medios aceptados: " + ", ".join(str(m) for m in pago["medios"]))
            y = _linea(hoja, 72, y, f"Escribe {titular.matricula} ({voc['matricula'].lower()}) {pago['lugar']}.", 11, True)
            if cuenta.contacto_dudas:
                y = _linea(hoja, 72, y, f"Dudas: {cuenta.contacto_dudas}")
        else:
            if negocio and negocio.nota_ficha:
                y = _linea(hoja, 72, y, negocio.nota_ficha)
            y = _linea(hoja, 72, y, f"Escribe {titular.matricula} ({voc['matricula'].lower()}) en referencia numérica y en concepto.", 11, True)
        hoja.showPage()
    hoja.save()
    return memoria.getvalue()
