SIMBOLOS = ("RD$", "US$", "S/", "$", "€", "₡", "Q")
CODIGOS = ("MXN", "USD", "EUR", "COP", "PEN", "CLP", "ARS", "GTQ", "CRC", "DOP")


class ErrorImporte(ValueError):
    pass


def a_centavos(valor):
    if isinstance(valor, bool):
        raise ErrorImporte("importe invalido")
    if isinstance(valor, int):
        return valor
    texto = str(valor).strip().replace("\u00a0", " ")
    negativo = texto.startswith("-")
    if negativo:
        texto = texto[1:].lstrip()
    for simbolo in SIMBOLOS:
        if texto.startswith(simbolo):
            texto = texto[len(simbolo):].lstrip()
            break
    for codigo in CODIGOS:
        if texto.upper().endswith(codigo):
            texto = texto[: -len(codigo)].rstrip()
            break
    if texto.startswith("-") and not negativo:
        negativo = True
        texto = texto[1:]
    texto = texto.replace(",", "").replace(" ", "")
    if not texto or not texto.isascii() or texto.count(".") > 1:
        raise ErrorImporte("importe invalido")
    entero, _, fraccion = texto.partition(".")
    entero = entero or "0"
    if not entero.isdigit() or (fraccion and not fraccion.isdigit()) or len(fraccion) > 2:
        raise ErrorImporte("importe invalido")
    centavos = int(entero) * 100 + int(fraccion.ljust(2, "0"))
    return -centavos if negativo else centavos


def formatear(centavos, simbolo="$", codigo=""):
    signo = "-" if centavos < 0 else ""
    enteros, resto = divmod(abs(int(centavos)), 100)
    texto = f"{signo}{simbolo}{enteros:,}.{resto:02d}"
    return f"{texto} {codigo}" if codigo else texto


def a_texto(centavos):
    signo = "-" if centavos < 0 else ""
    enteros, resto = divmod(abs(int(centavos)), 100)
    return f"{signo}{enteros}.{resto:02d}"
