class ErrorImporte(ValueError):
    pass


def a_centavos(valor):
    if isinstance(valor, bool):
        raise ErrorImporte("importe invalido")
    if isinstance(valor, int):
        return valor
    texto = str(valor).strip().replace("$", "").replace(",", "").replace(" ", "")
    negativo = texto.startswith("-")
    if negativo:
        texto = texto[1:]
    if not texto or not texto.isascii() or texto.count(".") > 1:
        raise ErrorImporte("importe invalido")
    entero, _, fraccion = texto.partition(".")
    entero = entero or "0"
    if not entero.isdigit() or (fraccion and not fraccion.isdigit()) or len(fraccion) > 2:
        raise ErrorImporte("importe invalido")
    centavos = int(entero) * 100 + int(fraccion.ljust(2, "0"))
    return -centavos if negativo else centavos


def formatear(centavos):
    signo = "-" if centavos < 0 else ""
    enteros, resto = divmod(abs(int(centavos)), 100)
    return f"{signo}${enteros:,}.{resto:02d}"


def a_texto(centavos):
    signo = "-" if centavos < 0 else ""
    enteros, resto = divmod(abs(int(centavos)), 100)
    return f"{signo}{enteros}.{resto:02d}"
