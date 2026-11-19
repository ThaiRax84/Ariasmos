import re
from html.parser import HTMLParser

import pytest
from django.core.cache import cache
from django.urls import reverse

from banco.models import Importacion, MovimientoBancario
from caja.models import Arqueo, MotivoRetiro, RetiroCaja, Turno
from cobros import libro
from cobros.models import ConceptoCobro, Pago
from configuracion.models import Parametro
from envios.middleware import CAMPO, MENSAJE
from envios.models import EnvioUsado
from inventario import servicios as inventario
from inventario.models import Articulo, Conteo, Devolucion, Venta
from solicitudes import motor
from solicitudes.models import Solicitud

from .banco_ayudas import cuenta_principal, estado, pdf, spei
from .conftest import cliente
from .libro_ayudas import cobro_en_piezas, preparar_conceptos, titular_activo, turno_de, verificar_sumas

class Formularios(HTMLParser):
    def __init__(self, ruta):
        super().__init__()
        self.ruta = ruta
        self.formularios = []
        self.actual = None

    def handle_starttag(self, etiqueta, atributos):
        atributos = dict(atributos)
        if etiqueta == "form" and (atributos.get("method") or "").lower() == "post":
            self.actual = {"accion": atributos.get("action") or self.ruta, "datos": {}}
            self.formularios.append(self.actual)
        elif etiqueta == "input" and self.actual is not None and atributos.get("type") == "hidden" and atributos.get("name"):
            self.actual["datos"][atributos["name"]] = atributos.get("value", "")

    def handle_endtag(self, etiqueta):
        if etiqueta == "form":
            self.actual = None


def formularios(respuesta, ruta):
    lector = Formularios(ruta)
    lector.feed(respuesta.content.decode())
    return lector.formularios


def formulario(respuesta, ruta, accion=None, con=None):
    for candidato in formularios(respuesta, ruta):
        if candidato["accion"] == reverse("salir"):
            continue
        if accion is not None and candidato["accion"] != accion:
            continue
        if isinstance(con, tuple) and candidato["datos"].get(con[0]) != con[1]:
            continue
        if isinstance(con, str) and con not in candidato["datos"]:
            continue
        if CAMPO in candidato["datos"]:
            return candidato
    raise AssertionError(f"No hay formulario con ficha hacia {accion} en {ruta}")


def dos_veces(c, respuesta, ruta, datos, accion=None, con=None, **extra):
    elegido = formulario(respuesta, ruta, accion, con)
    envio = {**{k: v for k, v in elegido["datos"].items() if k != "csrfmiddlewaretoken"}, **datos}
    primera = c.post(elegido["accion"], envio, **extra)
    segunda = c.post(elegido["accion"], envio, **extra)
    return primera, segunda


def fijar(clave, valor):
    Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})


@pytest.fixture
def base(personas):
    cache.clear()
    preparar_conceptos()
    return personas, titular_activo(personas["op"], personas["sup"], "Ana")


def test_cada_formulario_lleva_su_propia_ficha(base):
    personas, ana = base
    turno_de(personas["op"])
    ruta = reverse("cobros:cobrar", args=[ana.pk])
    pagina = cliente(personas["op"]).get(ruta)
    fichas = re.findall(r'name="' + CAMPO + r'" value="([A-Za-z0-9_-]{43})"', pagina.content.decode())
    assert len(fichas) >= 2 and len(set(fichas)) == len(fichas)
    otra = re.findall(r'name="' + CAMPO + r'" value="([^"]+)"', cliente(personas["op"]).get(ruta).content.decode())
    assert not set(otra) & set(fichas)
    assert all(CAMPO in f["datos"] for f in formularios(pagina, ruta))
    assert pagina["Cache-Control"] == "no-store"


