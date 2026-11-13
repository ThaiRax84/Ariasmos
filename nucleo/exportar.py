PELIGROSOS = ("=", "+", "-", "@", "\t", "\r")


def neutralizar(valor):
    if isinstance(valor, str) and valor.startswith(PELIGROSOS):
        return "'" + valor
    return valor
