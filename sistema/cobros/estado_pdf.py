from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.flowables import Preformatted

from banco.ficha import datos_de_pago
from configuracion import moneda
from configuracion.models import hoy_negocio, vocabulario

from .estado import estado_cuenta
from .libro import fecha_local

ESTILO_TABLA = TableStyle(
    [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ebef")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c0c6cc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
    ]
)


def formatear(centavos):
    return moneda.formatear(centavos, pdf=True)


def _corto(texto, maximo):
    texto = " ".join(str(texto or "").split())
    return texto if len(texto) <= maximo else texto[: maximo - 1] + "…"


def _parrafo(texto, estilo):
    return Preformatted(_corto(texto, 150), estilo)


def generar(titulares, titulo, negocio):
    voc = vocabulario()
    estado = estado_cuenta(titulares)
    estilos = getSampleStyleSheet()
    normal = estilos["Code"].clone("texto", fontName="Helvetica", fontSize=8, leading=10)
    grande = estilos["Code"].clone("titulo", fontName="Helvetica-Bold", fontSize=13, leading=16)
    varios = len(titulares) > 1
    piezas = [
        _parrafo(negocio.nombre if negocio else "", grande),
        _parrafo(f"Estado de cuenta al {hoy_negocio():%d/%m/%Y}", normal),
        _parrafo(titulo, normal),
        _parrafo(" · ".join(f"{voc['matricula']} {t.matricula_formateada}: {t.nombre_completo}" for t in titulares), normal),
        Spacer(1, 4 * mm),
        _parrafo(f"Adeudo: {formatear(estado['adeudo'])}    A favor: {formatear(estado['a_favor'])}", grande),
        Spacer(1, 3 * mm),
    ]
    encabezado = ([voc["titular"]] if varios else []) + ["Cargo", "Vence", "Original", "Beca", "Importe", "Cancelado", "Pagado", "Saldo"]
    filas = [encabezado]
    for fila in estado["cargos"]:
        cargo = fila["cargo"]
        nombre = _corto(cargo, 45) + (" (recargo)" if cargo.origen == "recargo" else "") + (f" · prórroga {cargo.prorroga:%d/%m/%Y}" if cargo.prorroga else "")
        beca = f"{cargo.beca.porcentaje_texto} (−{formatear(cargo.descuento)})" if cargo.beca_id else ""
        filas.append(
            ([_corto(cargo.titular.nombre_completo, 25)] if varios else [])
            + [nombre, f"{cargo.vencimiento:%d/%m/%Y}", formatear(cargo.importe_original), beca, formatear(cargo.importe_final), formatear(cargo.cancelado) if cargo.cancelado else "", formatear(cargo.aplicado) if cargo.aplicado else "", formatear(cargo.saldo)]
        )
    if len(filas) == 1:
        filas.append([""] * (len(encabezado) - 1) + ["Sin cargos"])
    tabla = Table(filas, repeatRows=1)
    tabla.setStyle(ESTILO_TABLA)
    piezas += [_parrafo("Cargos", grande), tabla, Spacer(1, 4 * mm)]
    filas = [["Recibo", "Fecha", "Pagó con", "Importe", "Aplicado a", "Estado"]]
    for pago in estado["pagos"]:
        aplicado = "; ".join(f"{_corto(a.cargo, 30)}: {formatear(a.importe)}" for a in pago.aplicaciones.all())
        situacion = f"Revertido: {_corto(pago.reversion.motivo, 40)}" if pago.revertido else (f"A favor {formatear(pago.disponible)}" if pago.disponible else "Aplicado")
        filas.append([str(pago.recibo) if hasattr(pago, "recibo") else "", f"{fecha_local(pago.fecha):%d/%m/%Y}", _corto(pago.titular.nombre_completo, 25), formatear(pago.importe), _corto(aplicado, 90), situacion])
    if len(filas) == 1:
        filas.append(["", "", "", "", "Sin pagos", ""])
    tabla = Table(filas, repeatRows=1, colWidths=[22 * mm, 20 * mm, 45 * mm, 24 * mm, 100 * mm, 40 * mm])
    tabla.setStyle(ESTILO_TABLA)
    piezas += [_parrafo("Pagos", grande), tabla, Spacer(1, 4 * mm)]
    cancelaciones = [(c, x) for c in (f["cargo"] for f in estado["cargos"]) for x in c.cancelaciones.all()]
    if cancelaciones:
        filas = [["Fecha", "Cargo", "Tipo", "Importe", "Motivo"]]
        for cargo, asiento in cancelaciones:
            filas.append([f"{fecha_local(asiento.creada):%d/%m/%Y}", _corto(cargo, 45), asiento.get_tipo_display(), formatear(asiento.importe), _corto(asiento.motivo, 70)])
        tabla = Table(filas, repeatRows=1)
        tabla.setStyle(ESTILO_TABLA)
        piezas += [_parrafo("Cancelaciones y condonaciones", grande), tabla, Spacer(1, 4 * mm)]
    pago = datos_de_pago()
    piezas.append(_parrafo("Cómo pagar", grande))
    if pago:
        cuenta = pago["cuenta"]
        lineas = [f"Banco: {cuenta.banco}", f"CLABE: {cuenta.clabe_formateada}", f"Beneficiario: {cuenta.beneficiario}"]
        if cuenta.numero_cuenta:
            lineas.append(f"Número de cuenta: {cuenta.numero_cuenta}")
        if cuenta.convenio:
            lineas.append(f"Convenio: {cuenta.convenio}")
        if pago["medios"]:
            lineas.append("Medios aceptados: " + ", ".join(str(m) for m in pago["medios"]))
        for titular in titulares:
            lineas.append(f"Para {titular.nombre_completo}: escribe {titular.matricula} ({voc['matricula'].lower()}) {pago['lugar']}.")
        if cuenta.contacto_dudas:
            lineas.append(f"Dudas: {cuenta.contacto_dudas}")
        if cuenta.nota_adicional:
            lineas.append(cuenta.nota_adicional)
    else:
        lineas = [negocio.nota_ficha] if negocio and negocio.nota_ficha else []
        lineas += [f"Para {t.nombre_completo}: escribe {t.matricula} ({voc['matricula'].lower()}) en referencia numérica y en concepto." for t in titulares]
    piezas += [_parrafo(linea, normal) for linea in lineas]
    memoria = BytesIO()
    documento = SimpleDocTemplate(memoria, pagesize=landscape(letter), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title="Estado de cuenta")
    documento.build(piezas)
    return memoria.getvalue()