def test_cobro_reenviado_no_cobra_dos_veces(base):
    personas, ana = base
    turno_de(personas["op"])
    op = cliente(personas["op"])
    ruta = reverse("cobros:cobrar", args=[ana.pk])
    pagina = op.get(ruta)
    previa, otra_previa = dos_veces(op, pagina, ruta, {"importe": "500"})
    assert previa.status_code == 200 and otra_previa.status_code == 200 and not Pago.objects.exists()
    cambio, _ = dos_veces(op, previa, ruta, {"r_50000": "1"}, con="ficha")
    assert cambio.status_code == 200 and not Pago.objects.exists()
    previa = cambio
    primera, segunda = dos_veces(op, previa, ruta, {"r_50000": "1"}, con="ficha")
    assert Pago.objects.count() == 1
    assert primera.status_code == 302 and segunda.status_code == 302 and primera.url == segunda.url
    assert MENSAJE in op.get(segunda.url).content.decode()
    sin_ficha = {**formulario(previa, ruta, con="ficha")["datos"], "r_50000": "1"}
    sin_ficha.pop(CAMPO)
    sin_ficha.pop("csrfmiddlewaretoken", None)
    op.post(ruta, sin_ficha)
    assert Pago.objects.count() == 1
    verificar_sumas()


def test_venta_reenviada_no_vende_dos_veces(base):
    personas, ana = base
    fijar("modulo_inventario", 1)
    libros = ConceptoCobro.objects.get(nombre="Libros")
    cuaderno = Articulo.objects.create(clave="CUA-1", nombre="Cuaderno", precio=5000, concepto=libros)
    conteo = inventario.subir_conteo({cuaderno.pk: 20}, personas["op"], Conteo.PANTALLA)
    motor.aprobar(conteo.solicitud, personas["sup"])
    turno_de(personas["op"])
    op = cliente(personas["op"])
    ruta = reverse("inventario:vender_publico")
    previa, _ = dos_veces(op, op.get(ruta), ruta, {f"cantidad_{cuaderno.pk}": "2"})
    assert previa.status_code == 200 and not Venta.objects.exists()
    cambio, _ = dos_veces(op, previa, ruta, {f"cantidad_{cuaderno.pk}": "2", "r_10000": "1"}, con="ficha")
    primera, segunda = dos_veces(op, cambio, ruta, {f"cantidad_{cuaderno.pk}": "2", "r_10000": "1"}, con="ficha")
    assert Venta.objects.count() == 1 and primera.url == segunda.url
    assert inventario.existencias()[cuaderno.pk] == 18
    venta = inventario.vender(ana, [(cuaderno.pk, 1)], Venta.ADEUDO, personas["op"])
    renglon = venta.renglones.get()
    fijar("devoluciones_inventario", 1)
    ruta = reverse("inventario:devolver_venta", args=[venta.pk])
    primera, segunda = dos_veces(op, op.get(ruta), ruta, {f"cantidad_{renglon.pk}": "1", "medio": "saldo", "motivo": "sobró"})
    assert Devolucion.objects.count() == 1 and primera.status_code == 302 and segunda.url == primera.url
    assert inventario.existencias()[cuaderno.pk] == 18


def test_retiro_reenviado_no_retira_dos_veces(base):
    personas, ana = base
    for clave, valor in (("tope_retiro_individual", 100000), ("tope_retiros_periodo", 300000), ("maximo_retiros_periodo", 5), ("periodo_retiros", "dia")):
        fijar(clave, valor)
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 200000, Pago.EFECTIVO, personas["op"], turno=turno, piezas=cobro_en_piezas(200000))
    motivo = MotivoRetiro.objects.get(nombre="Compra de insumos")
    op = cliente(personas["op"])
    ruta = reverse("caja:retiro_nuevo")
    primera, segunda = dos_veces(op, op.get(ruta), ruta, {"importe": "100", "motivo": motivo.pk, "nota": "", "p_10000": "1"})
    assert RetiroCaja.objects.count() + Solicitud.objects.filter(accion="retiro_caja").count() == 1
    assert primera.status_code == 302 and segunda.url == primera.url


def test_corte_de_caja_reenviado_no_se_cierra_dos_veces(base):
    personas, ana = base
    turno = turno_de(personas["op"])
    libro.registrar_pago(ana, 100000, Pago.EFECTIVO, personas["op"], turno=turno)
    op = cliente(personas["op"])
    ruta = reverse("caja:cerrar", args=[turno.pk])
    primera, segunda = dos_veces(op, op.get(ruta), ruta, {"d_50000": 1})
    assert Arqueo.objects.count() == 0 and primera.status_code == 302
    turno.refresh_from_db()
    assert turno.abierto
    ruta = reverse("caja:reconteo", args=[turno.pk])
    primera, segunda = dos_veces(op, op.get(ruta), ruta, {"nota": "Faltó dinero"}, con=("accion", "primero"))
    assert Arqueo.objects.count() == 1 and segunda.url == primera.url
    turno.refresh_from_db()
    assert turno.estado == Turno.CERRADO


