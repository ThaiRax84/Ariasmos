import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from auditoria.models import Evento
from banco import conciliacion
from banco.models import CargaTemporal, Importacion, MovimientoBancario
from cobros.models import Pago

from .banco_ayudas import cuenta_principal, enlace, estado, pdf, saldo_final, spei
from .conftest import cliente, nuevo_usuario

AGOSTO = [enlace(5, 1000, "intereses"), enlace(20, 2500, "varios")]


@pytest.fixture
def base(personas):
    from .libro_ayudas import preparar_conceptos, titular_activo

    cache.clear()
    preparar_conceptos()
    cuenta_principal()
    return personas, titular_activo(personas["op"], personas["sup"], "Ana")


def subir_pdf(usuario, movimientos, **opciones):
    c = cliente(usuario)
    r = c.post(reverse("conciliacion:importar"), {"archivo": SimpleUploadedFile("estado.pdf", pdf(estado(movimientos, **opciones)))})
    assert r.status_code == 302, r.content.decode()[-1500:]
    return c, r.url


def importar(usuario, movimientos, **opciones):
    c, url = subir_pdf(usuario, movimientos, **opciones)
    previa = c.get(url).content.decode()
    assert c.post(url).status_code == 302
    return Importacion.objects.order_by("-id").first(), previa


def importar_archivo(usuario, contenido):
    c = cliente(usuario)
    r = c.post(reverse("conciliacion:importar"), {"archivo": SimpleUploadedFile("movs.csv", contenido), "cuenta": cuenta_principal().pk})
    c.post(r.url, {"fecha": "0", "referencia": "1", "importe": "2"})
    c.post(reverse("conciliacion:previa", args=[r.url.split("/")[-3]]))
    return Importacion.objects.order_by("-id").first()


def pendientes():
    return [i.pk for i in conciliacion.pendientes_de_revision()]


def test_primera_y_septiembre_que_continua_queda_verificada(base):
    personas, _ = base
    agosto, previa = importar(personas["sup"], AGOSTO)
    assert agosto.continuidad == Importacion.PRIMERA and "Primera de la cuenta" in previa
    septiembre_movs = [enlace(3, 700, "intereses")]
    septiembre, previa = importar(personas["sup"], septiembre_movs, mes=9, saldo_inicial=saldo_final(AGOSTO))
    assert septiembre.continuidad == Importacion.VERIFICADA and "Verificada" in previa
    assert str(septiembre.periodo_inicio) == "2026-09-01" and septiembre.saldo_inicial == agosto.saldo_final
    evento = Evento.objects.filter(accion="importacion_bancaria").order_by("-id").first()
    assert evento.datos["continuidad"] == "verificada" and evento.datos["saldo_final"] == septiembre.saldo_final and "total_abonos" in evento.datos


def test_septiembre_con_otro_saldo_se_rechaza_sin_escribir(base):
    personas, ana = base
    importar(personas["sup"], AGOSTO)
    antes = (Importacion.objects.count(), MovimientoBancario.objects.count(), Pago.objects.count(), Evento.objects.filter(accion="importacion_bancaria").count())
    c, url = subir_pdf(personas["sup"], [spei(3, 50000, referencia=ana.matricula)], mes=9, saldo_inicial=saldo_final(AGOSTO) + 100)
    previa = c.get(url).content.decode()
    assert "No continúa el estado anterior" in previa and "Confirmar importación" not in previa
    c.post(url)
    despues = (Importacion.objects.count(), MovimientoBancario.objects.count(), Pago.objects.count(), Evento.objects.filter(accion="importacion_bancaria").count())
    assert antes == despues


def test_mismo_periodo_con_otros_saldos_se_rechaza(base):
    personas, _ = base
    importar(personas["sup"], AGOSTO)
    c, url = subir_pdf(personas["sup"], AGOSTO + [enlace(28, 900, "otro")])
    assert "mismo periodo con otros saldos" in c.get(url).content.decode()
    c.post(url)
    assert Importacion.objects.count() == 1 and MovimientoBancario.objects.count() == 2


def test_reimportar_el_mismo_pdf_no_cambia_nada(base):
    personas, ana = base
    movimientos = [spei(3, 50000, referencia=ana.matricula)]
    primera, _ = importar(personas["sup"], movimientos)
    otra, _ = importar(personas["sup"], movimientos)
    assert otra.continuidad == primera.continuidad == Importacion.PRIMERA
    assert otra.nuevos == 0 and MovimientoBancario.objects.count() == 1 and Pago.objects.filter(medio=Pago.BANCO).count() == 1
    assert pendientes() == []
    septiembre, _ = importar(personas["sup"], [enlace(4, 100, "x")], mes=9, saldo_inicial=saldo_final(movimientos))
    assert septiembre.continuidad == Importacion.VERIFICADA


