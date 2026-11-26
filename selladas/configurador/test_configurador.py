import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from cobros.models import ConceptoCobro
from configuracion.models import AvanceAsistente, Negocio, parametro
from cuentas.models import Dispositivo
from pruebas.test_asistente import paso_inicio
from pruebas.test_fabrica import Campos
from selladas.asistente.test_enter_y_autenticador import configurado_por, destino, enviar
from tarifas.models import TarifaAgrupacion
from titulares.models import Agrupacion

INICIO = reverse("asistente:inicio")
PASOS_NUEVOS = ("inicio", "marca", "personalizar", "grupos", "conceptos", "pago", "caja", "reglas", "cortes", "usuario", "codigo")
NOMBRES = {"grupo_1": "Grupo norte", "grupo_2": "Grupo sur"}


# La ruta «grupos» aún no existe: se resuelve dentro de cada prueba para que fallen una por una y no al importar.
def ruta(paso):
    return reverse(f"asistente:{paso}")


def autorizar(c):
    return c.post(INICIO, paso_inicio(settings.TOKEN_ASISTENTE))


def perder_sesion(c):
    c.cookies.pop(settings.SESSION_COOKIE_NAME, None)


def con_grupos(c, nombres=None):
    respuesta = c.post(ruta("grupos"), {"por_grupo": "si", **(nombres or NOMBRES)})
    assert destino(respuesta) == ruta("conceptos"), destino(respuesta)
    return [Agrupacion.objects.get(nombre=n) for n in (nombres or NOMBRES).values()]


def conceptos(n=2):
    return list(ConceptoCobro.objects.order_by("pk")[:n])


def casilla(concepto, agrupacion):
    return f"importe_{concepto.pk}_{agrupacion.pk}"


def tarifas():
    return set(TarifaAgrupacion.objects.values_list("concepto_id", "agrupacion_id", "importe_centavos", "activa"))


def importes():
    return dict(ConceptoCobro.objects.values_list("pk", "importe_centavos"))


def agrupaciones():
    return set(Agrupacion.objects.values_list("pk", "nombre", "activa"))


def valores(html):
    lector = Campos(None)
    lector.feed(html)
    datos = {}
    for formulario in lector.formularios:
        datos.update(formulario["datos"])
    return datos


def cantidad(texto):
    limpio = re.sub(r"[^0-9.]", "", texto or "")
    return Decimal(limpio) if limpio else None


@pytest.mark.django_db
def test_sin_token_grupos_manda_a_inicio_y_no_toca_nada():
    c = Client()
    autorizar(c)
    previa = Agrupacion.objects.create(nombre="Grupo previo")
    TarifaAgrupacion.objects.create(concepto=conceptos(1)[0], agrupacion=previa, importe_centavos=10000)
    antes = (agrupaciones(), tarifas())
    otro = Client()
    assert destino(otro.get(ruta("grupos"))) == INICIO
    for datos in ({"por_grupo": "no"}, {"por_grupo": "si", "grupo_1": "Intruso uno", "grupo_2": "Intruso dos"}, {"por_grupo": "si", "grupo_1": "Grupo previo", "accion": "otro"}):
        assert destino(otro.post(ruta("grupos"), datos)) == INICIO, datos
    assert (agrupaciones(), tarifas()) == antes


@pytest.mark.django_db
def test_grupos_invalidos_no_guardan_y_el_html_sale_escapado():
    c = Client()
    autorizar(c)
    malos = {
        "uno solo": {"grupo_1": "Grupo norte"},
        "ninguno": {},
        "mayúsculas y espacios": {"grupo_1": "Grupo norte", "grupo_2": "  GRUPO NORTE  "},
        "acentos": {"grupo_1": "Educación", "grupo_2": "educacion"},
        "101 caracteres": {"grupo_1": "G" * 101, "grupo_2": "Grupo sur"},
    }
    for motivo, nombres in malos.items():
        respuesta = c.post(ruta("grupos"), {"por_grupo": "si", **nombres})
        assert respuesta.status_code == 200, (motivo, destino(respuesta))
        if motivo in ("mayúsculas y espacios", "acentos"):
            assert "Ese grupo ya está escrito." in respuesta.content.decode(), motivo
        assert not Agrupacion.objects.exists(), motivo
        assert not AvanceAsistente.objects.get().estado.get("por_grupo"), motivo
    otro = c.post(ruta("grupos"), {"por_grupo": "si", **NOMBRES, "accion": "otro"})
    assert otro.status_code == 200 and not Agrupacion.objects.exists(), "«Agregar grupo» guardó"
    assert all(n in otro.content.decode() for n in NOMBRES.values()), "«Agregar grupo» perdió lo escrito"

    con_grupos(c, {"grupo_1": "<b>Grupo</b> uno", "grupo_2": "Grupo dos"})
    html = c.get(ruta("conceptos")).content.decode()
    assert "<b>Grupo</b>" not in html
    assert "&lt;b&gt;Grupo&lt;/b&gt; uno" in html