def test_conciliacion_reenviada_no_aplica_dos_veces(base):
    personas, ana = base
    cuenta_principal()
    sup = cliente(personas["sup"])
    from django.core.files.uploadedfile import SimpleUploadedFile

    ruta = reverse("conciliacion:importar")
    subida = sup.post(ruta, {"archivo": SimpleUploadedFile("estado.pdf", pdf(estado([spei(3, 30000, concepto="pago")])))})
    assert subida.status_code == 302
    previa = sup.get(subida.url)
    primera, segunda = dos_veces(sup, previa, subida.url, {})
    assert Importacion.objects.count() == 1 and primera.status_code == 302 and segunda.url == primera.url
    movimiento = MovimientoBancario.objects.get()
    ruta = reverse("conciliacion:movimiento", args=[movimiento.pk])
    accion = reverse("conciliacion:confirmar", args=[movimiento.pk])
    primera, segunda = dos_veces(sup, sup.get(ruta), ruta, {"matricula": ana.matricula}, accion=accion)
    movimiento.refresh_from_db()
    assert movimiento.estado == MovimientoBancario.APLICADO and Pago.objects.filter(medio=Pago.BANCO).count() == 1
    assert segunda.url == primera.url
    verificar_sumas()


def test_un_envio_con_error_se_puede_corregir_y_reenviar(base):
    personas, ana = base
    turno_de(personas["op"])
    op = cliente(personas["op"])
    ruta = reverse("cobros:cobrar", args=[ana.pk])
    malo, otra_vez = dos_veces(op, op.get(ruta), ruta, {"importe": "abc"})
    assert malo.status_code == 200 and otra_vez.status_code == 200
    assert not EnvioUsado.objects.exists()


def test_fichas_raras_se_ignoran_y_las_viejas_se_borran(base):
    personas, ana = base
    from datetime import timedelta

    from django.utils import timezone

    viejo = EnvioUsado.objects.create(ficha="v" * 43, ruta="/x/", destino="/")
    EnvioUsado.objects.filter(pk=viejo.pk).update(creado=timezone.now() - timedelta(days=3))
    turno_de(personas["op"])
    op = cliente(personas["op"])
    ruta = reverse("cobros:cobrar", args=[ana.pk])
    for rara in ("corta", "a" * 65, "<script>", "a" * 40 + "!!!"):
        assert op.post(ruta, {"importe": "5", CAMPO: rara}).status_code == 200
    assert list(EnvioUsado.objects.values_list("ficha", flat=True)) == ["v" * 43]
    dos_veces(op, op.get(ruta), ruta, {"importe": "5"})
    assert not EnvioUsado.objects.filter(pk=viejo.pk).exists()


def test_redireccion_a_otro_sitio_no_se_repite(base):
    personas, ana = base
    EnvioUsado.objects.create(ficha="r" * 43, ruta="/x/", destino="https://otro.ejemplo/")
    respuesta = cliente(personas["op"]).post(reverse("caja:abrir"), {CAMPO: "r" * 43})
    assert respuesta.status_code == 302 and respuesta.url == "/"
    respuesta = cliente(personas["op"]).post(reverse("caja:abrir"), {CAMPO: "r" * 43}, HTTP_REFERER="http://testserver/caja/")
    assert respuesta.status_code == 302 and respuesta.url == "http://testserver/caja/"


def test_operaciones_de_datos_terminan_en_redireccion(personas, roles):
    c = cliente(personas["dir"])
    respuesta = c.post(reverse("usuario_nuevo"), {"usuario": "nueva", "nombre": "Persona nueva", "rol": roles["Operación"].pk})
    assert respuesta.status_code == 302 and respuesta.url == reverse("usuario_codigo")
    pagina = c.get(respuesta.url).content.decode()
    assert re.search(r'<p class="codigo-equipo">[A-Z0-9]{5}-[A-Z0-9]{5}</p>', pagina)
    otra = c.get(reverse("usuario_codigo"))
    assert otra.status_code == 302 and otra.url == reverse("usuarios")
