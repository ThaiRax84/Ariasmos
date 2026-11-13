LONGITUD = 18
PESOS = (3, 7, 1)


class ErrorClabe(ValueError):
    def __init__(self, codigo, mensaje):
        super().__init__(mensaje)
        self.codigo = codigo


def normalizar(texto):
    return "".join(c for c in str(texto) if c.isascii() and c.isdigit())


def digito_verificador(primeros):
    if len(primeros) != LONGITUD - 1 or not primeros.isascii() or not primeros.isdigit():
        raise ErrorClabe("formato", "se necesitan 17 dígitos")
    suma = sum((int(c) * PESOS[i % 3]) % 10 for i, c in enumerate(primeros))
    return str((10 - suma % 10) % 10)


def analizar(texto):
    clabe = normalizar(texto)
    if len(clabe) != LONGITUD:
        raise ErrorClabe("longitud", "La CLABE tiene 18 dígitos.")
    if digito_verificador(clabe[:-1]) != clabe[-1]:
        raise ErrorClabe("digito", "La CLABE no es válida: revisa los dígitos.")
    return {"clabe": clabe, "banco": clabe[:3], "plaza": clabe[3:6], "cuenta": clabe[6:17], "digito": clabe[17]}


def es_valida(texto):
    try:
        analizar(texto)
    except ErrorClabe:
        return False
    return True


def formatear(clabe):
    clabe = normalizar(clabe)
    return " ".join([clabe[:3], clabe[3:6], clabe[6:17], clabe[17:]]).strip()