@pytest.mark.django_db
def test_importes_por_grupo_quedan_exactos_y_uno_invalido_no_guarda_ninguno():
    c = Client()
    autorizar(c)
    norte, sur = con_grupos(c)
    primero, segundo = conceptos()
    antes = importes()
    for malo in ("0", "-5", "doce", "99999999999999999"):
        datos = {f"importe_{primero.pk}": "1000", f"importe_{segundo.pk}": "80", casilla(primero, norte): "100", casilla(primero, sur): malo, casilla(segundo, norte): "50"}
        respuesta = c.post(ruta("conceptos"), datos)
        assert respuesta.status_code == 200, (malo, destino(respuesta))
        assert not TarifaAgrupacion.objects.exists(), f"Con la casilla «{malo}» se guardaron tarifas"
        assert importes() == antes
    datos = {f"importe_{primero.pk}": "1000", f"importe_{segundo.pk}": "80", casilla(primero, norte): "1250.50", casilla(primero, sur): "1300", casilla(segundo, norte): "99.99", casilla(segundo, sur): ""}
    assert destino(c.post(ruta("conceptos"), datos)) == ruta("pago")
    assert tarifas() == {(primero.pk, norte.pk, 125050, True), (primero.pk, sur.pk, 130000, True), (segundo.pk, norte.pk, 9999, True)}
    despues = {**antes, primero.pk: 100000, segundo.pk: 8000}
    assert importes() == despues
    datos[casilla(segundo, norte)] = ""
    assert destino(c.post(ruta("conceptos"), datos)) == ruta("pago")
    assert tarifas() == {(primero.pk, norte.pk, 125050, True), (primero.pk, sur.pk, 130000, True)}, "La casilla vaciada no borró su tarifa"
    assert importes() == despues


@pytest.mark.django_db
def test_casillas_ajenas_no_truenan_ni_crean_tarifas():
    c = Client()
    autorizar(c)
    norte, _ = con_grupos(c)
    cerrada = Agrupacion.objects.create(nombre="Grupo cerrado", activa=False)
    primero = conceptos(1)[0]
    cuenta = (ConceptoCobro.objects.count(), Agrupacion.objects.count())
    ajeno = max(ConceptoCobro.objects.values_list("pk", flat=True)) + 1000
    sin_grupo = max(Agrupacion.objects.values_list("pk", flat=True)) + 1000
    datos = {
        f"importe_{primero.pk}": "150",
        casilla(primero, norte): "200",
        f"importe_{ajeno}_{norte.pk}": "300",
        f"importe_{primero.pk}_{sin_grupo}": "400",
        casilla(primero, cerrada): "500",
        "importe_x_y": "600",
        f"importe_{primero.pk}_{norte.pk}_1": "700",
    }
    respuesta = c.post(ruta("conceptos"), datos)
    assert respuesta.status_code < 500
    assert destino(respuesta) == ruta("pago"), "Las casillas ajenas impidieron guardar"
    assert tarifas() == {(primero.pk, norte.pk, 20000, True)}
    assert (ConceptoCobro.objects.count(), Agrupacion.objects.count()) == cuenta
    assert not Agrupacion.objects.get(pk=cerrada.pk).activa


@pytest.mark.django_db
def test_igual_para_todos_copia_la_fila_sin_guardar():
    c = Client()
    autorizar(c)
    a, b, d = con_grupos(c, {"grupo_1": "Grupo uno", "grupo_2": "Grupo dos", "grupo_3": "Grupo tres"})
    primero, segundo = conceptos()
    antes = importes()
    datos = {
        casilla(primero, a): "",
        casilla(primero, b): "500",
        casilla(primero, d): "650",
        casilla(segundo, a): "70",
        casilla(segundo, b): "80",
        casilla(segundo, d): "",
        "igual": str(primero.pk),
    }
    respuesta = c.post(ruta("conceptos"), datos)
    assert respuesta.status_code == 200, destino(respuesta)
    pintado = valores(respuesta.content.decode())
    assert [cantidad(pintado.get(casilla(primero, g))) for g in (a, b, d)] == [Decimal(500)] * 3
    assert [cantidad(pintado.get(casilla(segundo, g))) for g in (a, b, d)] == [Decimal(70), Decimal(80), None]
    assert not TarifaAgrupacion.objects.exists()
    assert importes() == antes