def test_octubre_sin_septiembre_queda_con_hueco_y_pendiente_para_direccion(base):
    personas, ana = base
    importar(personas["sup"], AGOSTO)
    octubre, previa = importar(personas["sup"], [spei(3, 50000, referencia=ana.matricula)], mes=10, saldo_inicial=777)
    assert octubre.continuidad == Importacion.CON_HUECO and "Con hueco" in previa
    assert pendientes() == [octubre.pk]
    inicio = cliente(personas["dir"]).get(reverse("inicio")).content.decode()
    assert "Importaciones bancarias por revisar" in inicio and "$500.00" in inicio
    assert "por revisar" not in cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    detalle = cliente(personas["dir"]).get(reverse("conciliacion:importacion", args=[octubre.pk])).content.decode()
    assert "pendiente de revisión" in detalle and "Marcar como revisada" in detalle


def test_quien_importo_no_puede_marcarla_y_otra_persona_si(base):
    personas, ana = base
    importar(personas["dir"], AGOSTO)
    octubre, _ = importar(personas["dir"], [spei(3, 50000, referencia=ana.matricula)], mes=10)
    url = reverse("conciliacion:revisada", args=[octubre.pk])
    assert "Marcar como revisada" not in cliente(personas["dir"]).get(reverse("conciliacion:importacion", args=[octubre.pk])).content.decode()
    assert cliente(personas["dir"]).post(url).status_code == 403
    assert Evento.objects.filter(accion="revision_propia_denegada").count() == 1
    assert cliente(personas["sup"]).post(url).status_code == 403
    octubre.refresh_from_db()
    assert octubre.revisada_por is None and pendientes() == [octubre.pk]
    otra = nuevo_usuario("direccion2", personas["dir"].rol)
    assert cliente(otra).post(url).status_code == 302
    octubre.refresh_from_db()
    assert octubre.revisada_por == otra and octubre.revisada_en is not None and pendientes() == []
    evento = Evento.objects.get(accion="importacion_revisada")
    assert evento.datos["pagos"] == 1 and evento.datos["monto"] == 50000
    historial = cliente(personas["dir"]).get(reverse("conciliacion:importaciones")).content.decode()
    assert "Revisada por" in historial and "Con hueco" in historial


def test_archivo_generico_no_verificable_y_pendiente_si_aplico(base):
    personas, ana = base
    sin_pago = importar_archivo(personas["sup"], b"fecha,referencia,importe\n03/08/2026,,150\n")
    assert sin_pago.continuidad == Importacion.NO_VERIFICABLE and pendientes() == []
    con_pago = importar_archivo(personas["sup"], f"fecha,referencia,importe\n04/08/2026,{ana.matricula},300\n".encode())
    assert con_pago.continuidad == Importacion.NO_VERIFICABLE and pendientes() == [con_pago.pk]


def test_sin_pagos_no_pendiente_y_pasa_a_pendiente_al_confirmar_desde_la_cola(base):
    personas, ana = base
    importar(personas["sup"], AGOSTO)
    octubre, _ = importar(personas["sup"], [enlace(3, 50000, "pago sin matricula")], mes=10)
    assert octubre.continuidad == Importacion.CON_HUECO and pendientes() == []
    movimiento = MovimientoBancario.objects.get(importacion=octubre)
    cliente(personas["sup"]).post(reverse("conciliacion:confirmar", args=[movimiento.pk]), {"matricula": ana.matricula})
    assert pendientes() == [octubre.pk]


def test_verificada_con_pagos_no_pide_revision(base):
    personas, ana = base
    importar(personas["sup"], AGOSTO)
    septiembre, _ = importar(personas["sup"], [spei(3, 50000, referencia=ana.matricula)], mes=9, saldo_inicial=saldo_final(AGOSTO))
    assert septiembre.continuidad == Importacion.VERIFICADA and pendientes() == []
    assert cliente(personas["dir"]).post(reverse("conciliacion:revisada", args=[septiembre.pk])).status_code == 302
    septiembre.refresh_from_db()
    assert septiembre.revisada_por is None


def test_anterior_a_todo_lo_importado_queda_con_hueco(base):
    personas, _ = base
    importar(personas["sup"], AGOSTO, mes=9)
    junio, _ = importar(personas["sup"], [enlace(3, 100, "x")], mes=6)
    assert junio.continuidad == Importacion.CON_HUECO
    assert not CargaTemporal.objects.exists()


def test_estado_sin_periodo_legible_queda_con_hueco(base):
    importar(base[0]["sup"], AGOSTO)
    resumen = {"periodo_inicio": None, "periodo_fin": None, "saldo_inicial": 1, "saldo_final": 2}
    assert conciliacion.continuidad(cuenta_principal(), Importacion.ESTADO_PDF, resumen) == Importacion.CON_HUECO
    assert conciliacion.continuidad(cuenta_principal(), Importacion.ARCHIVO, resumen) == Importacion.NO_VERIFICABLE
