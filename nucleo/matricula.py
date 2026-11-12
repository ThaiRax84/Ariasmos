import hmac
import hashlib

VERSION = 1
RONDAS = 8
LONGITUD_MIN = 5
LONGITUD_MAX = 12
ETIQUETA = b"matricula-v1|"

DAMM = (
    (0, 3, 1, 7, 5, 9, 8, 6, 4, 2),
    (7, 0, 9, 2, 1, 5, 4, 8, 6, 3),
    (4, 2, 0, 6, 8, 7, 1, 3, 5, 9),
    (1, 7, 5, 0, 9, 8, 3, 4, 2, 6),
    (6, 1, 2, 3, 0, 4, 5, 9, 7, 8),
    (3, 6, 7, 4, 2, 0, 9, 5, 8, 1),
    (5, 8, 6, 9, 7, 2, 0, 1, 3, 4),
    (8, 9, 4, 5, 3, 6, 2, 0, 1, 7),
    (9, 4, 3, 8, 6, 1, 7, 2, 0, 5),
    (2, 5, 8, 1, 4, 3, 6, 7, 9, 0),
)


class ErrorMatricula(ValueError):
    pass


class EspacioAgotado(ErrorMatricula):
    pass


def digito_verificador(digitos):
    estado = 0
    for c in digitos:
        estado = DAMM[estado][ord(c) - 48]
    return str(estado)


def es_valida(matricula, longitud=7):
    if not isinstance(matricula, str) or len(matricula) != longitud:
        return False
    if not matricula.isascii() or not matricula.isdigit():
        return False
    if matricula[0] == "0":
        return False
    estado = 0
    for c in matricula:
        estado = DAMM[estado][ord(c) - 48]
    return estado == 0


def capacidad(longitud=7):
    _validar_longitud(longitud)
    return 9 * 10 ** (longitud - 2)


def capacidad_por_sede(longitud=7, ranuras=10):
    return capacidad(longitud) // ranuras


def _validar_longitud(longitud):
    if not LONGITUD_MIN <= longitud <= LONGITUD_MAX:
        raise ErrorMatricula("longitud fuera de rango")


def _ronda(clave, i, valor, modulo):
    mensaje = ETIQUETA + bytes([i]) + valor.to_bytes(8, "big") + modulo.to_bytes(8, "big")
    resumen = hmac.new(clave, mensaje, hashlib.sha256).digest()
    return int.from_bytes(resumen[:16], "big") % modulo


def _feistel(clave, x, mitad):
    izq, der = divmod(x, mitad)
    for i in range(RONDAS):
        izq, der = der, (izq + _ronda(clave, i, der, mitad)) % mitad
    return izq * mitad + der


def _feistel_inverso(clave, y, mitad):
    izq, der = divmod(y, mitad)
    for i in reversed(range(RONDAS)):
        izq, der = (der - _ronda(clave, i, izq, mitad)) % mitad, izq
    return izq * mitad + der


def permutar(clave, indice, longitud=7):
    _validar_longitud(longitud)
    d = longitud - 1
    total = 9 * 10 ** (d - 1)
    if not 0 <= indice < total:
        raise EspacioAgotado("indice fuera del espacio")
    mitad = 10 ** ((d + 1) // 2)
    y = _feistel(clave, indice, mitad)
    while y >= total:
        y = _feistel(clave, y, mitad)
    return y


def despermutar(clave, valor, longitud=7):
    _validar_longitud(longitud)
    d = longitud - 1
    total = 9 * 10 ** (d - 1)
    if not 0 <= valor < total:
        raise ErrorMatricula("valor fuera del espacio")
    mitad = 10 ** ((d + 1) // 2)
    x = _feistel_inverso(clave, valor, mitad)
    while x >= total:
        x = _feistel_inverso(clave, x, mitad)
    return x


def construir(clave, indice, longitud=7):
    d = longitud - 1
    cuerpo = str(10 ** (d - 1) + permutar(clave, indice, longitud))
    return cuerpo + digito_verificador(cuerpo)


def indice_de(clave, matricula, longitud=7):
    if not es_valida(matricula, longitud):
        raise ErrorMatricula("matricula invalida")
    d = longitud - 1
    return despermutar(clave, int(matricula[:-1]) - 10 ** (d - 1), longitud)


def es_trivial(matricula):
    if len(set(matricula)) < 3:
        return True
    pasos = {(ord(b) - ord(a)) % 10 for a, b in zip(matricula, matricula[1:])}
    return pasos == {1} or pasos == {9}


def generar(clave, contador, sede=0, ranuras=10, longitud=7):
    if len(clave) < 32:
        raise ErrorMatricula("clave demasiado corta")
    if ranuras < 1 or not 0 <= sede < ranuras:
        raise ErrorMatricula("sede fuera de rango")
    if contador < 0:
        raise ErrorMatricula("contador negativo")
    limite = capacidad_por_sede(longitud, ranuras)
    while True:
        if contador >= limite:
            raise EspacioAgotado("no quedan matriculas para esta sede")
        matricula = construir(clave, contador * ranuras + sede, longitud)
        contador += 1
        if not es_trivial(matricula):
            return matricula, contador


def formatear(matricula):
    corte = len(matricula) // 2
    return matricula[:corte] + " " + matricula[corte:]


def normalizar(texto):
    return "".join(c for c in texto if c.isascii() and c.isdigit())


def extraer_candidatas(texto, longitud=7):
    encontradas = []
    vistas = set()
    grupos = []
    actual = []
    for c in texto:
        if c.isascii() and c.isdigit():
            actual.append(c)
        elif c in " -./" and actual:
            actual.append(c)
        else:
            if actual:
                grupos.append("".join(actual))
            actual = []
    if actual:
        grupos.append("".join(actual))
    for grupo in grupos:
        piezas = [p for p in grupo.replace("-", " ").replace(".", " ").replace("/", " ").split() if p]
        opciones = list(piezas)
        for i in range(len(piezas)):
            junto = piezas[i]
            for j in range(i + 1, len(piezas)):
                junto += piezas[j]
                if len(junto) > longitud:
                    break
                opciones.append(junto)
        for op in opciones:
            if len(op) >= longitud:
                for k in range(len(op) - longitud + 1):
                    trozo = op[k:k + longitud]
                    if trozo not in vistas and es_valida(trozo, longitud):
                        vistas.add(trozo)
                        encontradas.append(trozo)
    return encontradas


def vecinas(matricula):
    resultado = set()
    n = len(matricula)
    for i in range(n):
        for dgt in "0123456789":
            if dgt != matricula[i]:
                resultado.add(matricula[:i] + dgt + matricula[i + 1:])
    for i in range(n - 1):
        if matricula[i] != matricula[i + 1]:
            resultado.add(matricula[:i] + matricula[i + 1] + matricula[i] + matricula[i + 2:])
    for i in range(n):
        resultado.add(matricula[:i] + matricula[i + 1:])
    for i in range(n + 1):
        for dgt in "0123456789":
            resultado.add(matricula[:i] + dgt + matricula[i:])
    resultado.discard(matricula)
    return resultado
