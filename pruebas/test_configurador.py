import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from cobros.models import ConceptoCobro
from configuracion.models import AvanceAsistente, Negocio, parametro
from cuentas.models import Dispositivo
from tarifas.models import TarifaAgrupacion
from titulares.models import Agrupacion

from .test_asistente import paso_inicio


def instalar_hasta_grupos():
    c = Client()
    assert c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE)).url == reverse("asistente:marca")
    return c


def enviar_grupos(c, *nombres, por_grupo="si"):
    datos = {"por_grupo": por_grupo, **{f"grupo_{n}": nombre for n, nombre in enumerate(nombres, start=1)}}
    return c.post(reverse("asistente:grupos"), datos)


def casillas(c):
    conceptos, agrupaciones = list(ConceptoCobro.objects.all()), list(Agrupacion.objects.filter(activa=True))
    return conceptos, agrupaciones, {f"importe_{k.pk}_{a.pk}": "" for k in conceptos for a in agrupaciones}


@pytest.mark.django_db
def test_grupos_validos_se_guardan_y_los_invalidos_no_guardan_nada():
    c = instalar_hasta_grupos()
    for nombres in (("Primaria",), ("Primaria", " primaria "), ("Árbol", "arbol"), ("Primaria", "x" * 101)):
        assert enviar_grupos(c, *nombres).status_code == 200
        assert not Agrupacion.objects.exists()
    assert enviar_grupos(c, "Primaria", "<b>Secundaria</b>").url == reverse("asistente:conceptos")
    assert set(Agrupacion.objects.values_list("nombre", flat=True)) == {"Primaria", "<b>Secundaria</b>"}
    assert AvanceAsistente.objects.get().estado["por_grupo"] is True
    pagina = c.get(reverse("asistente:conceptos")).content.decode()
    assert "&lt;b&gt;Secundaria&lt;/b&gt;" in pagina and "<b>Secundaria</b>" not in pagina


@pytest.mark.django_db
def test_importes_por_grupo_guardan_tarifas_exactas_y_no_tocan_el_concepto():
    c = instalar_hasta_grupos()
    enviar_grupos(c, "Primaria", "Secundaria")
    conceptos, agrupaciones, datos = casillas(c)
    antes = {k.pk: k.importe_centavos for k in conceptos}
    primero = conceptos[0]
    datos[f"importe_{primero.pk}_{agrupaciones[0].pk}"] = "1,500.50"
    datos[f"importe_{primero.pk}_{agrupaciones[1].pk}"] = "1800"
    datos["importe_9999_1"] = "5"
    datos[f"importe_{primero.pk}_9999"] = "5"
    assert c.post(reverse("asistente:conceptos"), datos).url == reverse("asistente:pago")
    assert {(t.agrupacion_id, t.importe_centavos) for t in TarifaAgrupacion.objects.all()} == {(agrupaciones[0].pk, 150050), (agrupaciones[1].pk, 180000)}
    assert {k.pk: k.importe_centavos for k in ConceptoCobro.objects.all()} == antes


@pytest.mark.django_db
@pytest.mark.parametrize("malo", ["0", "-5", "mucho", "9" * 19])
def test_una_casilla_invalida_no_guarda_ninguna(malo):
    c = instalar_hasta_grupos()
    enviar_grupos(c, "Primaria", "Secundaria")
    conceptos, agrupaciones, datos = casillas(c)
    datos[f"importe_{conceptos[0].pk}_{agrupaciones[0].pk}"] = "100"
    datos[f"importe_{conceptos[0].pk}_{agrupaciones[1].pk}"] = malo
    assert c.post(reverse("asistente:conceptos"), datos).status_code == 200
    assert not TarifaAgrupacion.objects.exists()


@pytest.mark.django_db
def test_igual_para_todos_repinta_sin_guardar_y_pasar_a_no_borra_las_tarifas():
    c = instalar_hasta_grupos()
    enviar_grupos(c, "Primaria", "Secundaria")
    conceptos, agrupaciones, datos = casillas(c)
    datos[f"importe_{conceptos[0].pk}_{agrupaciones[0].pk}"] = "700"
    respuesta = c.post(reverse("asistente:conceptos"), {**datos, "igual": str(conceptos[0].pk)})
    assert respuesta.status_code == 200 and respuesta.content.decode().count('value="700"') == 2
    assert not TarifaAgrupacion.objects.exists()
    c.post(reverse("asistente:conceptos"), {**datos, f"importe_{conceptos[0].pk}_{agrupaciones[1].pk}": "700"})
    assert TarifaAgrupacion.objects.count() == 2
    assert enviar_grupos(c, por_grupo="no").url == reverse("asistente:conceptos")
    assert not TarifaAgrupacion.objects.exists() and Agrupacion.objects.count() == 2
    sin_grupos = {f"importe_{k.pk}": "100" for k in conceptos}
    assert c.post(reverse("asistente:conceptos"), sin_grupos).url == reverse("asistente:pago")
    assert not TarifaAgrupacion.objects.exists() and ConceptoCobro.objects.get(pk=conceptos[0].pk).importe_centavos == 10000


@pytest.mark.django_db
def test_con_el_negocio_sin_configurar_un_equipo_nuevo_desplaza_al_pendiente_mas_viejo():
    c = instalar_hasta_grupos()
    ligado = AvanceAsistente.objects.get().dispositivo
    for n in range(parametro("maximo_equipos_pendientes") - 1):
        Dispositivo.objects.create(hash_credencial=f"{n:064d}", codigo="ABC123")
    assert Dispositivo.objects.filter(estado=Dispositivo.PENDIENTE).count() == parametro("maximo_equipos_pendientes")
    assert Client().get(reverse("asistente:inicio")).status_code == 200
    assert Dispositivo.objects.filter(pk=ligado.pk).exists() and c.get(reverse("asistente:grupos")).status_code == 200
    Negocio.objects.filter(pk=1).update(configurado=True)
    Dispositivo.objects.create(hash_credencial="f" * 64, codigo="ABC123")
    assert Client().get(reverse("entrar")).status_code == 403


@pytest.mark.django_db
def test_al_terminar_un_paso_se_guarda_el_siguiente_aunque_no_se_abra():
    c = instalar_hasta_grupos()
    c.post(reverse("asistente:marca"), {"omitir": "1"})
    c.post(reverse("asistente:personalizar"), {"titular": "Socio", "titulares": "Socios", "matricula": "Número", "agrupacion": "Grupo", "agrupaciones": "Grupos", "familia": "Cuenta", "familias": "Cuentas", "seguir": "continuar"})
    c.cookies.pop(settings.SESSION_COOKIE_NAME, None)
    assert c.get(reverse("asistente:inicio")).url == reverse("asistente:grupos")
