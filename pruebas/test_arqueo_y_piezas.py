import re

import pytest
from django.urls import reverse

from auditoria.models import Evento
from caja import piezas as control_piezas
from caja import servicios as caja
from caja.models import Arqueo, Caja, ConteoArqueo, MovimientoPiezas, RegistroInmutable, Turno
from cobros import libro
from cobros.models import Pago
from configuracion.models import Parametro
from cortes.models import DIARIO, Corte

from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo, turno_de, verificar_sumas


@pytest.fixture
def base(personas):
    preparar_conceptos()
    return personas, titular_activo(personas["op"], personas["sup"], "Ana")


def encender():
    Parametro.objects.update_or_create(clave="control_denominaciones", defaults={"valor": "1"})


def textos_de(centavos):
    pesos, resto = divmod(centavos, 100)
    return {f"{pesos:,}.{resto:02d}", f"{pesos}.{resto:02d}", str(centavos)}


def sin_esperado(texto, esperado):
    return not any(t in texto for t in textos_de(esperado))


def test_conteo_que_coincide_cierra_y_revela(base):
    personas, ana = base
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 15000, Pago.EFECTIVO, personas["op"], turno=turno)
    op = cliente(personas["op"])
    respuesta = op.post(reverse("caja:cerrar", args=[turno.pk]), {"d_10000": 1, "d_5000": 1})
    assert respuesta.url == reverse("caja:turno", args=[turno.pk])
    arqueo = Arqueo.objects.get()
    assert (arqueo.contado, arqueo.esperado, arqueo.diferencia, arqueo.con_reconteo, arqueo.primer_contado) == (15000, 15000, 0, False, 15000)
    assert "150.00" in op.get(respuesta.url).content.decode()


def test_no_coincide_solo_lo_dice_y_admite_un_reconteo(base):
    personas, ana = base
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 123456, Pago.EFECTIVO, personas["op"], turno=turno)
    op = cliente(personas["op"])
    primera = op.post(reverse("caja:cerrar", args=[turno.pk]), {"d_100000": 1})
    assert primera.url == reverse("caja:reconteo", args=[turno.pk])
    pagina = op.get(primera.url).content.decode()
    assert "no coincide" in pagina and sin_esperado(pagina, 123456) and sin_esperado(pagina, 23456)
    for palabra in ("sobra", "falta", "Faltan", "Sobran", "Esperado", "Debe haber"):
        assert palabra not in pagina
    primero = ConteoArqueo.objects.get(turno=turno)
    assert (primero.numero, primero.contado) == (1, 100000)
    primero.contado = 123456
    with pytest.raises(RegistroInmutable):
        primero.save()
    with pytest.raises(RegistroInmutable):
        ConteoArqueo.objects.filter(pk=primero.pk).update(contado=123456)
    with pytest.raises(RegistroInmutable):
        primero.delete()
    assert op.post(reverse("caja:cerrar", args=[turno.pk]), {"d_100000": 2}).url == reverse("caja:reconteo", args=[turno.pk])
    assert ConteoArqueo.objects.filter(turno=turno).count() == 1
    sin_nota = op.post(reverse("caja:reconteo", args=[turno.pk]), {"accion": "reconteo", "d_100000": 1, "d_20000": 1})
    assert sin_nota.status_code == 200 and sin_esperado(sin_nota.content.decode(), 123456)
    assert ConteoArqueo.objects.filter(turno=turno).count() == 1
    with pytest.raises(caja.NotaRequerida):
        caja.reconteo(turno, personas["op"], {"100000": 1}, "")
    final = op.post(reverse("caja:reconteo", args=[turno.pk]), {"accion": "reconteo", "d_100000": 1, "d_20000": 1, "nota": "Recontado"})
    assert final.url == reverse("caja:turno", args=[turno.pk])
    arqueo = Arqueo.objects.get()
    assert (arqueo.primer_contado, arqueo.contado, arqueo.esperado, arqueo.con_reconteo) == (100000, 120000, 123456, True)
    assert op.post(reverse("caja:reconteo", args=[turno.pk]), {"accion": "reconteo", "d_100000": 2, "nota": "otra"}).url == reverse("caja:turno", args=[turno.pk])
    with pytest.raises(caja.ErrorCaja):
        caja.reconteo(turno, personas["op"], {"100000": 2}, "otra vez")
    assert ConteoArqueo.objects.filter(turno=turno).count() == 2 and Arqueo.objects.count() == 1
    revelado = op.get(final.url).content.decode()
    assert "1,234.56" in revelado and "1,000.00" in revelado
    evento = Evento.objects.get(accion="primer_conteo")
    assert evento.datos["coincide"] is False and "esperado" not in evento.datos
    cierre = Evento.objects.get(accion="turno_cerrado")
    assert cierre.datos["primer_contado"] == 100000 and cierre.datos["contado"] == 120000 and cierre.datos["esperado"] == 123456
    corte = Corte.objects.get(tipo=DIARIO)
    assert corte.cifras["totales"]["con_reconteo"] and corte.cifras["totales"]["primer_contado"] == 100000


