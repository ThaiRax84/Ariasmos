import re
from dataclasses import dataclass, field
from datetime import date

MESES = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12}

RENGLON = re.compile(r"^(\s*)(\d{2})-([A-Z]{3})-(\d{4})\s+(\d{1,12})\s+(\S.*)$")
IMPORTE = re.compile(r"(?<![\d,.])\d{1,3}(?:,\d{3})*\.\d{2}(?![\d,])")
INICIO = re.compile(r"SALDO FINAL DEL PERIODO ANTERIOR")
FINAL = re.compile(r"SALDO FINAL DEL PERIODO\s*:")
TOTAL = re.compile(r"^\s*TOTAL\b")
PERIODO = re.compile(r"PERIODO\s+DEL\s+(\d{2})-([A-Z]{3})-(\d{4})\s+AL\s+(\d{2})-([A-Z]{3})-(\d{4})")
CLABE = re.compile(r"CUENTA CLABE:\s*(\d{18})")
HORA = re.compile(r"HORA\s+(\d{2}:\d{2}:\d{2})")
RUIDO = re.compile(r"ESTADO DE CUENTA|CODIGO DE CLIENTE|PERIODO\s+DEL|P[áa]gina\s+\d+\s+de\s+\d+|FECHA\s+FOLIO\s+DESCRIPCION")

SANGRIA_MINIMA = 3
SANGRIA_MAXIMA = 20
MAXIMO_LINEAS = 200000
MAXIMO_DETALLE = 40

SPEI = "spei"
MISMO_BANCO = "mismo_banco"
EFECTIVO = "efectivo"
DEVOLUCION = "devolucion"
OTRO = "otro"

PREFIJOS_MISMO_BANCO = ("ABONO TRANSFERENCIA ENLACE", "ABONO TRANSF RAPIDA SANTANDER")
ETIQUETAS = (
    ("RECIBIDO DE ", "banco_origen"),
    ("DE LA CUENTA ", "cuenta_pagador"),
    ("DEL CLIENTE ", "nombre_pagador"),
    ("CLAVE DE RASTREO ", "rastreo"),
    ("REF ", "referencia"),
    ("CONCEPTO ", "concepto"),
    ("RFC ", "rfc"),
)


class ErrorEstado(ValueError):
    def __init__(self, codigo, mensaje):
        super().__init__(mensaje)
        self.codigo = codigo


@dataclass(frozen=True)
class Movimiento:
    fecha: date
    folio: str
    descripcion: str
    importe: int
    saldo: int
    sentido: str
    clase: str
    hora: str = ""
    banco_origen: str = ""
    cuenta_pagador: str = ""
    nombre_pagador: str = ""
    rastreo: str = ""
    referencia: str = ""
    concepto: str = ""
    rfc: str = ""
    detalle: tuple = ()

    @property
    def es_cobro_posible(self):
        return self.sentido == "abono" and self.clase in (SPEI, MISMO_BANCO, EFECTIVO)


@dataclass
class Estado:
    saldo_inicial: int
    saldo_final: int
    depositos: int
    retiros: int
    movimientos: list = field(default_factory=list)
    clabe: str = ""
    periodo_inicio: date = None
    periodo_fin: date = None


def centavos(texto):
    entero, decimales = texto.replace(",", "").split(".")
    return int(entero) * 100 + int(decimales)


def _fecha(dia, mes, anio):
    if mes not in MESES:
        raise ErrorEstado("fecha", "Mes desconocido en una fecha del estado de cuenta.")
    try:
        return date(int(anio), MESES[mes], int(dia))
    except ValueError:
        raise ErrorEstado("fecha", "Fecha inválida en el estado de cuenta.")


def _clasificar(descripcion, sentido):
    if sentido != "abono":
        return OTRO
    if descripcion.startswith("ABONO TRANSFERENCIA SPEI"):
        return SPEI
    if descripcion.startswith(PREFIJOS_MISMO_BANCO):
        return MISMO_BANCO
    if descripcion.startswith("DEPOSITO EN EFECTIVO"):
        return EFECTIVO
    if "DEVOLUCION" in descripcion:
        return DEVOLUCION
    return OTRO


def _armar(bruto, sentido):
    descripcion = bruto["descripcion"]
    clase = _clasificar(descripcion, sentido)
    campos = {}
    sueltas = []
    for linea in bruto["detalle"]:
        for etiqueta, nombre in ETIQUETAS:
            if linea.startswith(etiqueta) or linea == etiqueta.strip():
                if nombre not in campos:
                    campos[nombre] = linea[len(etiqueta):].strip()
                break
        else:
            sueltas.append(linea)
    hora = HORA.search(descripcion)
    if clase == MISMO_BANCO:
        for prefijo in PREFIJOS_MISMO_BANCO:
            if descripcion.startswith(prefijo):
                texto = " ".join([descripcion[len(prefijo):].strip()] + sueltas).strip()
                campos["concepto"] = texto
                break
    if clase != SPEI:
        for nombre in ("banco_origen", "cuenta_pagador", "nombre_pagador", "referencia", "rfc"):
            campos.pop(nombre, None)
        if clase != MISMO_BANCO:
            campos.pop("concepto", None)
    cuenta = campos.get("cuenta_pagador", "")
    if cuenta and not (cuenta.isascii() and cuenta.isdigit()):
        cuenta = ""
    referencia = campos.get("referencia", "")
    if referencia and not (referencia.isascii() and referencia.isdigit()):
        referencia = ""
    return Movimiento(
        fecha=bruto["fecha"],
        folio=bruto["folio"],
        descripcion=descripcion,
        importe=bruto["importe"],
        saldo=bruto["saldo"],
        sentido=sentido,
        clase=clase,
        hora=hora.group(1) if hora else "",
        banco_origen=campos.get("banco_origen", ""),
        cuenta_pagador=cuenta,
        nombre_pagador=campos.get("nombre_pagador", ""),
        rastreo=campos.get("rastreo", ""),
        referencia=referencia,
        concepto=campos.get("concepto", ""),
        rfc=campos.get("rfc", ""),
        detalle=tuple(bruto["detalle"]),
    )


