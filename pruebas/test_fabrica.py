import re
from html.parser import HTMLParser

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from caja import piezas as control_piezas
from caja.servicios import esperado_de
from configuracion.moneda import formatear
from caja.models import Arqueo, MotivoRetiro, MovimientoPiezas, RetiroCaja, Turno
from cobros.models import Pago, ReversionPago
from configuracion.models import Parametro, parametro
from cuentas.models import Rol
from inventario import servicios as inventario
from inventario.models import Articulo, Conteo, Venta
from cobros.models import ConceptoCobro
from solicitudes import motor
from solicitudes.models import Solicitud
from titulares.models import Titular
from titulares.servicios import crear_titular

from .conftest import cliente, nuevo_usuario
from .test_asistente import paso_inicio, terminar

PLANTILLAS = ("escuela", "academia", "gimnasio", "rentas", "servicios", "generico")


class Campos(HTMLParser):
    def __init__(self, elegir):
        super().__init__()
        self.elegir = elegir
        self.formularios = []
        self.actual = None
        self.select = None
        self.texto = None

    def handle_starttag(self, etiqueta, atributos):
        atributos = dict(atributos)
        if etiqueta == "form" and (atributos.get("method") or "").lower() == "post":
            self.actual = {"accion": atributos.get("action"), "datos": {}, "nombres": set()}
            self.formularios.append(self.actual)
        if self.actual is None:
            return
        nombre = atributos.get("name")
        if etiqueta == "input" and nombre:
            self.actual["nombres"].add(nombre)
            tipo = atributos.get("type", "text")
            if tipo in ("checkbox", "radio"):
                if "checked" in atributos:
                    self.actual["datos"][nombre] = atributos.get("value", "on")
            elif tipo not in ("submit", "button", "file"):
                self.actual["datos"][nombre] = atributos.get("value") or ""
        elif etiqueta == "select" and nombre:
            self.actual["nombres"].add(nombre)
            self.select = nombre
        elif etiqueta == "option" and self.select:
            if "selected" in atributos or self.select not in self.actual["datos"]:
                self.actual["datos"][self.select] = atributos.get("value", "")
        elif etiqueta == "textarea" and nombre:
            self.actual["nombres"].add(nombre)
            self.texto = nombre
            self.actual["datos"][nombre] = ""

    def handle_data(self, datos):
        if self.texto and self.actual is not None:
            self.actual["datos"][self.texto] += datos

    def handle_endtag(self, etiqueta):
        if etiqueta == "select":
            self.select = None
        elif etiqueta == "textarea":
            self.texto = None
        elif etiqueta == "form":
            self.actual = None


def formulario(respuesta, con):
    assert respuesta.status_code < 500
    lector = Campos(con)
    lector.feed(respuesta.content.decode())
    for candidato in lector.formularios:
        if con in candidato["nombres"]:
            return {k: v for k, v in candidato["datos"].items() if k != "csrfmiddlewaretoken"}
    raise AssertionError(f"No hay formulario con {con}")


def sin_5xx(*respuestas):
    for respuesta in respuestas:
        assert respuesta.status_code < 500, respuesta.status_code


def pide_piezas(respuesta, prefijo):
    sin_5xx(respuesta)
    texto = respuesta.content.decode()
    assert "data-mosaicos" in texto
    assert re.search(r'name="' + prefijo + r'\d+"', texto)
    return texto


def solo_piezas(datos, prefijo):
    return {k: v for k, v in datos.items() if not k.startswith(prefijo)}


def correr_asistente(plantilla):
    c = Client()
    datos = paso_inicio(settings.TOKEN_ASISTENTE, plantilla)
    datos["inventario"] = "on"
    assert c.post(reverse("asistente:inicio"), datos).status_code == 302
    for paso, extra in (("personalizar", {"seguir": "continuar"}), ("conceptos", {}), ("caja", {}), ("reglas", {})):
        pagina = c.get(reverse(f"asistente:{paso}"))
        sin_5xx(pagina)
        if paso == "caja":
            assert 'name="control_denominaciones"' in pagina.content.decode()
            assert re.search(r'<input type="checkbox" name="control_denominaciones"[^>]*checked', pagina.content.decode())
        envio = formulario(pagina, "ficha_envio")
        envio.update(extra)
        respuesta = c.post(reverse(f"asistente:{paso}"), envio)
        assert respuesta.status_code == 302, (paso, respuesta.content.decode()[:3000])
    assert terminar(c).url == reverse("primeros_pasos")
    return c


