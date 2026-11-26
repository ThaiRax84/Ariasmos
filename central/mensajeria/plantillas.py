import re

PATRON_VARIABLE = re.compile(r"\[([a-z_]{1,30})\]")


def variables_de(texto):
    return list(dict.fromkeys(PATRON_VARIABLE.findall(texto)))


def con_numeros(texto, variables):
    numeros = {nombre: f"{{{{{i}}}}}" for i, nombre in enumerate(variables, 1)}
    return PATRON_VARIABLE.sub(lambda hallada: numeros[hallada.group(1)], texto)