@pytest.mark.django_db
def test_sin_grupos_los_importes_van_al_concepto_como_hoy():
    c = Client()
    autorizar(c)
    previa = Agrupacion.objects.create(nombre="Grupo previo")
    assert destino(c.post(ruta("grupos"), {"por_grupo": "no"})) == ruta("conceptos")
    primero = conceptos(1)[0]
    html = c.get(ruta("conceptos")).content.decode()
    assert f'name="importe_{primero.pk}"' in html
    assert f'name="importe_{primero.pk}_' not in html
    assert destino(c.post(ruta("conceptos"), {f"importe_{primero.pk}": "1500"})) == ruta("pago")
    assert ConceptoCobro.objects.get(pk=primero.pk).importe_centavos == 150000
    assert not TarifaAgrupacion.objects.exists()
    assert Agrupacion.objects.filter(pk=previa.pk, activa=True).exists()


@pytest.mark.django_db
def test_cambiar_a_no_borra_las_tarifas_guardadas():
    c = Client()
    autorizar(c)
    norte, sur = con_grupos(c)
    primero = conceptos(1)[0]
    assert destino(c.post(ruta("conceptos"), {f"importe_{primero.pk}": "150", casilla(primero, norte): "100", casilla(primero, sur): "200"})) == ruta("pago")
    assert TarifaAgrupacion.objects.count() == 2
    assert c.get(ruta("grupos")).status_code == 200
    assert destino(c.post(ruta("grupos"), {"por_grupo": "no"})) == ruta("conceptos")
    assert not TarifaAgrupacion.objects.exists()
    assert set(Agrupacion.objects.values_list("nombre", flat=True)) == set(NOMBRES.values())


@pytest.mark.django_db
def test_orden_nuevo_de_punta_a_punta_y_reanuda_en_grupos():
    c = Client()
    recorrido = []
    paso = "inicio"
    reanudado = False
    for _ in range(3 * len(PASOS_NUEVOS)):
        recorrido.append(paso)
        extra = None
        if paso == "grupos":
            if not reanudado:
                perder_sesion(c)
                assert destino(c.get(INICIO)) == ruta("grupos"), "Sin la cookie de sesión no se reanudó en «grupos»"
                reanudado = True
            extra = {"por_grupo": "si", **NOMBRES}
        if paso == "conceptos":
            extra = {f"importe_{conceptos(1)[0].pk}": "150", casilla(conceptos(1)[0], Agrupacion.objects.get(nombre="Grupo norte")): "100"}
        respuesta = enviar(c, paso, extra=extra)
        assert respuesta.status_code == 302, (recorrido, respuesta.status_code)
        if paso == "inicio":
            assert respuesta.url == ruta("marca"), f"Tras «inicio» fue a {respuesta.url}"
        if respuesta.url == reverse("primeros_pasos"):
            break
        paso = next((p for p in PASOS_NUEVOS if ruta(p) == respuesta.url), respuesta.url)
    else:
        pytest.fail(f"La instalación no termina; ciclo: {' -> '.join(recorrido)}")
    assert recorrido == list(PASOS_NUEVOS)
    assert configurado_por("jefa")
    assert TarifaAgrupacion.objects.filter(importe_centavos=10000).exists()


def llenar_pendientes(tanda):
    faltan = parametro("maximo_equipos_pendientes") - Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).count()
    Dispositivo.objects.bulk_create(Dispositivo(hash_credencial=f"{tanda}{i:063d}", codigo="LLENO") for i in range(faltan))
    Dispositivo.objects.exclude(avance__isnull=False).update(creado=timezone.now() - timedelta(hours=1))


@pytest.mark.django_db
def test_cupo_lleno_en_la_instalacion_no_deja_fuera_al_equipo_nuevo():
    c = Client()
    autorizar(c)
    ligado = AvanceAsistente.objects.get().dispositivo_id
    Dispositivo.objects.filter(pk=ligado).update(creado=timezone.now() - timedelta(hours=5))
    llenar_pendientes(1)
    respuesta = Client().get(INICIO)
    assert respuesta.status_code == 200, f"Sin cupo, el equipo nuevo recibió {respuesta.status_code}"
    assert AvanceAsistente.objects.get().dispositivo_id == ligado
    assert c.get(ruta("marca")).status_code == 200, "El equipo que instala perdió la autorización"
    assert Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).count() <= parametro("maximo_equipos_pendientes")

    Negocio.objects.filter(pk=1).update(configurado=True)
    llenar_pendientes(2)
    cuenta = Dispositivo.objects.count()
    assert Client().get("/").status_code == 403
    assert Dispositivo.objects.count() == cuenta
