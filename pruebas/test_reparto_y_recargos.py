import random
from datetime import date, timedelta

import pytest

from nucleo import recargos as r
from nucleo.reparto import ErrorReparto, Pendiente, repartir

D = date(2026, 11, 10)


def p(id, titular, saldo, dias=0, recargo=False, prioridad=100):
    return Pendiente(id, titular, saldo, D + timedelta(days=dias), recargo, prioridad)


def test_pago_exacto_de_un_cargo():
    partes, resto = repartir(150000, [p(1, 7, 150000)], 7)
    assert [(x.cargo, x.importe) for x in partes] == [(1, 150000)] and resto == 0


def test_recargo_antes_que_el_cargo_base_y_luego_el_mas_antiguo():
    pendientes = [p(1, 7, 100000, dias=0), p(2, 7, 100000, dias=-30), p(3, 7, 5000, dias=5, recargo=True)]
    partes, resto = repartir(120000, pendientes, 7)
    assert [(x.cargo, x.importe) for x in partes] == [(3, 5000), (2, 100000), (1, 15000)] and resto == 0


def test_prioridad_desempata_mismo_vencimiento():
    partes, _ = repartir(100, [p(1, 7, 100, prioridad=50), p(2, 7, 100, prioridad=10)], 7)
    assert partes[0].cargo == 2


def test_lo_que_sobra_pasa_a_los_hermanos_y_solo_despues_es_saldo_a_favor():
    pendientes = [p(1, 7, 100000), p(2, 8, 80000, dias=-10), p(3, 9, 50000, dias=-20)]
    partes, resto = repartir(200000, pendientes, 7, miembros=[7, 8, 9])
    assert [(x.cargo, x.titular, x.importe) for x in partes] == [(1, 7, 100000), (3, 9, 50000), (2, 8, 50000)]
    assert resto == 0
    partes, resto = repartir(250000, pendientes, 7, miembros=[8, 9])
    assert sum(x.importe for x in partes) == 230000 and resto == 20000


def test_primero_todo_lo_del_titular_aunque_el_hermano_deba_algo_mas_antiguo():
    pendientes = [p(1, 7, 100, dias=30), p(2, 8, 100, dias=-300, recargo=True)]
    partes, _ = repartir(100, pendientes, 7, miembros=[8])
    assert [(x.cargo) for x in partes] == [1]


def test_sin_familia_no_toca_cargos_de_otros():
    partes, resto = repartir(500, [p(1, 7, 100), p(2, 8, 100)], 7)
    assert [(x.cargo, x.importe) for x in partes] == [(1, 100)] and resto == 400


def test_errores():
    for malo in (0, -5, 10.5, True, "100"):
        with pytest.raises(ErrorReparto):
            repartir(malo, [p(1, 7, 100)], 7)
    with pytest.raises(ErrorReparto):
        repartir(100, [p(1, 7, 100), p(1, 7, 50)], 7)
    with pytest.raises(ErrorReparto):
        repartir(100, [p(1, 7, -1)], 7)
    with pytest.raises(ErrorReparto):
        repartir(100, [p(1, 7, 100)], 7, orden=("recargos", "otro"))


def test_invariantes_con_datos_al_azar():
    azar = random.Random(2026)
    for _ in range(3000):
        titulares = list(range(1, azar.randint(2, 6)))
        objetivo = azar.choice(titulares)
        miembros = [t for t in titulares if azar.random() < 0.6]
        pendientes = [
            Pendiente(i, azar.choice(titulares), azar.choice([0, azar.randint(1, 300000)]), D + timedelta(days=azar.randint(-200, 60)), azar.random() < 0.2, azar.choice([10, 50, 100]))
            for i in range(1, azar.randint(1, 15))
        ]
        importe = azar.randint(1, 900000)
        partes, resto = repartir(importe, pendientes, objetivo, miembros)
        saldos = {x.id: x for x in pendientes}
        familia = set(miembros) | {objetivo}
        assert sum(x.importe for x in partes) + resto == importe
        assert resto >= 0
        assert len({x.cargo for x in partes}) == len(partes)
        for parte in partes:
            assert 0 < parte.importe <= saldos[parte.cargo].saldo
            assert saldos[parte.cargo].titular in familia
        pendiente_familia = sum(x.saldo for x in pendientes if x.titular in familia)
        assert sum(x.importe for x in partes) == min(importe, pendiente_familia)
        if resto > 0:
            assert sum(x.importe for x in partes) == pendiente_familia
        propios = sum(x.saldo for x in pendientes if x.titular == objetivo)
        aplicado_propio = sum(x.importe for x in partes if x.titular == objetivo)
        assert aplicado_propio == min(importe, propios)


