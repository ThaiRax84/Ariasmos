import io

import pytest
import segno
from django.urls import reverse
from pypdf import PdfReader

from auditoria.models import Evento
from cobros import libro, qr
from cobros.models import Pago
from configuracion.models import Parametro

from .conftest import cliente, equipo_aprobado
from .libro_ayudas import preparar_conceptos, titular_activo, turno_de


@pytest.fixture
def recibo(personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Anabel")
    pago = libro.registrar_pago(ana, 123400, Pago.EFECTIVO, personas["op"], turno=turno_de(personas["op"]))
    return personas, ana, pago.recibo


def test_el_qr_lleva_solo_serie_folio_y_codigo(recibo):
    personas, ana, objeto = recibo
    texto = qr.texto(objeto)
    assert texto == f"AR1|{objeto.serie}|{objeto.folio}|{objeto.codigo}"
    for prohibido in (ana.nombre, ana.apellidos, ana.matricula, "1234", "http", "//"):
        assert prohibido not in texto
    pagina = cliente(personas["op"]).get(reverse("cobros:recibo", args=[objeto.pk])).content.decode()
    esperado = segno.make(texto, error="m", micro=False).svg_inline(scale=4, dark="#000", light="#fff", border=4)
    assert esperado in pagina


def test_el_pdf_lleva_el_qr(recibo):
    personas, ana, objeto = recibo
    documento = cliente(personas["op"]).get(reverse("cobros:recibo_pdf", args=[objeto.pk])).content
    contenido = PdfReader(io.BytesIO(documento)).pages[0].get_contents().get_data()
    assert contenido.count(b" re") > 100 and b"AR1|" not in documento


def test_verificar_con_el_texto_del_qr_o_con_el_codigo(recibo):
    personas, ana, objeto = recibo
    c = cliente(personas["op"])
    por_qr = c.get(reverse("cobros:verificar"), {"codigo": qr.texto(objeto).lower()}).content.decode()
    assert "Recibo auténtico" in por_qr and ana.nombre in por_qr
    sin_guion = c.get(reverse("cobros:verificar"), {"codigo": objeto.codigo.replace("-", ""), "folio": f"{objeto.serie}-{objeto.folio}"}).content.decode()
    assert "Recibo auténtico" in sin_guion
    falso = c.get(reverse("cobros:verificar"), {"codigo": f"AR1|{objeto.serie}|{objeto.folio}|AAAAA-AAAAA"}).content.decode()
    assert "No reconocido" in falso and ana.nombre not in falso
    otro_folio = c.get(reverse("cobros:verificar"), {"codigo": f"AR1|{objeto.serie}|{objeto.folio + 1}|{objeto.codigo}"}).content.decode()
    assert "No reconocido" in otro_folio
    for malo in ("AR1|A|1", "AR1|a b|1|X", "AR2|A|1|AAAAA-AAAAA", f"AR1|{objeto.serie}|x|{objeto.codigo}"):
        assert "Recibo auténtico" not in c.get(reverse("cobros:verificar"), {"codigo": malo}).content.decode()
    assert Evento.objects.filter(accion="recibo_verificado", datos__por_qr=True).count() == 1
    assert Evento.objects.filter(accion="recibo_no_reconocido").count() == 2


def test_verificar_un_recibo_cancelado(recibo):
    personas, ana, objeto = recibo
    turno_de(personas["sup"], "Caja 2")
    libro.registrar_pago(ana, 200000, Pago.EFECTIVO, personas["sup"], turno=personas["sup"].turnos.get(estado="abierto"))
    libro.revertir_pago(objeto.pago, "error", personas["sup"], turno=personas["sup"].turnos.get(estado="abierto"))
    texto = cliente(personas["op"]).get(reverse("cobros:verificar"), {"codigo": qr.texto(objeto)}).content.decode()
    assert "CANCELADO" in texto


def test_verificar_exige_sesion_y_permiso(recibo):
    personas, ana, objeto = recibo
    assert cliente().get(reverse("cobros:verificar"), {"codigo": qr.texto(objeto)}).status_code == 302


def test_intentos_fallidos_limitados_por_persona(recibo):
    personas, ana, objeto = recibo
    Parametro.objects.create(clave="intentos_verificar_recibo_por_hora", valor="3")
    c = cliente(personas["op"])
    for numero in range(3):
        c.get(reverse("cobros:verificar"), {"codigo": f"AR1|{objeto.serie}|{objeto.folio}|AAAAA-AAAA{numero}"})
    bloqueado = c.get(reverse("cobros:verificar"), {"codigo": qr.texto(objeto)}).content.decode()
    assert "Recibo auténtico" not in bloqueado and "demasiadas verificaciones" in bloqueado.lower()
    assert Evento.objects.filter(accion="verificacion_bloqueada", datos__por="usuario").exists()
    assert "Recibo auténtico" in cliente(personas["op2"]).get(reverse("cobros:verificar"), {"codigo": qr.texto(objeto)}).content.decode()


def test_intentos_fallidos_limitados_por_equipo(recibo):
    personas, ana, objeto = recibo
    Parametro.objects.create(clave="intentos_verificar_recibo_por_hora", valor="3")
    equipo = equipo_aprobado()
    for numero, usuario in enumerate((personas["op"], personas["op2"], personas["sup"])):
        cliente(usuario, credencial=equipo).get(reverse("cobros:verificar"), {"codigo": f"AR1|{objeto.serie}|{objeto.folio}|BBBBB-BBBB{numero}"})
    bloqueado = cliente(personas["dir"], credencial=equipo).get(reverse("cobros:verificar"), {"codigo": qr.texto(objeto)}).content.decode()
    assert "Recibo auténtico" not in bloqueado
    assert Evento.objects.filter(accion="verificacion_bloqueada", datos__por="equipo").exists()
    assert "Recibo auténtico" in cliente(personas["dir"]).get(reverse("cobros:verificar"), {"codigo": qr.texto(objeto)}).content.decode()


def test_campo_de_captura_guiada(recibo):
    personas, ana, objeto = recibo
    pagina = cliente(personas["op"]).get(reverse("cobros:verificar")).content.decode()
    assert 'data-acepta="recibo"' in pagina and 'data-acepta="folio"' in pagina
