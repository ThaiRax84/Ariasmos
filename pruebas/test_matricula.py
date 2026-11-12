import itertools
import random

import pytest

from nucleo import matricula as m

CLAVE = bytes(range(32))
OTRA = bytes(range(1, 33))


def test_tabla_damm_es_cuasigrupo_antisimetrico():
    for fila in m.DAMM:
        assert sorted(fila) == list(range(10))
    for col in range(10):
        assert sorted(m.DAMM[f][col] for f in range(10)) == list(range(10))
    for i in range(10):
        assert m.DAMM[i][i] == 0


def test_vector_conocido_damm():
    assert m.digito_verificador("572") == "4"
    assert m.es_valida("5724", 4) is True
    assert m.es_valida("5742", 4) is False
    assert m.es_valida("0572" + m.digito_verificador("0572"), 5) is False


def test_permutacion_es_biyeccion_completa_longitud_7():
    total = m.capacidad(7)
    assert total == 900_000
    vistos = bytearray(total)
    for i in range(total):
        y = m.permutar(CLAVE, i, 7)
        assert 0 <= y < total
        assert vistos[y] == 0
        vistos[y] = 1
    assert sum(vistos) == total


@pytest.mark.parametrize("longitud", [5, 6])
def test_permutacion_biyeccion_longitudes_cortas(longitud):
    total = m.capacidad(longitud)
    salida = {m.permutar(CLAVE, i, longitud) for i in range(total)}
    assert salida == set(range(total))


@pytest.mark.parametrize("longitud", [5, 6, 7, 8, 10, 12])
def test_inversa(longitud):
    rnd = random.Random(longitud)
    total = m.capacidad(longitud)
    for _ in range(300):
        i = rnd.randrange(total)
        mat = m.construir(CLAVE, i, longitud)
        assert len(mat) == longitud
        assert mat[0] != "0"
        assert m.es_valida(mat, longitud)
        assert m.indice_de(CLAVE, mat, longitud) == i


def test_detecta_todo_error_de_un_digito_y_transposicion_adyacente():
    rnd = random.Random(7)
    for _ in range(20_000):
        mat = m.construir(CLAVE, rnd.randrange(900_000), 7)
        pos = rnd.randrange(7)
        for dgt in "0123456789":
            if dgt != mat[pos]:
                assert not m.es_valida(mat[:pos] + dgt + mat[pos + 1:], 7)
        for i in range(6):
            if mat[i] != mat[i + 1]:
                assert not m.es_valida(mat[:i] + mat[i + 1] + mat[i] + mat[i + 2:], 7)


def test_deteccion_exhaustiva_sobre_todos_los_cuerpos_de_4_digitos():
    for cuerpo in range(1000, 10000):
        s = str(cuerpo)
        mat = s + m.digito_verificador(s)
        for pos in range(5):
            for dgt in "0123456789":
                if dgt != mat[pos]:
                    cand = mat[:pos] + dgt + mat[pos + 1:]
                    estado = 0
                    for c in cand:
                        estado = m.DAMM[estado][int(c)]
                    assert estado != 0
        for i in range(4):
            if mat[i] != mat[i + 1]:
                cand = mat[:i] + mat[i + 1] + mat[i] + mat[i + 2:]
                estado = 0
                for c in cand:
                    estado = m.DAMM[estado][int(c)]
                assert estado != 0


def test_claves_distintas_dan_secuencias_distintas():
    a = [m.construir(CLAVE, i) for i in range(200)]
    b = [m.construir(OTRA, i) for i in range(200)]
    assert a != b
    assert len(set(a) & set(b)) < 5


def test_no_parece_secuencial():
    cuerpos = [int(m.construir(CLAVE, i)[:-1]) for i in range(2000)]
    difs = [abs(b - a) for a, b in zip(cuerpos, cuerpos[1:])]
    assert sum(1 for d in difs if d < 1000) < 20
    primeros = {str(c)[0] for c in cuerpos}
    assert primeros == set("123456789")


def test_sedes_no_chocan():
    por_sede = []
    for sede in range(10):
        contador = 0
        emitidas = set()
        for _ in range(3000):
            mat, contador = m.generar(CLAVE, contador, sede=sede, ranuras=10)
            emitidas.add(mat)
        assert len(emitidas) == 3000
        por_sede.append(emitidas)
    for a, b in itertools.combinations(por_sede, 2):
        assert not (a & b)


def test_generar_salta_triviales_y_avanza_contador():
    contador = 0
    for _ in range(5000):
        mat, nuevo = m.generar(CLAVE, contador)
        assert nuevo > contador
        assert not m.es_trivial(mat)
        contador = nuevo
    assert m.es_trivial("1111111")
    assert m.es_trivial("1234567")
    assert m.es_trivial("9876543")
    assert m.es_trivial("8901234")
    assert not m.es_trivial("4829173")


def test_espacio_agotado():
    with pytest.raises(m.EspacioAgotado):
        m.generar(CLAVE, m.capacidad_por_sede(7, 10))
    with pytest.raises(m.ErrorMatricula):
        m.generar(b"corta", 0)
    with pytest.raises(m.ErrorMatricula):
        m.generar(CLAVE, 0, sede=10, ranuras=10)


def test_extraer_candidatas_de_texto_bancario():
    mat = m.construir(CLAVE, 12345)
    assert m.extraer_candidatas(f"PAGO COLEGIATURA {mat} NOV") == [mat]
    assert m.extraer_candidatas(f"matricula {mat[:3]} {mat[3:]}") == [mat]
    assert m.extraer_candidatas(f"ref:{mat[:3]}-{mat[3:]}.") == [mat]
    assert mat in m.extraer_candidatas(f"00{mat}")
    assert m.extraer_candidatas("colegiatura de juanito") == []
    assert m.extraer_candidatas("") == []


def test_formato_y_normalizacion():
    assert m.formatear("4829173") == "482 9173"
    assert m.normalizar(" 482-9173 ") == "4829173"


def test_vecinas_contiene_errores_tipicos():
    mat = m.construir(CLAVE, 777)
    v = m.vecinas(mat)
    assert mat not in v
    assert mat[:-1] in v
    assert mat[1:] in v
    mal = mat[:2] + str((int(mat[2]) + 1) % 10) + mat[3:]
    assert mal in v
    assert mat in m.vecinas(mal)


VECTORES = ["1923501", "7723043", "8944604", "4705821", "2025236"]
VECTOR_SEDE_3 = "4705821"


def test_vectores_fijos():
    esperado = [m.construir(CLAVE, i) for i in range(5)]
    assert esperado == VECTORES
    assert m.generar(CLAVE, 0, sede=3, ranuras=10)[0] == VECTOR_SEDE_3