def test_cerrar_con_el_primer_conteo_pide_nota(base):
    personas, ana = base
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 50000, Pago.EFECTIVO, personas["op"], turno=turno)
    resultado = caja.primer_conteo(turno, personas["op"], {"20000": 1})
    assert not resultado.cerrado
    with pytest.raises(caja.NotaRequerida):
        caja.cerrar_con_primer_conteo(turno, personas["op"], "  ")
    arqueo = caja.cerrar_con_primer_conteo(turno, personas["op"], "Faltó")
    assert (arqueo.contado, arqueo.diferencia, arqueo.con_reconteo, arqueo.nota) == (20000, -30000, False, "Faltó")


def test_solo_quien_tiene_el_turno_lo_cuenta(base):
    personas, ana = base
    turno = turno_de(personas["op"])
    assert cliente(personas["op2"]).post(reverse("caja:cerrar", args=[turno.pk]), {"d_100": 1}).status_code == 403
    assert cliente(personas["sup"]).get(reverse("caja:reconteo", args=[turno.pk])).status_code == 403
    with pytest.raises(caja.ErrorCaja):
        caja.primer_conteo(turno, personas["op2"], {})
    assert not ConteoArqueo.objects.exists()


def test_turno_en_arqueo_no_recibe_movimientos(base):
    personas, ana = base
    turno = turno_de(personas["op"])
    pago = libro.registrar_pago(ana, 50000, Pago.EFECTIVO, personas["op"], turno=turno)
    caja.primer_conteo(turno, personas["op"], {"100": 1})
    with pytest.raises(libro.ErrorLibro):
        libro.registrar_pago(ana, 100, Pago.EFECTIVO, personas["op"], turno=turno)
    with pytest.raises(libro.ErrorLibro):
        libro.revertir_pago(pago, "x", personas["sup"], turno=turno)
    op = cliente(personas["op"])
    assert op.post(reverse("cobros:cobrar", args=[ana.pk]), {"importe": "10"}).url == reverse("caja:inicio")
    assert "en arqueo" in op.get(reverse("caja:inicio")).content.decode()
    assert Pago.objects.count() == 1


def _turno_con_piezas(personas, fondo):
    encender()
    caja_ = Caja.objects.get_or_create(nombre="Caja 1")[0]
    datos = {"caja": caja_.pk}
    datos.update({f"f_{valor}": cantidad for valor, cantidad in fondo.items()})
    op = cliente(personas["op"])
    op.post(reverse("caja:abrir"), datos)
    return op, Turno.objects.get(usuario=personas["op"], estado=Turno.ABIERTO)


def _cobrar(c, titular, importe, recibidas):
    vista = c.post(reverse("cobros:cobrar", args=[titular.pk]), {"importe": importe})
    texto = vista.content.decode()
    ficha = re.search(r'name="ficha" value="([^"]+)"', texto).group(1)
    centavos = re.search(r'name="importe" value="(\d+)"', texto).group(1)
    datos = {"paso": "cambio", "ficha": ficha, "importe": centavos}
    datos.update({f"r_{valor}": cantidad for valor, cantidad in recibidas.items()})
    return c.post(reverse("cobros:cobrar", args=[titular.pk]), datos), ficha, centavos


