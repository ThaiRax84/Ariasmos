from nucleo import identificacion as ident
from nucleo import matricula as m

CLAVE = bytes(range(32))
A, B, C = (m.construir(CLAVE, i) for i in (10, 20, 30))
PADRON = {A: [130000, 5000], B: [100000], C: []}
CUENTA = "012345678901234567"


def existe(matricula):
    return matricula in PADRON


def saldos(matricula):
    return PADRON[matricula]


def decidir(ref, concepto, importe, **extra):
    return ident.decidir(ref, concepto, importe, existe, saldos, **extra)


def test_matricula_en_referencia_o_en_concepto_es_automatica():
    for ref, concepto in ((A, "colegiatura"), ("0260803", f"pago {A}"), ("", f"mat {A[:3]} {A[3:]}"), ("123456", f"{A[:3]}-{A[3:]} nov")):
        d = decidir(ref, concepto, 130000)
        assert (d.resultado, d.matricula, d.motivo) == (ident.AUTOMATICA, A, ident.POR_MATRICULA)
        assert d.coincide_importe


def test_misma_matricula_en_ambos_campos_no_es_ambigua():
    d = decidir(A, f"colegiatura {A}", 999)
    assert d.resultado == ident.AUTOMATICA and d.matricula == A and not d.coincide_importe


def test_dos_matriculas_distintas_no_se_aplica_sola():
    d = decidir(A, f"hermanos {B}", 100000)
    assert d.resultado == ident.SUGERIDA and d.motivo == ident.AMBIGUA
    assert d.matricula == B and d.alternativas == (A,)


def test_matricula_valida_que_no_existe_no_cuenta():
    ajena = next(x for x in (m.construir(CLAVE, i) for i in range(1000, 1100)) if x not in PADRON)
    assert decidir(ajena, "pago", 1000).resultado == ident.SIN_PISTA


def test_un_digito_mal_se_sugiere_y_no_se_aplica():
    mala = A[:3] + str((int(A[3]) + 1) % 10) + A[4:]
    assert not m.es_valida(mala)
    d = decidir(mala, "colegiatura", 130000)
    assert d.resultado == ident.SUGERIDA and d.matricula == A and d.motivo == ident.POR_MATRICULA_CERCANA and d.coincide_importe


def test_digitos_vecinos_intercambiados_un_digito_de_menos_o_de_mas():
    i = next(i for i in range(6) if A[i] != A[i + 1])
    for mala in (A[:i] + A[i + 1] + A[i] + A[i + 2:], A[:-1], A[1:], A + "5"):
        d = decidir("", f"pago {mala}", 5)
        assert d.resultado == ident.SUGERIDA and A in (d.matricula,) + d.alternativas


def test_matricula_incrustada_en_un_numero_mas_largo_solo_se_sugiere():
    for texto in (A + "5", "7" + A, "55" + A + "0018"):
        d = decidir("", f"pago {texto}", 130000)
        assert d.resultado == ident.SUGERIDA and d.matricula == A and d.motivo == ident.POR_MATRICULA_CERCANA
    assert decidir("", f"pago 000{A}", 130000).resultado == ident.AUTOMATICA
    assert decidir("", f"ref.{A}.", 130000).resultado == ident.AUTOMATICA


def test_esta_aislada():
    assert ident.esta_aislada("4829173", "pago 482 9173 nov")
    assert ident.esta_aislada("4829173", "482-9173")
    assert ident.esta_aislada("4829173", "0004829173")
    assert not ident.esta_aislada("4829173", "14829173")
    assert not ident.esta_aislada("4829173", "48291735")
    assert not ident.esta_aislada("4829173", None)


def test_sin_matricula_el_pagador_conocido_se_sugiere():
    d = decidir("0260803", "colegiatura", 100000, cuenta_pagador=CUENTA, regla_de=lambda c: B if c == CUENTA else None)
    assert (d.resultado, d.matricula, d.motivo) == (ident.SUGERIDA, B, ident.POR_PAGADOR) and d.coincide_importe


def test_pagador_confiable_con_importe_exacto_puede_aplicarse_solo():
    extra = dict(cuenta_pagador=CUENTA, regla_de=lambda c: B, pagador_confiable=lambda c: True)
    assert decidir("0260803", "colegiatura", 100000, **extra).resultado == ident.AUTOMATICA
    assert decidir("0260803", "colegiatura", 77700, **extra).resultado == ident.SUGERIDA


def test_matricula_que_contradice_a_un_pagador_confiable_no_se_aplica_sola():
    extra = dict(cuenta_pagador=CUENTA, regla_de=lambda c: B, pagador_confiable=lambda c: True)
    d = decidir(A, "pago", 130000, **extra)
    assert d.resultado == ident.SUGERIDA and d.motivo == ident.CONTRADICCION and d.matricula == A and d.alternativas == (B,)
    extra["pagador_confiable"] = lambda c: False
    assert decidir(A, "pago", 130000, **extra).resultado == ident.AUTOMATICA


def test_sin_pista():
    for ref, concepto in (("", ""), ("0260803", "colegiatura de juan"), ("1", "x"), (None, None)):
        assert decidir(ref, concepto, 100).resultado == ident.SIN_PISTA


def test_coincide_importe():
    assert ident.coincide_importe(130000, [130000, 5000])
    assert ident.coincide_importe(135000, [130000, 5000])
    assert ident.coincide_importe(5000, [130000, 5000])
    assert not ident.coincide_importe(100, [130000, 5000])
    assert not ident.coincide_importe(100, [])
    assert ident.coincide_importe(230000, [130000, 100000, 5000])
