import io
import random

import pytest

from nucleo import sobre

CLAVE = bytes(range(32))
OTRA = bytes(range(1, 33))


def sellar(datos, clave=CLAVE, trozo=64):
    salida = io.BytesIO()
    sobre.cifrar(io.BytesIO(datos), salida, clave, trozo=trozo)
    return salida.getvalue()


def abrir(sellado, clave=CLAVE, trozo=64):
    salida = io.BytesIO()
    sobre.descifrar(io.BytesIO(sellado), salida, clave, trozo_maximo=trozo + 16)
    return salida.getvalue()


@pytest.mark.parametrize("largo", [0, 1, 63, 64, 65, 128, 129, 1000])
def test_ida_y_vuelta(largo):
    datos = random.Random(largo).randbytes(largo)
    sellado = sellar(datos)
    assert abrir(sellado) == datos
    assert datos[:16] not in sellado or largo < 16


def test_dos_cifrados_del_mismo_contenido_son_distintos():
    assert sellar(b"x" * 500) != sellar(b"x" * 500)


def test_clave_equivocada():
    with pytest.raises(sobre.ErrorSobre):
        abrir(sellar(b"secreto" * 50), OTRA)


def test_un_bit_alterado_en_cualquier_parte_se_detecta():
    sellado = bytearray(sellar(random.Random(1).randbytes(300)))
    for posicion in range(len(sellado)):
        alterado = bytearray(sellado)
        alterado[posicion] ^= 1
        with pytest.raises(sobre.ErrorSobre):
            abrir(bytes(alterado))


def test_truncado_se_detecta_en_cualquier_punto():
    sellado = sellar(random.Random(2).randbytes(300))
    for corte in range(len(sellado)):
        with pytest.raises(sobre.ErrorSobre):
            abrir(sellado[:corte])


def _trozos(sellado):
    cabecera = len(sobre.MAGIA) + 8
    partes, i = [], cabecera
    while i < len(sellado):
        largo = int.from_bytes(sellado[i:i + 4], "big")
        partes.append(sellado[i:i + 4 + largo])
        i += 4 + largo
    return sellado[:cabecera], partes


def test_trozos_reordenados_quitados_o_repetidos_se_detectan():
    cabecera, partes = _trozos(sellar(random.Random(3).randbytes(300)))
    assert len(partes) == 5
    variantes = [
        [partes[1], partes[0]] + partes[2:],
        partes[:-1],
        partes[1:],
        partes[:2] + partes[3:],
        partes + [partes[-1]],
        partes[:3] + [partes[2]] + partes[3:],
    ]
    for variante in variantes:
        with pytest.raises(sobre.ErrorSobre):
            abrir(cabecera + b"".join(variante))


def test_trozos_de_otro_respaldo_no_se_mezclan():
    cabecera_a, partes_a = _trozos(sellar(b"a" * 300))
    _, partes_b = _trozos(sellar(b"b" * 300))
    with pytest.raises(sobre.ErrorSobre):
        abrir(cabecera_a + b"".join([partes_a[0], partes_b[1]] + partes_a[2:]))


def test_archivo_que_no_es_un_sobre():
    for basura in (b"", b"hola", b"PK\x03\x04" + b"0" * 100, sobre.MAGIA, sobre.MAGIA + b"12345678"):
        with pytest.raises(sobre.ErrorSobre):
            abrir(basura)


def test_largo_declarado_absurdo_no_reserva_memoria():
    cabecera, _ = _trozos(sellar(b"x"))
    with pytest.raises(sobre.ErrorSobre):
        abrir(cabecera + (2 ** 31).to_bytes(4, "big") + b"x" * 32)


def test_clave_invalida():
    for clave in (b"corta", "texto" * 8, None):
        with pytest.raises(sobre.ErrorSobre):
            sellar(b"x", clave)


def test_clave_de_recuperacion_ida_y_vuelta():
    azar = random.Random(4)
    for _ in range(300):
        clave = azar.randbytes(32)
        texto = sobre.clave_a_texto(clave)
        assert sobre.texto_a_clave(texto) == clave
        assert sobre.texto_a_clave(texto.lower().replace("-", " ")) == clave
        grupos = texto.split("-")
        assert all(len(g) == 4 for g in grupos[:-1]) and all(c in sobre.ALFABETO + "-" for c in texto)
    assert not set("ILOU") & set(sobre.ALFABETO)


def test_clave_de_recuperacion_detecta_errores_de_captura():
    azar = random.Random(5)
    clave = azar.randbytes(32)
    texto = sobre.clave_a_texto(clave).replace("-", "")
    detectados = total = 0
    for posicion in range(len(texto)):
        for letra in sobre.ALFABETO:
            if letra == texto[posicion]:
                continue
            total += 1
            try:
                if sobre.texto_a_clave(texto[:posicion] + letra + texto[posicion + 1:]) != clave:
                    continue
            except sobre.ErrorSobre:
                detectados += 1
    assert detectados == total
    for malo in ("", "ABCD", texto[:-1], texto + "A", texto[:10] + "!" + texto[11:]):
        with pytest.raises(sobre.ErrorSobre):
            sobre.texto_a_clave(malo)


def test_letras_parecidas_se_aceptan_al_teclear():
    clave = bytes(range(32))
    texto = sobre.clave_a_texto(clave)
    assert sobre.texto_a_clave(texto.replace("0", "O").replace("V", "U")) == clave


def test_texto_cifrado_ligado_a_su_contexto():
    ficha = sobre.cifrar_texto(CLAVE, "JBSWY3DPEHPK3PXP", "totp|7")
    assert sobre.esta_cifrado(ficha) and "JBSWY3DP" not in ficha
    assert sobre.descifrar_texto(CLAVE, ficha, "totp|7") == "JBSWY3DPEHPK3PXP"
    assert sobre.cifrar_texto(CLAVE, "JBSWY3DPEHPK3PXP", "totp|7") != ficha
    for clave, contexto in ((CLAVE, "totp|8"), (OTRA, "totp|7")):
        with pytest.raises(sobre.ErrorSobre):
            sobre.descifrar_texto(clave, ficha, contexto)
    with pytest.raises(sobre.ErrorSobre):
        sobre.descifrar_texto(CLAVE, ficha[:-4] + "AAAA", "totp|7")
    with pytest.raises(sobre.ErrorSobre):
        sobre.descifrar_texto(CLAVE, "JBSWY3DPEHPK3PXP", "totp|7")
    assert not sobre.esta_cifrado("JBSWY3DPEHPK3PXP")


def test_derivar_da_claves_distintas_y_estables():
    a, b = sobre.derivar(CLAVE, "respaldo"), sobre.derivar(CLAVE, "secretos")
    assert len(a) == 32 and a != b and a != CLAVE and a == sobre.derivar(CLAVE, "respaldo")
    assert sobre.derivar(OTRA, "respaldo") != a
