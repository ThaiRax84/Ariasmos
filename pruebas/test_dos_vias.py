from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from banco import conciliacion
from banco.models import Importacion, MovimientoBancario
from cobros.models import Pago
from cortes import calculo

from .banco_ayudas import cuenta_principal, enlace, estado, pdf, spei
from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo, verificar_sumas


def base(personas):
    preparar_conceptos()
    cuenta_principal()
    return titular_activo(personas["op"], personas["sup"], "Ana")


def importar_csv(usuario, texto):
    c = cliente(usuario)
    r = c.post(reverse("conciliacion:importar"), {"archivo": SimpleUploadedFile("movs.csv", texto.encode()), "cuenta": cuenta_principal().pk})
    r2 = c.post(r.url, {"fecha": "0", "referencia": "1", "concepto": "2", "importe": "3"})
    assert r2.status_code == 302, r2.content.decode()[-1500:]
    c.post(r2.url)
    return Importacion.objects.order_by("-id").first()


def importar_pdf(usuario, movimientos):
    c = cliente(usuario)
    r = c.post(reverse("conciliacion:importar"), {"archivo": SimpleUploadedFile("estado.pdf", pdf(estado(movimientos)))})
    previa = c.get(r.url).content.decode()
    c.post(r.url)
    return Importacion.objects.order_by("-id").first(), previa


def test_archivo_a_mitad_de_mes_y_despues_el_estado_oficial_sin_rastreo_en_el_archivo(personas):
    ana = base(personas)
    archivo = importar_csv(personas["sup"], f"fecha,referencia,concepto,importe\n03/08/2026,{ana.matricula},colegiatura,500.00\n")
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 1
    assert [i.pk for i in conciliacion.pendientes_de_revision()] == [archivo.pk]
    oficial, previa = importar_pdf(personas["sup"], [spei(3, 50000, referencia=ana.matricula, concepto="colegiatura", nombre="PAGADOR FICTICIO", rastreo="RASTREO01")])
    assert "ya llegaron por otra vía" in previa
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 1 and oficial.otra_via == 1 and oficial.aplicados == 0
    primero = MovimientoBancario.objects.get(importacion=archivo)
    segundo = MovimientoBancario.objects.get(importacion=oficial)
    assert segundo.estado == MovimientoBancario.MISMO and segundo.mismo_que == primero and segundo.pago_id is None
    assert primero.confirmado_por == segundo and primero.rastreo == "RASTREO01" and primero.nombre_pagador == "PAGADOR FICTICIO" and primero.cuenta_pagador
    assert conciliacion.pendientes_de_revision().count() == 0
    banco = calculo.cifras_mayor(segundo.fecha.replace(day=1), segundo.fecha.replace(day=31))["totales"]["banco"]
    assert banco["aplicado_confirmado_por_estado_oficial"] == 50000 and banco["aplicado_sin_confirmar"] == 0
    verificar_sumas()


def test_estado_oficial_primero_y_luego_el_archivo_no_duplica(personas):
    ana = base(personas)
    oficial, _ = importar_pdf(personas["sup"], [spei(5, 70000, referencia=ana.matricula, concepto="pago")])
    archivo = importar_csv(personas["sup"], f"fecha,referencia,concepto,importe\n05/08/2026,{ana.matricula},pago,700.00\n")
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 1 and archivo.otra_via == 1
    assert MovimientoBancario.objects.get(importacion=archivo).estado == MovimientoBancario.MISMO
    assert MovimientoBancario.objects.get(importacion=oficial).confirmado_por_id is None


def test_con_clave_de_rastreo_en_ambas_vias(personas):
    ana = base(personas)
    cuenta = cuenta_principal()
    comun = {"fecha": "2026-08-07", "folio": "", "descripcion": "ABONO", "importe": 30000, "saldo": None, "sentido": "abono", "clase": "archivo", "hora": "", "banco_origen": "", "cuenta_pagador": "", "nombre_pagador": ""}
    conciliacion.importar(cuenta, [{**comun, "rastreo": "RX1", "referencia": ana.matricula, "concepto": "uno", "huella": "a1"}], Importacion.ARCHIVO, "a.csv", "0" * 64, personas["sup"])
    otro = {**comun, "clase": "spei", "rastreo": "RX1", "referencia": "", "concepto": "texto distinto", "huella": "p1"}
    conciliacion.importar(cuenta, [otro], Importacion.ESTADO_PDF, "e.pdf", "0" * 64, personas["sup"], {"periodo_inicio": None, "periodo_fin": None})
    assert Pago.objects.count() == 1 and MovimientoBancario.objects.get(huella="p1").mismo_que.huella == "a1"
    distinto = {**otro, "rastreo": "RX2", "referencia": ana.matricula, "concepto": "uno", "huella": "p2"}
    conciliacion.importar(cuenta, [distinto], Importacion.ESTADO_PDF, "e2.pdf", "0" * 64, personas["sup"], {"periodo_inicio": None, "periodo_fin": None})
    assert MovimientoBancario.objects.get(huella="p2").mismo_que_id is None


def test_varias_coincidencias_quedan_en_la_cola_como_posible_duplicado(personas):
    ana = base(personas)
    importar_csv(personas["sup"], f"fecha,referencia,concepto,importe\n10/08/2026,{ana.matricula},colegiatura,200.00\n10/08/2026,{ana.matricula},colegiatura,200.00\n")
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 2
    oficial, previa = importar_pdf(personas["sup"], [spei(10, 20000, referencia=ana.matricula, concepto="colegiatura", rastreo="Z9")])
    assert "posible duplicado" in previa
    nuevo = MovimientoBancario.objects.get(importacion=oficial)
    assert nuevo.posible_duplicado and nuevo.estado == MovimientoBancario.POR_IDENTIFICAR and nuevo.pago_id is None
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 2
    assert "posible duplicado" in cliente(personas["sup"]).get(reverse("conciliacion:cola")).content.decode()
    assert "posible duplicado" in cliente(personas["sup"]).get(reverse("conciliacion:movimiento", args=[nuevo.pk])).content.decode()
