import calendar
from io import BytesIO

from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

from banco.models import Banco, CuentaBancaria

from .test_lector_santander import COLUMNAS, ENCABEZADO, dinero, sub

CLABE = "002010077777777771"


def cuenta_principal():
    return CuentaBancaria.objects.filter(clabe=CLABE).first() or CuentaBancaria.objects.create(
        banco=Banco.objects.get(clave="002"), clabe=CLABE, beneficiario="Negocio de prueba", contacto_dudas="5512345678", principal=True
    )


MESES = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]


def renglon(dia, folio, descripcion, importe, saldo, mes=8, anio=2026):
    return f"{dia:02d}-{MESES[mes - 1]}-{anio} {folio} {descripcion}".ljust(96) + dinero(importe).rjust(12) + " " * 14 + dinero(saldo).rjust(12)


def spei(dia, importe, referencia="", concepto="", cuenta="032180000118359719", nombre="PERSONA FICTICIA", rastreo=None):
    detalle = [sub("RECIBIDO DE BANCO FICTICIO"), sub(f"DE LA CUENTA {cuenta}"), sub(f"DEL CLIENTE {nombre}"), sub(f"CLAVE DE RASTREO {rastreo or f'R{dia:02d}{importe}'}")]
    if referencia:
        detalle.append(sub(f"REF {referencia}"))
    detalle.append(sub(f"CONCEPTO {concepto}".rstrip()))
    detalle.append(sub("RFC XAXX010101000"))
    return (dia, "ABONO TRANSFERENCIA SPEI HORA 10:00:00", importe, +1, detalle)


def enlace(dia, importe, texto):
    return (dia, f"ABONO TRANSFERENCIA ENLACE {texto}", importe, +1, [])


def efectivo(dia, importe):
    return (dia, "DEPOSITO EN EFECTIVO", importe, +1, [])


def retiro(dia, importe):
    return (dia, "PAGO TRANSFERENCIA SPEI HORA 12:00:00", importe, -1, [sub("ENVIADO A BANCO FICTICIO"), sub("CONCEPTO renta")])


def periodo(mes, anio=2026):
    ultimo = calendar.monthrange(anio, mes)[1]
    return f"PERIODO DEL 01-{MESES[mes - 1]}-{anio} AL {ultimo:02d}-{MESES[mes - 1]}-{anio}"


def estado(movimientos, clabe=CLABE, saldo_inicial=100000, alterar=None, mes=8, anio=2026):
    encabezado = [linea.replace("PERIODO DEL 01-AGO-2026 AL 31-AGO-2026", periodo(mes, anio)) for linea in ENCABEZADO]
    lineas = encabezado + [
        f"           CUENTA EJEMPLO PYME                            00-00000000-0         CUENTA CLABE: {clabe}",
        "",
        "        Detalle de movimientos cuenta de cheques.",
        f" SALDO FINAL DEL PERIODO ANTERIOR:                                 ${dinero(saldo_inicial)}",
        COLUMNAS,
    ]
    saldo = saldo_inicial
    depositos = retiros = 0
    for n, (dia, descripcion, importe, signo, detalle) in enumerate(movimientos):
        saldo += signo * importe
        if signo > 0:
            depositos += importe
        else:
            retiros += importe
        lineas.append(renglon(dia, f"{2000000 + n}", descripcion, importe if alterar != n else importe + 100, saldo, mes, anio))
        lineas += detalle
    lineas.append(" " * 30 + "TOTAL".ljust(70) + dinero(depositos).rjust(14) + dinero(retiros).rjust(18))
    lineas.append(" " * 100 + "SALDO FINAL DEL PERIODO:".ljust(40) + "$" + dinero(saldo))
    return lineas


def pdf(lineas, cifrado=False):
    memoria = BytesIO()
    hoja = canvas.Canvas(memoria, pagesize=landscape(letter), encrypt="clave" if cifrado else None)
    y = 590
    hoja.setFont("Courier", 6.5)
    for linea in lineas:
        if y < 30:
            hoja.showPage()
            hoja.setFont("Courier", 6.5)
            y = 590
        hoja.drawString(15, y, linea)
        y -= 8
    hoja.save()
    return memoria.getvalue()


def saldo_final(movimientos, saldo_inicial=100000):
    return saldo_inicial + sum(signo * importe for _, _, importe, signo, _ in movimientos)
