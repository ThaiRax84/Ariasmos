import random

import pytest

from nucleo import clabe

VALIDAS = ["002010077777777771", "032180000118359719"]


def test_vectores_publicados():
    for valor in VALIDAS:
        datos = clabe.analizar(valor)
        assert datos["clabe"] == valor
        assert clabe.digito_verificador(valor[:-1]) == valor[-1]
    assert clabe.analizar(VALIDAS[0])["banco"] == "002"
    assert clabe.analizar(VALIDAS[0])["plaza"] == "010"
    assert clabe.analizar(VALIDAS[0])["cuenta"] == "07777777777"


def test_acepta_espacios_y_guiones():
    assert clabe.analizar("002 010 07777777777 1")["clabe"] == VALIDAS[0]
    assert clabe.analizar("002-010-07777777777-1")["clabe"] == VALIDAS[0]
    assert clabe.formatear(VALIDAS[0]) == "002 010 07777777777 1"


def test_longitud_incorrecta():
    for valor in ("", "123", VALIDAS[0][:-1], VALIDAS[0] + "1"):
        with pytest.raises(clabe.ErrorClabe) as error:
            clabe.analizar(valor)
        assert error.value.codigo == "longitud"


def test_digito_incorrecto():
    with pytest.raises(clabe.ErrorClabe) as error:
        clabe.analizar("002010077777777772")
    assert error.value.codigo == "digito"
    assert not clabe.es_valida("002010077777777772")


def test_detecta_todo_error_de_un_digito():
    azar = random.Random(18)
    for _ in range(3000):
        cuerpo = "".join(azar.choice("0123456789") for _ in range(17))
        completa = cuerpo + clabe.digito_verificador(cuerpo)
        assert clabe.es_valida(completa)
        posicion = azar.randrange(18)
        for digito in "0123456789":
            if digito != completa[posicion]:
                assert not clabe.es_valida(completa[:posicion] + digito + completa[posicion + 1:])


def test_digito_verificador_exige_17_digitos():
    with pytest.raises(clabe.ErrorClabe):
        clabe.digito_verificador("123")
    with pytest.raises(clabe.ErrorClabe):
        clabe.digito_verificador("0020100777777777a")
