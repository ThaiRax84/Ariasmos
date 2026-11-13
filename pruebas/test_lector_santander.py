from datetime import date

import pytest

from nucleo.lectores import santander_pyme as s

ENCABEZADO = [
    "          Banco Ejemplo, S.A.,",
    "          Institución de Banca Múltiple.                                              ESTADO DE CUENTA",
    "NEGOCIO DE PRUEBA SC                                                                  CODIGO DE CLIENTE NO. 00000000",
    "                                                                                      PERIODO DEL 01-AGO-2026 AL 31-AGO-2026",
]
COLUMNAS = "  FECHA      FOLIO      DESCRIPCION                                    DEPOSITO          RETIRO            SALDO"


def dinero(centavos):
    return f"{centavos // 100:,}.{centavos % 100:02d}"


def renglon(dia, folio, descripcion, importe, saldo, desplazo=0):
    return f"{dia:02d}-AGO-2026 {folio} {descripcion}".ljust(96 + desplazo) + dinero(importe).rjust(12) + " " * 14 + dinero(saldo).rjust(12)


def sub(texto):
    return " " * 26 + texto


def estado(saltos=True):
    lineas = list(ENCABEZADO)
    lineas += [
        "           CUENTA EJEMPLO PYME                            00-00000000-0         CUENTA CLABE: 002010077777777771",
        "",
        "        Detalle de movimientos cuenta de cheques.",
        "CUENTA EJEMPLO PYME 00-00000000-0",
        " SALDO FINAL DEL PERIODO ANTERIOR:                                 $1,000.00",
        COLUMNAS,
    ]
    saldo = 100000
    movimientos = [
        (3, "1000001", "ABONO TRANSFERENCIA ENLACE colegiatura 4829173 de", 130000, +1, [sub("agosto")]),
        (3, "1000002", "ABONO TRANSFERENCIA SPEI HORA 10:53:26", 100000, +1, [
            sub("RECIBIDO DE BANCO UNO"), sub("DE LA CUENTA 002010077777777771"), sub("DEL CLIENTE PERSONA FICTICIA UNO"),
            sub("CLAVE DE RASTREO ABC123456789"), sub("REF 0260803"), sub("CONCEPTO colegiatura hijo"), sub("RFC XAXX010101000"),
        ]),
        (4, "1000003", "DEPOSITO EN EFECTIVO ATM", 50000, +1, []),
        (5, "1000004", "CONSUMO LOCAL AJENO TERMINACION 0000", 25050, -1, [sub("COMERCIO FICTICIO")]),
        (6, "1000005", "ABONO TRANSF RAPIDA SANTANDER Transferencia a NEGOCIO", 85000, +1, []),
        (7, "1000006", "ABONO TRANSFERENCIA SPEI HORA 16:17:23", 208000, +1, [
            sub("RECIBIDO DE BANCO DOS"), sub("DE LA CUENTA 032180000118359719"), sub("DEL CLIENTE PERSONA,FICTICIA/DOS"),
            sub("CLAVE DE RASTREO 2026080740014ABCD0000012345"), sub("REF 4829173"), sub("CONCEPTO"), sub("RFC XAXX010101000"),
        ]),
        (8, "1000007", "ABONO POR DEVOLUCIONES SPEI HORA 09:00:00", 30000, +1, [sub("DEVUELTO POR BANCO TRES"), sub("CLAVE DE RASTREO DEV0001")]),
        (9, "1000008", "PAGO TRANSFERENCIA SPEI HORA 12:00:00", 120000, -1, [
            sub("ENVIADO A BANCO UNO"), sub("A LA CUENTA 002010077777777771"), sub("AL CLIENTE PROVEEDOR FICTICIO"),
            sub("CLAVE DE RASTREO SAL0001"), sub("REF 1234567"), sub("CONCEPTO renta"),
        ]),
    ]
    depositos = retiros = 0
    for n, (dia, folio, descripcion, importe, signo, detalle) in enumerate(movimientos):
        saldo += signo * importe
        if signo > 0:
            depositos += importe
        else:
            retiros += importe
        lineas.append(renglon(dia, folio, descripcion, importe, saldo, desplazo=(n % 3) * 4))
        if saltos and n == 1:
            lineas += detalle[:3] + ["", " Página 1 de 2.", ""] + ENCABEZADO + [COLUMNAS] + detalle[3:]
        else:
            lineas += detalle
    lineas.append(" " * 30 + "TOTAL".ljust(70) + dinero(depositos).rjust(14) + dinero(retiros).rjust(18))
    lineas.append(" " * 100 + "SALDO FINAL DEL PERIODO:".ljust(40) + "$" + dinero(saldo))
    lineas += ["", "        Detalle de movimientos Inversión.", " SALDO FINAL DEL PERIODO ANTERIOR:                    0.00", " " * 30 + "TOTAL".ljust(70) + "0.00".rjust(14) + "0.00".rjust(18), " " * 100 + "SALDO FINAL DEL PERIODO:".ljust(40) + "$0.00"]
    return lineas, saldo, depositos, retiros


