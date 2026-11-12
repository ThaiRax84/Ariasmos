import pytest

from nucleo import cadena, dinero, telefono, totp

SECRETO_RFC = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


@pytest.mark.parametrize("momento,esperado", [(59, "94287082"), (1111111109, "07081804"), (1234567890, "89005924"), (2000000000, "69279037")])
def test_totp_vectores_rfc6238(momento, esperado):
    assert totp.codigo(SECRETO_RFC, totp.paso_actual(momento), digitos=8) == esperado
    assert totp.codigo(SECRETO_RFC, totp.paso_actual(momento)) == esperado[-6:]


def test_totp_verifica_con_ventana_y_rechaza_otro():
    secreto = totp.generar_secreto()
    paso = totp.paso_actual(1_000_000)
    assert totp.verificar(secreto, totp.codigo(secreto, paso - 1), momento=1_000_000) == paso - 1
    assert totp.verificar(secreto, totp.codigo(secreto, paso - 3), momento=1_000_000) is None
    assert totp.verificar(secreto, "12ab", momento=1_000_000) is None
    assert totp.uri(secreto, "persona", "Negocio X").startswith("otpauth://totp/Negocio%20X%3Apersona?secret=")


def test_dinero_en_centavos():
    assert dinero.a_centavos("1,250.5") == 125050
    assert dinero.a_centavos("$ 3") == 300
    assert dinero.a_centavos(".07") == 7
    assert dinero.formatear(123456789) == "$1,234,567.89"
    for malo in ("", "1.234", "abc", "1.2.3", "١٢"):
        with pytest.raises(dinero.ErrorImporte):
            dinero.a_centavos(malo)


def test_cadena_detecta_alteracion():
    eslabones = []
    anterior = cadena.GENESIS
    for i in range(5):
        contenido = {"i": i, "texto": "á"}
        propio = cadena.encadenar(anterior, contenido)
        eslabones.append((anterior, contenido, propio))
        anterior = propio
    assert cadena.verificar(eslabones) is None
    eslabones[2] = (eslabones[2][0], {"i": 99, "texto": "á"}, eslabones[2][2])
    assert cadena.verificar(eslabones) == 2


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("55 1234 5678", "525512345678"),
        ("(55) 1234-5678", "525512345678"),
        ("+52 55 1234 5678", "525512345678"),
        ("0052 55 1234 5678", "525512345678"),
        ("525512345678", "525512345678"),
    ],
)
def test_telefono_normaliza(entrada, esperado):
    assert telefono.normalizar(entrada, "52", 10) == esperado


@pytest.mark.parametrize("entrada", ["", "12345", "55 1234 567", "+1 555 123 4567", "55-1234-5678 ext 2", "abc"])
def test_telefono_rechaza(entrada):
    with pytest.raises(telefono.TelefonoInvalido):
        telefono.normalizar(entrada, "52", 10)


def test_telefono_formato():
    assert telefono.formatear("525512345678", "52") == "+52 55 1234 5678"