@pytest.fixture(params=PLANTILLAS)
def fabrica(request, db):
    direccion = correr_asistente(request.param)
    assert parametro("control_denominaciones") == 1
    assert not Parametro.objects.filter(clave="aviso_control_denominaciones", valor="1").exists()
    assert control_piezas.denominaciones()
    cajero = nuevo_usuario("cajero", Rol.objects.get(nombre="Operación"))
    supervisor = nuevo_usuario("supervisor", Rol.objects.get(nombre="Supervisión"))
    return {"plantilla": request.param, "dir": direccion, "op": cajero, "sup": supervisor}


def _titular(fabrica):
    titular = crear_titular(fabrica["op"], {"nombre": "Ana", "apellidos": "Prueba"}, contacto={"nombre": "Resp", "valores": {}}, conceptos=[])
    motor.ejecutar("alta", fabrica["sup"], titular)
    titular.refresh_from_db()
    assert titular.estado == Titular.ACTIVO
    return titular


def _aprobar(fabrica, solicitud):
    sup = cliente(fabrica["sup"])
    sin_5xx(sup.get(reverse("solicitudes:detalle", args=[solicitud.pk])))
    respuesta = sup.post(reverse("solicitudes:aprobar", args=[solicitud.pk]), {})
    sin_5xx(respuesta)
    assert Solicitud.objects.get(pk=solicitud.pk).estado == Solicitud.APROBADA


def _cobrar(op, titular, importe, recibidas):
    ruta = reverse("cobros:cobrar", args=[titular.pk])
    pagina = op.get(ruta)
    sin_5xx(pagina)
    paso_importe = op.post(ruta, {**formulario(pagina, "importe"), "importe": importe})
    pide_piezas(paso_importe, "r_")
    envio = formulario(paso_importe, "paso")
    envio.update(recibidas)
    paso_cambio = op.post(ruta, envio)
    pide_piezas(paso_cambio, "c_")
    confirmar = formulario(paso_cambio, "paso")
    assert confirmar["paso"] == "confirmar"
    antes = Pago.objects.count()
    sin_piezas = op.post(ruta, solo_piezas(solo_piezas(confirmar, "r_"), "c_"))
    sin_5xx(sin_piezas)
    assert Pago.objects.count() == antes
    hecho = op.post(ruta, confirmar)
    assert hecho.status_code == 302 and "/recibos/" in hecho.url or Pago.objects.count() == antes + 1
    sin_5xx(op.get(hecho.url))
    assert Pago.objects.count() == antes + 1
    return Pago.objects.order_by("-id").first()