def test_lee_y_cuadra():
    lineas, saldo, depositos, retiros = estado()
    e = s.leer(lineas)
    assert (e.saldo_inicial, e.saldo_final, e.depositos, e.retiros) == (100000, saldo, depositos, retiros)
    assert e.clabe == "002010077777777771"
    assert (e.periodo_inicio, e.periodo_fin) == (date(2026, 8, 1), date(2026, 8, 31))
    assert [m.sentido for m in e.movimientos] == ["abono", "abono", "abono", "cargo", "abono", "abono", "abono", "cargo"]
    assert [m.clase for m in e.movimientos] == [s.MISMO_BANCO, s.SPEI, s.EFECTIVO, s.OTRO, s.MISMO_BANCO, s.SPEI, s.DEVOLUCION, s.OTRO]


def test_spei_trae_todos_los_datos_aunque_lo_parta_un_salto_de_pagina():
    spei = s.leer(estado()[0]).movimientos[1]
    assert spei.fecha == date(2026, 8, 3) and spei.folio == "1000002" and spei.importe == 100000 and spei.hora == "10:53:26"
    assert spei.banco_origen == "BANCO UNO" and spei.cuenta_pagador == "002010077777777771"
    assert spei.nombre_pagador == "PERSONA FICTICIA UNO" and spei.rastreo == "ABC123456789"
    assert spei.referencia == "0260803" and spei.concepto == "colegiatura hijo" and spei.rfc == "XAXX010101000"
    assert s.leer(estado(saltos=False)[0]).movimientos[1] == spei


def test_concepto_vacio_y_referencia_con_matricula():
    spei = s.leer(estado()[0]).movimientos[5]
    assert spei.referencia == "4829173" and spei.concepto == "" and spei.nombre_pagador == "PERSONA,FICTICIA/DOS"


def test_mismo_banco_solo_trae_el_texto_libre_unido():
    e = s.leer(estado()[0])
    enlace, rapida = e.movimientos[0], e.movimientos[4]
    assert enlace.concepto == "colegiatura 4829173 de agosto" and enlace.referencia == "" and enlace.cuenta_pagador == ""
    assert rapida.concepto == "Transferencia a NEGOCIO"


def test_efectivo_devolucion_y_cargos_no_traen_datos_de_pagador():
    e = s.leer(estado()[0])
    efectivo, devolucion, cargo = e.movimientos[2], e.movimientos[6], e.movimientos[7]
    assert efectivo.es_cobro_posible and not efectivo.concepto and not efectivo.referencia
    assert not devolucion.es_cobro_posible and not cargo.es_cobro_posible
    assert cargo.referencia == "" and cargo.cuenta_pagador == "" and cargo.concepto == ""


def test_solo_lee_la_primera_seccion():
    assert len(s.leer(estado()[0]).movimientos) == 8


def test_importe_alterado_se_rechaza():
    lineas = estado()[0]
    i = next(i for i, l in enumerate(lineas) if "1000003" in l)
    lineas[i] = lineas[i].replace("500.00", "900.00", 1)
    with pytest.raises(s.ErrorEstado) as error:
        s.leer(lineas)
    assert error.value.codigo == "descuadre"


def test_movimiento_faltante_se_rechaza():
    lineas = [l for l in estado()[0] if "1000003" not in l]
    with pytest.raises(s.ErrorEstado) as error:
        s.leer(lineas)
    assert error.value.codigo == "descuadre"


def test_total_alterado_se_rechaza():
    lineas = estado()[0]
    i = next(i for i, l in enumerate(lineas) if l.strip().startswith("TOTAL"))
    lineas[i] = lineas[i].replace("6,030.00", "6,031.00")
    with pytest.raises(s.ErrorEstado) as error:
        s.leer(lineas)
    assert error.value.codigo == "descuadre"


def test_archivo_que_no_es_un_estado_de_cuenta():
    for lineas in ([], ["hola"], ["x"] * 50, estado()[0][:12]):
        with pytest.raises(s.ErrorEstado) as error:
            s.leer(lineas)
        assert error.value.codigo == "formato"


def test_estado_truncado_sin_saldo_final():
    lineas = estado()[0]
    corte = next(i for i, l in enumerate(lineas) if "SALDO FINAL DEL PERIODO:" in l)
    with pytest.raises(s.ErrorEstado):
        s.leer(lineas[:corte])


def test_huellas_distintas_por_movimiento_y_estables():
    e = s.leer(estado()[0])
    huellas = [s.huella(e.clabe, m, i) for i, m in enumerate(e.movimientos)]
    assert len(set(huellas)) == len(huellas)
    assert huellas == [s.huella(e.clabe, m, i) for i, m in enumerate(s.leer(estado()[0]).movimientos)]


def test_centavos():
    assert s.centavos("1,300.00") == 130000 and s.centavos("0.05") == 5 and s.centavos("1,234,567.89") == 123456789
