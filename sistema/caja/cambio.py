LIMITE_ESTADOS = 200000


class DemasiadoComplejo(Exception):
    pass


def _ordenar(existencias):
    ordenadas = []
    for valor, cantidad in existencias.items():
        valor, cantidad = int(valor), int(cantidad)
        if valor <= 0:
            raise ValueError("denominación no válida")
        if cantidad > 0:
            ordenadas.append((valor, cantidad))
    return sorted(ordenadas, reverse=True)


def proponer(cambio, existencias, limite=LIMITE_ESTADOS):
    if type(cambio) is not int or cambio < 0:
        raise ValueError("el cambio debe ser un entero no negativo")
    if cambio == 0:
        return {}
    piezas = _ordenar(existencias)
    total = len(piezas)
    capacidad = [0] * (total + 1)
    for indice in range(total - 1, -1, -1):
        valor, cantidad = piezas[indice]
        capacidad[indice] = capacidad[indice + 1] + valor * cantidad
    memoria = {}

    def mejor(indice, resto):
        if resto == 0:
            return (0, ())
        if indice == total or resto > capacidad[indice]:
            return None
        clave = (indice, resto)
        if clave in memoria:
            return memoria[clave]
        if len(memoria) >= limite:
            raise DemasiadoComplejo("el cambio requiere demasiadas combinaciones")
        valor, cantidad = piezas[indice]
        maximo = min(cantidad, resto // valor)
        minimo = max(0, -(-(resto - capacidad[indice + 1]) // valor))
        elegido = None
        for usadas in range(maximo, minimo - 1, -1):
            siguiente = mejor(indice + 1, resto - usadas * valor)
            if siguiente is None:
                continue
            cuenta = usadas + siguiente[0]
            if elegido is None or cuenta < elegido[0]:
                elegido = (cuenta, ((valor, usadas),) + siguiente[1])
        memoria[clave] = elegido
        return elegido

    resultado = mejor(0, cambio)
    if resultado is None:
        return None
    return {valor: usadas for valor, usadas in resultado[1] if usadas}

