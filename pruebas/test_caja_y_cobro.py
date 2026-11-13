import re

import pytest
from django.urls import reverse

from banco.models import Banco, CuentaBancaria
from caja.models import Arqueo, Caja, Traslado, Turno
from caja.servicios import ErrorCaja, cerrar_turno, custodia, disponible_para_trasladar
from cobros import libro
from cobros.models import Pago, Recibo
from configuracion.models import Parametro
from solicitudes.models import Solicitud

from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo, turno_de, verificar_sumas


@pytest.fixture
def caja(personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    return personas, ana


def cobrar(c, titular, importe):
    vista = c.post(reverse("cobros:cobrar", args=[titular.pk]), {"importe": importe})
    texto = vista.content.decode()
    ficha = re.search(r'name="ficha" value="([^"]+)"', texto)
    centavos = re.search(r'name="importe" value="(\d+)"', texto)
    return vista, (ficha.group(1) if ficha else None), (centavos.group(1) if centavos else None)


def confirmar(c, titular, ficha, centavos):
    return c.post(reverse("cobros:cobrar", args=[titular.pk]), {"paso": "confirmar", "ficha": ficha, "importe": centavos})


def test_cobro_con_vista_previa_y_doble_envio(caja):
    personas, ana = caja
    op = cliente(personas["op"])
    assert op.post(reverse("cobros:cobrar", args=[ana.pk]), {"importe": "100"}).url == reverse("caja:inicio")
    op.post(reverse("caja:abrir"), {"caja": _caja_libre(), "fondo_inicial": "0"})
    assert Turno.objects.filter(usuario=personas["op"], estado=Turno.ABIERTO).exists()
    vista, ficha, centavos = cobrar(op, ana, "1,200.50")
    assert "Inscripción" in vista.content.decode() and "Queda a favor" in vista.content.decode()
    assert not Pago.objects.exists() and centavos == "120050"
    primera = confirmar(op, ana, ficha, centavos)
    segunda = confirmar(op, ana, ficha, centavos)
    assert Pago.objects.count() == 1 and primera.url == segunda.url
    recibo = Recibo.objects.get()
    assert primera.url == reverse("cobros:recibo", args=[recibo.pk])
    pagina = op.get(primera.url).content.decode()
    assert recibo.codigo in pagina and "1,200.50" in pagina
    pdf = op.get(reverse("cobros:recibo_pdf", args=[recibo.pk]))
    assert pdf["Content-Type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    verificar_sumas()


def _caja_libre():
    return Caja.objects.get_or_create(nombre="Caja 1")[0].pk


@pytest.mark.parametrize("importe", ["0", "-1", "1.234", "abc", "", "1e5", "99999999999999"])
def test_importes_invalidos_en_el_cobro(caja, importe):
    personas, ana = caja
    turno_de(personas["op"])
    vista, ficha, _ = cobrar(cliente(personas["op"]), ana, importe)
    assert vista.status_code == 200 and ficha is None and not Pago.objects.exists()


def test_confirmacion_manipulada_rechazada(caja):
    personas, ana = caja
    turno_de(personas["op"])
    op = cliente(personas["op"])
    for ficha, centavos in (("corta", "100"), ("x" * 20, "-5"), ("x" * 20, "abc"), ("x" * 20, "0"), ("../../etc" + "x" * 20, "100")):
        confirmar(op, ana, ficha, centavos)
    assert not Pago.objects.exists()


def test_pago_sobre_tope_requiere_autorizacion(caja):
    personas, ana = caja
    Parametro.objects.create(clave="tope_pago_individual", valor="100000")
    turno = turno_de(personas["op"])
    op = cliente(personas["op"])
    vista, ficha, centavos = cobrar(op, ana, "2000")
    assert "necesitará autorización" in vista.content.decode()
    respuesta = confirmar(op, ana, ficha, centavos)
    solicitud = Solicitud.objects.get(accion="pago_sobre_tope")
    assert respuesta.url == reverse("solicitudes:detalle", args=[solicitud.pk]) and not Pago.objects.exists()
    cliente(personas["sup"]).post(reverse("solicitudes:aprobar", args=[solicitud.pk]))
    pago = Pago.objects.get()
    assert pago.turno == turno and pago.registrado_por == personas["op"] and pago.importe == 200000 and pago.solicitud == solicitud
    assert confirmar(op, ana, ficha, centavos).url == reverse("cobros:recibo", args=[pago.recibo.pk])
    assert Pago.objects.count() == 1


def test_verificar_recibo(caja):
    personas, ana = caja
    pago = libro.registrar_pago(ana, 5000, Pago.EFECTIVO, personas["op"], turno=turno_de(personas["op"]))
    recibo = pago.recibo
    c = cliente(personas["op"])
    bueno = c.get(reverse("cobros:verificar"), {"folio": f"{recibo.serie}-{recibo.folio}", "codigo": recibo.codigo.lower()}).content.decode()
    assert "Recibo auténtico" in bueno
    malo = c.get(reverse("cobros:verificar"), {"folio": f"{recibo.serie}-{recibo.folio}", "codigo": "AAAAA-AAAAA"}).content.decode()
    assert "no corresponden" in malo
    otro = c.get(reverse("cobros:verificar"), {"folio": f"{recibo.serie}-99", "codigo": recibo.codigo}).content.decode()
    assert "no corresponden" in otro
    assert libro.recibo_valido(recibo)


def test_arqueo_ciego(caja):
    personas, ana = caja
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 123456, Pago.EFECTIVO, personas["op"], turno=turno)
    op = cliente(personas["op"])
    for pagina in (reverse("caja:inicio"), reverse("caja:cerrar", args=[turno.pk]), reverse("caja:turno", args=[turno.pk])):
        texto = op.get(pagina).content.decode()
        assert "1,234.56" not in texto and "123456" not in texto, pagina
    supervisor = cliente(personas["sup"])
    texto = supervisor.get(reverse("caja:turno", args=[turno.pk])).content.decode()
    assert "1,234.56" not in texto
    assert supervisor.get(reverse("caja:cerrar", args=[turno.pk])).status_code == 403
    respuesta = op.post(reverse("caja:cerrar", args=[turno.pk]), {"d_100000": 1})
    assert respuesta.status_code == 200 and "supera el umbral" in respuesta.content.decode()
    assert "1,234.56" not in respuesta.content.decode()
    turno.refresh_from_db()
    assert turno.abierto
    op.post(reverse("caja:cerrar", args=[turno.pk]), {"d_100000": 1, "nota": "Faltó dinero"})
    arqueo = Arqueo.objects.get()
    assert (arqueo.contado, arqueo.esperado, arqueo.diferencia, arqueo.supera_umbral) == (100000, 123456, -23456, True)
    assert "1,234.56" in op.get(reverse("caja:turno", args=[turno.pk])).content.decode()
    assert "Diferencia de arqueo" in supervisor.get(reverse("inicio")).content.decode()
    with pytest.raises(ErrorCaja):
        cerrar_turno(turno, personas["op"], {"100000": 1}, "otra vez")
    assert Arqueo.objects.count() == 1


def test_entrega_con_doble_firma_y_custodia(caja):
    personas, ana = caja
    op, sup, direccion = personas["op"], personas["sup"], personas["dir"]
    turno = turno_de(op)
    libro.registrar_pago(ana, 150000, Pago.EFECTIVO, op, turno=turno)
    assert custodia(op) == 150000 and disponible_para_trasladar(op) == 0
    c_op = cliente(op)
    respuesta = c_op.post(reverse("caja:entrega"), {"destino": sup.pk, "importe": "1000"})
    assert respuesta.status_code == 200 and not Traslado.objects.exists()
    cerrar_turno(turno, op, {"100000": 1, "50000": 1})
    c_op.post(reverse("caja:entrega"), {"destino": sup.pk, "importe": "1000"})
    entrega = Traslado.objects.get()
    assert entrega.estado == Traslado.PENDIENTE and custodia(op) == 150000 and disponible_para_trasladar(op) == 50000
    assert c_op.post(reverse("caja:confirmar", args=[entrega.pk]), {"importe": "1000"}).status_code == 403
    assert cliente(direccion).post(reverse("caja:confirmar", args=[entrega.pk]), {"importe": "1000"}).status_code == 403
    c_sup = cliente(sup)
    c_sup.post(reverse("caja:confirmar", args=[entrega.pk]), {"importe": "999"})
    entrega.refresh_from_db()
    assert entrega.estado == Traslado.PENDIENTE
    c_sup.post(reverse("caja:confirmar", args=[entrega.pk]), {"importe": "1000"})
    c_sup.post(reverse("caja:confirmar", args=[entrega.pk]), {"importe": "1000"})
    entrega.refresh_from_db()
    assert entrega.estado == Traslado.CONFIRMADO
    assert custodia(op) == 50000 and custodia(sup) == 100000
    cuenta = CuentaBancaria.objects.create(banco=Banco.objects.get(clave="002"), clabe="002010077777777771", beneficiario="B", principal=True)
    c_sup.post(reverse("caja:deposito"), {"cuenta": cuenta.pk, "importe": "600", "fecha": "2026-01-15", "referencia": "DEP1"})
    deposito = Traslado.objects.get(tipo=Traslado.DEPOSITO)
    assert deposito.estado == Traslado.POR_CONCILIAR and custodia(sup) == 40000
    assert c_sup.post(reverse("caja:deposito"), {"cuenta": cuenta.pk, "importe": "500", "fecha": "2026-01-15", "referencia": "DEP2"}).status_code == 200
    assert Traslado.objects.filter(tipo=Traslado.DEPOSITO).count() == 1
    c_op.post(reverse("caja:entrega"), {"destino": sup.pk, "importe": "500"})
    otra = Traslado.objects.filter(estado=Traslado.PENDIENTE).get()
    c_sup.post(reverse("caja:rechazar", args=[otra.pk]), {"nota": "No llegó"})
    otra.refresh_from_db()
    assert otra.estado == Traslado.RECHAZADO and custodia(op) == 50000
    personas_custodia = cliente(sup).get(reverse("caja:custodia")).content.decode()
    assert "500.00" in personas_custodia and "400.00" in personas_custodia
    verificar_sumas()


def test_nadie_se_entrega_a_si_mismo(caja):
    personas, ana = caja
    sup = personas["sup"]
    turno = turno_de(sup)
    libro.registrar_pago(ana, 10000, Pago.EFECTIVO, sup, turno=turno)
    cerrar_turno(turno, sup, {"10000": 1})
    respuesta = cliente(sup).post(reverse("caja:entrega"), {"destino": sup.pk, "importe": "10"})
    assert respuesta.status_code == 200 and not Traslado.objects.exists()


def test_un_turno_por_persona_y_por_caja(caja):
    personas, ana = caja
    turno = turno_de(personas["op"])
    with pytest.raises(ErrorCaja):
        turno_de(personas["op"], "Otra caja")
    with pytest.raises(ErrorCaja):
        turno_de(personas["op2"], turno.caja.nombre)