def leer(lineas):
    lineas = list(lineas)
    if len(lineas) > MAXIMO_LINEAS:
        raise ErrorEstado("tamano", "El estado de cuenta es demasiado grande.")
    clabe = ""
    periodo_inicio = periodo_fin = None
    saldo_inicial = saldo_final = None
    totales = None
    brutos = []
    actual = None
    dentro = False
    for linea in lineas:
        if not dentro:
            if not clabe:
                encontrada = CLABE.search(linea)
                if encontrada:
                    clabe = encontrada.group(1)
            if periodo_inicio is None:
                encontrado = PERIODO.search(linea)
                if encontrado:
                    periodo_inicio = _fecha(*encontrado.group(1, 2, 3))
                    periodo_fin = _fecha(*encontrado.group(4, 5, 6))
            if saldo_inicial is None and INICIO.search(linea):
                importes = IMPORTE.findall(linea)
                if len(importes) != 1:
                    raise ErrorEstado("formato", "No se encontró el saldo inicial.")
                saldo_inicial = centavos(importes[0])
                dentro = True
            continue
        if FINAL.search(linea):
            importes = IMPORTE.findall(linea)
            if len(importes) != 1:
                raise ErrorEstado("formato", "No se encontró el saldo final.")
            saldo_final = centavos(importes[0])
            break
        if TOTAL.match(linea):
            importes = IMPORTE.findall(linea)
            if len(importes) == 2:
                totales = (centavos(importes[0]), centavos(importes[1]))
            actual = None
            continue
        renglon = RENGLON.match(linea)
        if renglon:
            resto = renglon.group(6)
            importes = list(IMPORTE.finditer(resto))
            if len(importes) != 2:
                raise ErrorEstado("formato", "Un movimiento no trae importe y saldo.")
            actual = {
                "fecha": _fecha(*renglon.group(2, 3, 4)),
                "folio": renglon.group(5),
                "descripcion": " ".join(resto[: importes[0].start()].split()),
                "importe": centavos(importes[0].group()),
                "saldo": centavos(importes[1].group()),
                "columna": renglon.start(6),
                "detalle": [],
            }
            brutos.append(actual)
            continue
        if actual is None or not linea.strip() or RUIDO.search(linea):
            continue
        sangria = len(linea) - len(linea.lstrip())
        if actual["columna"] + SANGRIA_MINIMA <= sangria <= actual["columna"] + SANGRIA_MAXIMA and not IMPORTE.search(linea):
            if len(actual["detalle"]) < MAXIMO_DETALLE:
                actual["detalle"].append(" ".join(linea.split()))
    if saldo_inicial is None:
        raise ErrorEstado("formato", "No se encontró la sección de movimientos de la cuenta.")
    if saldo_final is None:
        raise ErrorEstado("formato", "El estado de cuenta está incompleto: falta el saldo final.")
    movimientos = []
    saldo = saldo_inicial
    depositos = retiros = 0
    for bruto in brutos:
        if bruto["importe"] <= 0:
            raise ErrorEstado("formato", "Un movimiento trae importe en cero.")
        if saldo + bruto["importe"] == bruto["saldo"]:
            sentido = "abono"
            depositos += bruto["importe"]
        elif saldo - bruto["importe"] == bruto["saldo"]:
            sentido = "cargo"
            retiros += bruto["importe"]
        else:
            raise ErrorEstado("descuadre", f"El saldo no cuadra en el movimiento con folio {bruto['folio']}.")
        saldo = bruto["saldo"]
        movimientos.append(_armar(bruto, sentido))
    if saldo != saldo_final:
        raise ErrorEstado("descuadre", "El saldo final no coincide con la suma de los movimientos.")
    if totales is not None and totales != (depositos, retiros):
        raise ErrorEstado("descuadre", "Los totales de depósitos y retiros no coinciden con los movimientos.")
    return Estado(saldo_inicial, saldo_final, depositos, retiros, movimientos, clabe, periodo_inicio, periodo_fin)


def huella(clabe_cuenta, movimiento, ordinal):
    partes = [
        clabe_cuenta,
        movimiento.fecha.isoformat(),
        movimiento.folio,
        str(movimiento.importe),
        movimiento.sentido,
        movimiento.rastreo,
        str(ordinal),
    ]
    return "|".join(partes)