def test_sumar_meses_respeta_fin_de_mes():
    assert r.sumar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert r.sumar_meses(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert r.sumar_meses(date(2026, 11, 15), 2) == date(2027, 1, 15)
    assert r.fecha_en_mes(2026, 2, 31) == date(2026, 2, 28)


def test_fechas_de_recargo():
    v = date(2026, 11, 10)
    assert r.fechas_de_recargo(v, date(2026, 11, 10)) == []
    assert r.fechas_de_recargo(v, date(2026, 11, 11)) == [date(2026, 11, 11)]
    assert r.fechas_de_recargo(v, date(2026, 11, 13), dias_gracia=3) == []
    assert r.fechas_de_recargo(v, date(2026, 11, 14), dias_gracia=3) == [date(2026, 11, 14)]
    assert r.fechas_de_recargo(v, date(2027, 2, 1)) == [date(2026, 11, 11)]
    assert r.fechas_de_recargo(v, date(2027, 1, 11), se_repite=True) == [date(2026, 11, 11), date(2026, 12, 11), date(2027, 1, 11)]


def test_prorroga_mueve_el_inicio_y_no_puede_adelantarlo():
    v = date(2026, 11, 10)
    assert r.fechas_de_recargo(v, date(2026, 11, 25), prorroga_hasta=date(2026, 11, 25)) == []
    assert r.fechas_de_recargo(v, date(2026, 11, 26), prorroga_hasta=date(2026, 11, 25)) == [date(2026, 11, 26)]
    assert r.fechas_de_recargo(v, date(2026, 11, 11), prorroga_hasta=date(2026, 11, 1)) == [date(2026, 11, 11)]


def test_importes_de_recargo_y_tope():
    assert r.importe_recargo("fijo", 10000, 150000) == 10000
    assert r.importe_recargo("porcentaje", 500, 150000) == 7500
    assert r.importe_recargo("porcentaje", 333, 100001) == 3330
    assert r.importe_recargo("porcentaje", 250, 30) == 1
    assert r.importe_recargo("fijo", 10000, 0) == 0
    assert r.importe_recargo("fijo", 10000, 150000, acumulado=25000, tope=30000) == 5000
    assert r.importe_recargo("fijo", 10000, 150000, acumulado=30000, tope=30000) == 0
    with pytest.raises(r.ErrorRecargo):
        r.importe_recargo("otro", 1, 1)


def test_recargos_pendientes_se_pone_al_dia_sin_duplicar():
    v = date(2026, 9, 10)
    hoy = date(2026, 12, 15)
    todos = r.recargos_pendientes("fijo", 10000, 150000, v, hoy, se_repite=True)
    assert todos == [(date(2026, 9, 11), 10000), (date(2026, 10, 11), 10000), (date(2026, 11, 11), 10000), (date(2026, 12, 11), 10000)]
    faltan = r.recargos_pendientes("fijo", 10000, 150000, v, hoy, ya_generadas=[date(2026, 9, 11), date(2026, 10, 11)], acumulado=20000, se_repite=True)
    assert faltan == [(date(2026, 11, 11), 10000), (date(2026, 12, 11), 10000)]
    assert r.recargos_pendientes("fijo", 10000, 150000, v, hoy, ya_generadas=[f for f, _ in todos], acumulado=40000, se_repite=True) == []
    con_tope = r.recargos_pendientes("fijo", 10000, 150000, v, hoy, se_repite=True, tope=25000)
    assert con_tope == [(date(2026, 9, 11), 10000), (date(2026, 10, 11), 10000), (date(2026, 11, 11), 5000)]
    assert r.recargos_pendientes("fijo", 10000, 0, v, hoy, se_repite=True) == []


def test_beca():
    assert r.importe_con_beca(150000) == (150000, 0)
    assert r.importe_con_beca(150000, "porcentaje", 2500) == (112500, 37500)
    assert r.importe_con_beca(150000, "fijo", 20000) == (130000, 20000)
    assert r.importe_con_beca(150000, "fijo", 999999) == (0, 150000)
    assert r.importe_con_beca(99999, "porcentaje", 3333) == (66669, 33330)
    with pytest.raises(r.ErrorRecargo):
        r.importe_con_beca(100, "porcentaje", 10001)
