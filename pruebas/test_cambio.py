import itertools
import random

import pytest

from caja.cambio import DemasiadoComplejo, proponer

MXN = [100000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100, 50]


def voraz(cambio, existencias):
    resto = cambio
    elegidas = {}
    for valor in sorted(existencias, reverse=True):
        usadas = min(existencias[valor], resto // valor)
        if usadas:
            elegidas[valor] = usadas
            resto -= usadas * valor
    return elegidas if resto == 0 else None


def fuerza_bruta(cambio, existencias):
    valores = sorted(existencias, reverse=True)
    mejor = None
    for cuentas in itertools.product(*[range(existencias[v] + 1) for v in valores]):
        if sum(c * v for c, v in zip(cuentas, valores)) == cambio:
            piezas = sum(cuentas)
            if mejor is None or piezas < mejor:
                mejor = piezas
    return mejor


def suma(propuesta):
    return sum(v * c for v, c in propuesta.items())


def test_cambio_cero_y_sin_existencias():
    assert proponer(0, {}) == {}
    assert proponer(0, {500: 3}) == {}
    assert proponer(500, {}) is None
    assert proponer(500, {500: 0}) is None


def test_cambio_exacto_con_denominaciones_mexicanas():
    existencias = {5000: 2, 2000: 5, 1000: 3, 500: 4, 100: 10}
    propuesta = proponer(8700, existencias)
    assert suma(propuesta) == 8700 and propuesta == {5000: 1, 2000: 1, 1000: 1, 500: 1, 100: 2}
    assert all(propuesta[v] <= existencias[v] for v in propuesta)


def test_donde_la_estrategia_voraz_falla_el_calculo_exacto_encuentra_cambio():
    existencias = {5000: 1, 2000: 3}
    assert voraz(6000, existencias) is None
    assert proponer(6000, existencias) == {2000: 3}


def test_donde_la_voraz_da_mas_piezas_el_calculo_da_las_minimas():
    existencias = {400: 1, 300: 2, 100: 2}
    assert voraz(600, existencias) == {400: 1, 100: 2}
    assert proponer(600, existencias) == {300: 2}


def test_sin_solucion_lo_dice():
    assert proponer(300, {500: 4, 200: 1}) is None
    assert proponer(150, {100: 5}) is None
    assert proponer(1000000, {500: 10}) is None


def test_nunca_usa_mas_piezas_de_las_que_hay():
    existencias = {1000: 1, 500: 1, 100: 3}
    assert proponer(1800, existencias) == {1000: 1, 500: 1, 100: 3}
    assert proponer(1900, existencias) is None


@pytest.mark.parametrize("semilla", range(40))
def test_coincide_con_la_fuerza_bruta(semilla):
    azar = random.Random(semilla)
    valores = azar.sample([1, 2, 3, 4, 5, 7, 10, 12, 20, 25, 50], azar.randint(2, 4))
    existencias = {v: azar.randint(0, 4) for v in valores}
    for cambio in range(0, 80):
        esperado = fuerza_bruta(cambio, existencias)
        propuesta = proponer(cambio, existencias)
        if esperado is None:
            assert propuesta is None, (cambio, existencias)
        else:
            assert propuesta is not None and suma(propuesta) == cambio and sum(propuesta.values()) == esperado, (cambio, existencias, propuesta)
            assert all(0 < propuesta[v] <= existencias[v] for v in propuesta)


def test_caja_grande_responde_rapido():
    existencias = {v: 500 for v in MXN}
    propuesta = proponer(9999950, existencias)
    assert suma(propuesta) == 9999950 and sum(propuesta.values()) == 109
    assert proponer(sum(v * c for v, c in existencias.items()), existencias) == existencias


def test_entradas_invalidas():
    for malo in (-1, 1.5, "100", True):
        with pytest.raises(ValueError):
            proponer(malo, {100: 1})
    with pytest.raises(ValueError):
        proponer(100, {0: 1})


def test_limite_de_combinaciones():
    existencias = {v: 50 for v in (98, 94, 90, 86, 82, 78, 74, 70, 66, 62, 58, 54, 50, 46, 42, 38, 34, 30, 26, 22)}
    with pytest.raises(DemasiadoComplejo):
        proponer(9999, existencias, limite=1000)
    assert proponer(9999, {v: 50 for v in (98, 94, 90, 86)}) is None