def _propuesta(texto):
    return {int(v): int(c) for v, c in re.findall(r'name="c_(\d+)" value="(\d+)"', texto) if int(c)}


def test_apertura_con_piezas(base):
    personas, ana = base
    op, turno = _turno_con_piezas(personas, {10000: 2, 5000: 1, 2000: 3})
    assert turno.fondo_inicial == 31000
    assert control_piezas.existencias(turno) == {"10000": 2, "5000": 1, "2000": 3}
    assert 'name="fondo_inicial"' not in cliente(personas["op2"]).get(reverse("caja:inicio")).content.decode()


def test_cobro_con_cambio_propuesto_y_cierre_por_denominacion(base):
    personas, ana = base
    op, turno = _turno_con_piezas(personas, {10000: 2, 5000: 2, 2000: 5})
    respuesta, ficha, centavos = _cobrar(op, ana, "130", {20000: 1})
    texto = respuesta.content.decode()
    assert "70.00" in texto and _propuesta(texto) == {5000: 1, 2000: 1}
    datos = {"paso": "confirmar", "ficha": ficha, "importe": centavos, "r_20000": 1, "c_5000": 1, "c_2000": 1}
    assert op.post(reverse("cobros:cobrar", args=[ana.pk]), datos).status_code == 302
    pago = Pago.objects.get()
    movimientos = {(m.origen, m.denominacion, m.piezas) for m in MovimientoPiezas.objects.filter(pago=pago)}
    assert movimientos == {("recibido", 20000, 1), ("cambio", 5000, -1), ("cambio", 2000, -1)}
    assert control_piezas.existencias(turno) == {"20000": 1, "10000": 2, "5000": 1, "2000": 4}
    conteo = {"d_20000": 1, "d_10000": 2, "d_5000": 1, "d_2000": 4}
    assert op.post(reverse("caja:cerrar", args=[turno.pk]), conteo).url == reverse("caja:turno", args=[turno.pk])
    pagina = op.get(reverse("caja:turno", args=[turno.pk])).content.decode()
    assert "Debe haber" in pagina
    arqueo = Arqueo.objects.get()
    assert arqueo.esperado_piezas == {"20000": 1, "10000": 2, "5000": 1, "2000": 4} and arqueo.diferencia == 0
    secciones = {s["clave"]: s["filas"] for s in Corte.objects.get(tipo=DIARIO).cifras["secciones"]}
    assert {f["denominacion"]: f["esperadas"] for f in secciones["piezas"]} == {20000: 1, 10000: 2, 5000: 1, 2000: 4}
    verificar_sumas()


def test_cambio_capturado_debe_sumar_exacto_y_recibido_alcanzar(base):
    personas, ana = base
    op, turno = _turno_con_piezas(personas, {5000: 2, 2000: 5})
    corto, ficha, centavos = _cobrar(op, ana, "130", {10000: 1})
    assert "no alcanzan" in corto.content.decode() and not Pago.objects.exists()
    _, ficha, centavos = _cobrar(op, ana, "130", {20000: 1})
    malo = op.post(reverse("cobros:cobrar", args=[ana.pk]), {"paso": "confirmar", "ficha": ficha, "importe": centavos, "r_20000": 1, "c_5000": 1})
    assert malo.status_code == 200 and "exactamente" in malo.content.decode() and not Pago.objects.exists()
    otro = op.post(reverse("cobros:cobrar", args=[ana.pk]), {"paso": "confirmar", "ficha": ficha, "importe": centavos, "r_20000": 1, "c_2000": 2, "c_1000": 3})
    assert otro.status_code == 302 and Pago.objects.count() == 1
    with pytest.raises(libro.ErrorLibro):
        libro.registrar_pago(ana, 100, Pago.EFECTIVO, personas["op"], turno=turno, piezas={"recibidas": {"7": 1}, "cambio": {}})


