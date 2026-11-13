import re
from dataclasses import dataclass

from . import matricula as generador

AUTOMATICA = "automatica"
SUGERIDA = "sugerida"
SIN_PISTA = "sin_pista"

POR_MATRICULA = "matricula"
POR_MATRICULA_CERCANA = "matricula_cercana"
POR_PAGADOR = "pagador"
AMBIGUA = "varias_matriculas"
CONTRADICCION = "matricula_y_pagador_distintos"


@dataclass(frozen=True)
class Decision:
    resultado: str
    matricula: str = ""
    motivo: str = ""
    alternativas: tuple = ()
    coincide_importe: bool = False


def _unicas(valores):
    vistas = []
    for valor in valores:
        if valor not in vistas:
            vistas.append(valor)
    return vistas


def _corridas(texto):
    corridas = []
    actual = []
    for c in texto or "":
        if c.isascii() and c.isdigit():
            actual.append(c)
        else:
            if actual:
                corridas.append("".join(actual))
            actual = []
    if actual:
        corridas.append("".join(actual))
    return corridas


def esta_aislada(matricula, texto):
    patron = r"(?<!\d)0*" + r"[ \-./]?".join(matricula) + r"(?!\d)"
    return re.search(patron, texto or "") is not None


def coincide_importe(importe, saldos):
    saldos = [s for s in saldos if s > 0]
    if not saldos:
        return False
    if importe in saldos or importe == sum(saldos):
        return True
    acumulado = 0
    for saldo in saldos:
        acumulado += saldo
        if acumulado == importe:
            return True
    return False


def cercanas(referencia, concepto, existe, longitud=7):
    encontradas = []
    for texto in (referencia, concepto):
        for corrida in _corridas(texto):
            if not longitud - 1 <= len(corrida) <= longitud + 1:
                continue
            for vecina in sorted(generador.vecinas(corrida)):
                if len(vecina) == longitud and generador.es_valida(vecina, longitud) and existe(vecina):
                    encontradas.append(vecina)
    return _unicas(encontradas)


def decidir(referencia, concepto, importe, existe, saldos_de, cuenta_pagador="", regla_de=None, pagador_confiable=None, longitud=7):
    exactas = _unicas(
        [m for m in generador.extraer_candidatas(referencia or "", longitud) if existe(m)]
        + [m for m in generador.extraer_candidatas(concepto or "", longitud) if existe(m)]
    )
    por_pagador = regla_de(cuenta_pagador) if regla_de is not None and cuenta_pagador else None

    def con_importe(matricula):
        return coincide_importe(importe, saldos_de(matricula))

    aisladas = [x for x in exactas if esta_aislada(x, referencia) or esta_aislada(x, concepto)]
    incrustadas = [x for x in exactas if x not in aisladas]
    if len(exactas) == 1 and aisladas:
        matricula = exactas[0]
        if por_pagador and por_pagador != matricula and pagador_confiable is not None and pagador_confiable(cuenta_pagador):
            return Decision(SUGERIDA, matricula, CONTRADICCION, (por_pagador,), con_importe(matricula))
        return Decision(AUTOMATICA, matricula, POR_MATRICULA, (), con_importe(matricula))
    if len(exactas) > 1:
        ordenadas = sorted(exactas, key=lambda x: (not con_importe(x), x != por_pagador, exactas.index(x)))
        return Decision(SUGERIDA, ordenadas[0], AMBIGUA, tuple(ordenadas[1:]), con_importe(ordenadas[0]))
    vecinas = _unicas(incrustadas + cercanas(referencia, concepto, existe, longitud))
    if por_pagador and por_pagador not in vecinas:
        candidatas = [por_pagador] + vecinas
    else:
        candidatas = list(vecinas)
    if not candidatas:
        return Decision(SIN_PISTA)
    ordenadas = sorted(candidatas, key=lambda m: (m != por_pagador, not con_importe(m), candidatas.index(m)))
    mejor = ordenadas[0]
    if mejor == por_pagador:
        if pagador_confiable is not None and pagador_confiable(cuenta_pagador) and con_importe(mejor) and len(ordenadas) == 1:
            return Decision(AUTOMATICA, mejor, POR_PAGADOR, (), True)
        return Decision(SUGERIDA, mejor, POR_PAGADOR, tuple(ordenadas[1:]), con_importe(mejor))
    return Decision(SUGERIDA, mejor, POR_MATRICULA_CERCANA, tuple(ordenadas[1:]), con_importe(mejor))