def test_un_dia_completo_con_valores_de_fabrica(fabrica):
    op = cliente(fabrica["op"])
    ana = _titular(fabrica)
    for ruta in ("inicio", "cobros:buscar", "caja:inicio", "caja:traslados", "inventario:vender"):
        sin_5xx(op.get(reverse(ruta)))

    inicio = pide_piezas(op.get(reverse("caja:inicio")), "f_")
    assert 'name="fondo_inicial"' not in inicio
    abrir = formulario(op.get(reverse("caja:inicio")), "apertura")
    assert op.post(reverse("caja:abrir"), {**solo_piezas(abrir, "f_"), "fondo_inicial": "500"}).status_code == 200
    assert not Turno.objects.exists()
    abrir.update({"apertura": "efectivo", "f_10000": "2", "f_5000": "2", "f_2000": "5", "f_1000": "5", "f_500": "4"})
    sin_5xx(op.post(reverse("caja:abrir"), abrir))
    turno = Turno.objects.get(usuario=fabrica["op"], estado=Turno.ABIERTO)
    assert turno.fondo_inicial == 20000 + 10000 + 10000 + 5000 + 2000

    libros = ConceptoCobro.objects.filter(tipo=ConceptoCobro.POR_EVENTO).first() or ConceptoCobro.objects.first()
    articulo = Articulo.objects.create(clave="ART-1", nombre="Artículo de prueba", precio=12000, concepto=libros)
    conteo = inventario.subir_conteo({articulo.pk: 10}, fabrica["op"], Conteo.PANTALLA)
    motor.aprobar(conteo.solicitud, fabrica["sup"])
    venta = op.post(reverse("inventario:vender_titular", args=[ana.pk]), {**formulario(op.get(reverse("inventario:vender_titular", args=[ana.pk])), "modo"), f"cantidad_{articulo.pk}": "1", "modo": "ahora"})
    assert venta.status_code == 302 and "venta=" in venta.url
    ruta_venta = venta.url
    pagina = op.get(ruta_venta)
    sin_5xx(pagina)
    paso_importe = op.post(ruta_venta, formulario(pagina, "importe"))
    pide_piezas(paso_importe, "r_")
    envio = formulario(paso_importe, "paso")
    envio["r_10000"] = "1"
    envio["r_2000"] = "1"
    paso_cambio = op.post(ruta_venta, envio)
    pide_piezas(paso_cambio, "r_")
    assert op.post(ruta_venta, formulario(paso_cambio, "paso")).status_code == 302
    assert Venta.objects.filter(titular=ana).get().pago is not None

    pago = _cobrar(op, ana, "350", {"r_50000": "1"})
    assert pago.importe == 35000
    assert control_piezas.total(dict((str(m.denominacion), -m.piezas) for m in MovimientoPiezas.objects.filter(pago=pago, origen=MovimientoPiezas.CAMBIO))) == 15000

    ruta = reverse("inventario:vender_publico")
    pagina = op.post(ruta, {**formulario(op.get(ruta), "ficha_envio"), f"cantidad_{articulo.pk}": "1"})
    pide_piezas(pagina, "r_")
    envio = formulario(pagina, "paso")
    envio.update({f"cantidad_{articulo.pk}": "1", "r_20000": "1"})
    cambio = op.post(ruta, envio)
    pide_piezas(cambio, "c_")
    confirmar = formulario(cambio, "paso")
    confirmar[f"cantidad_{articulo.pk}"] = "1"
    publicas = Venta.objects.filter(titular__interno=True)
    sin_5xx(op.post(ruta, solo_piezas(solo_piezas(confirmar, "r_"), "c_")))
    assert not publicas.exists()
    sin_5xx(op.post(ruta, confirmar))
    assert publicas.count() == 1 and publicas.get().pago is not None

    ruta = reverse("caja:retiro_nuevo")
    pagina = pide_piezas(op.get(ruta), "p_")
    retiro = formulario(op.get(ruta), "importe")
    retiro.update({"importe": "50", "nota": "Insumos", "motivo": MotivoRetiro.objects.filter(activo=True).first().pk})
    sin_5xx(op.post(ruta, retiro))
    assert not RetiroCaja.objects.exists() and not Solicitud.objects.filter(accion="retiro_caja").exists()
    retiro.update({"p_2000": "2", "p_1000": "1"})
    sin_5xx(op.post(ruta, retiro))
    solicitud = Solicitud.objects.filter(accion="retiro_caja").first()
    if solicitud is not None:
        _aprobar(fabrica, solicitud)
    assert RetiroCaja.objects.count() == 1

    ruta = reverse("cobros:revertir", args=[pago.pk])
    pide_piezas(op.get(ruta), "p_")
    reversion = formulario(op.get(ruta), "motivo")
    reversion["motivo"] = "Pago equivocado"
    sin_5xx(op.post(ruta, reversion))
    assert not Solicitud.objects.filter(accion="revertir_pago").exists() and not ReversionPago.objects.exists()
    reversion.update({"p_20000": "1", "p_10000": "1", "p_2000": "2", "p_1000": "1"})
    sin_5xx(op.post(ruta, reversion))
    solicitud = Solicitud.objects.filter(accion="revertir_pago").first()
    if solicitud is not None:
        _aprobar(fabrica, solicitud)
    assert ReversionPago.objects.filter(pago=pago).exists()

    retiro = RetiroCaja.objects.get()
    sin_5xx(op.post(reverse("caja:retiro_sin_comprobante", args=[retiro.pk]), {"motivo": "Ticket extraviado"}))
    ruta = reverse("caja:cerrar", args=[turno.pk])
    pagina = op.get(ruta)
    sin_5xx(pagina)
    assert "d_" in pagina.content.decode()
    texto = pagina.content.decode()
    assert formatear(esperado_de(turno)) not in texto and 'name="d_' in texto
    existencias = control_piezas.existencias(turno)
    assert all(cantidad >= 0 for cantidad in existencias.values())
    conteo = {f"d_{valor}": str(cantidad) for valor, cantidad in existencias.items()}
    sin_5xx(op.post(ruta, {**formulario(pagina, "nota"), **conteo}))
    assert Arqueo.objects.filter(turno=turno, diferencia=0).exists()
    for ruta in ("inicio", "caja:inicio", "cobros:buscar"):
        sin_5xx(op.get(reverse(ruta)))
    for ruta in ("inicio", "configuracion:indice", "configuracion:caja"):
        sin_5xx(fabrica["dir"].get(reverse(ruta)))