def test_sin_combinacion_exacta_lo_dice_y_no_bloquea(base):
    personas, ana = base
    op, turno = _turno_con_piezas(personas, {5000: 1})
    respuesta, ficha, centavos = _cobrar(op, ana, "130", {20000: 1})
    texto = respuesta.content.decode()
    assert "no tiene las piezas" in texto and _propuesta(texto) == {}
    datos = {"paso": "confirmar", "ficha": ficha, "importe": centavos, "r_20000": 1, "c_5000": 1, "c_2000": 1}
    assert op.post(reverse("cobros:cobrar", args=[ana.pk]), datos).status_code == 302
    assert control_piezas.existencias(turno)["2000"] == -1


def test_propuestas_de_cambio_sin_cobro_se_limitan(base):
    personas, ana = base
    Parametro.objects.create(clave="propuestas_cambio_sin_cobro", valor="2")
    op, turno = _turno_con_piezas(personas, {5000: 4, 2000: 5})
    for _ in range(2):
        assert _propuesta(_cobrar(op, ana, "130", {20000: 1})[0].content.decode()) == {5000: 1, 2000: 1}
    tercera = _cobrar(op, ana, "130", {20000: 1})[0].content.decode()
    assert _propuesta(tercera) == {} and "Captura las piezas" in tercera
    assert Evento.objects.filter(accion="propuesta_cambio_limitada").exists()


def test_devolucion_con_piezas(base):
    personas, ana = base
    op, turno = _turno_con_piezas(personas, {5000: 2})
    pago = libro.registrar_pago(ana, 20000, Pago.EFECTIVO, personas["op"], turno=turno, piezas={"recibidas": {"20000": 1}, "cambio": {}})
    sup = cliente(personas["sup"])
    caja_2 = Caja.objects.create(nombre="Caja 2")
    sup.post(reverse("caja:abrir"), {"caja": caja_2.pk, "f_20000": 1})
    turno_sup = caja.turno_abierto(personas["sup"])
    libro.registrar_pago(ana, 30000, Pago.EFECTIVO, personas["sup"], turno=turno_sup, piezas={"recibidas": {"20000": 1, "10000": 1}, "cambio": {}})
    pagina = sup.post(reverse("cobros:revertir", args=[pago.pk]), {"motivo": "error", "p_20000": 2})
    assert pagina.status_code == 200 and "exactamente" in pagina.content.decode()
    sup.post(reverse("cobros:revertir", args=[pago.pk]), {"motivo": "error", "p_20000": 1})
    assert MovimientoPiezas.objects.filter(origen="devolucion", turno=turno_sup, denominacion=20000, piezas=-1).exists()


def test_supervision_con_turno_abierto_no_ve_su_propio_esperado(base):
    personas, ana = base
    sup = personas["sup"]
    turno = turno_de(sup, "Caja 2")
    libro.registrar_pago(ana, 123456, Pago.EFECTIVO, sup, turno=turno)
    otro = turno_de(personas["op"])
    libro.registrar_pago(ana, 777700, Pago.EFECTIVO, personas["op"], turno=otro)
    c = cliente(sup)
    for url in (reverse("caja:custodia"), reverse("inicio"), reverse("caja:inicio"), reverse("caja:turno", args=[turno.pk]), reverse("caja:cerrar", args=[turno.pk]), reverse("cortes:lista"), reverse("caja:retiros")):
        texto = c.get(url).content.decode()
        assert sin_esperado(texto, 123456), url
    assert "7,777.00" in c.get(reverse("caja:custodia")).content.decode()


def test_mensajes_de_devolucion_no_revelan_lo_cobrado_del_turno(base):
    personas, ana = base
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 123456, Pago.EFECTIVO, personas["op"], turno=turno)
    otro = libro.registrar_pago(ana, 900000, Pago.EFECTIVO, personas["op"], turno=turno)
    caja.cerrar_turno(turno, personas["op"], {"100000": 10, "20000": 1, "2000": 1, "200": 1, "50": 1, "100": 1}, "conteo")
    nuevo = turno_de(personas["op"])
    libro.registrar_pago(ana, 123456, Pago.EFECTIVO, personas["op"], turno=nuevo)
    with pytest.raises(libro.ErrorLibro) as error:
        libro.revertir_pago(otro, "error", personas["sup"], turno=nuevo)
    assert sin_esperado(str(error.value), 123456) and "9,000.00" in str(error.value)
