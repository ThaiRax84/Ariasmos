import pytest
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

from auditoria.models import Evento
from banco.catalogo import leer
from banco.models import Banco, CuentaBancaria, MedioPago
from configuracion.models import Negocio
from nucleo import clabe
from titulares.servicios import crear_titular

from .conftest import cliente

CLABE_PRUEBA = "002010077777777771"


def clabe_con_prefijo(prefijo):
    cuerpo = prefijo + "180000118359"[: 17 - len(prefijo)].ljust(17 - len(prefijo), "0")
    return cuerpo + clabe.digito_verificador(cuerpo)


def datos_cuenta(**cambios):
    datos = {"clabe": CLABE_PRUEBA, "beneficiario": "Beneficiario de prueba", "referencia_en": "ambos", "contacto_dudas": "55 1234 5678", "activa": "on", "principal": "on"}
    datos.update(cambios)
    return datos


def test_clabe_invalida_rechazada_y_valida_normalizada(personas):
    c = cliente(personas["dir"])
    respuesta = c.post(reverse("banco:nueva"), datos_cuenta(clabe="002010077777777772"))
    assert respuesta.status_code == 200 and "La CLABE no es válida" in respuesta.content.decode()
    respuesta = c.post(reverse("banco:nueva"), datos_cuenta(clabe="00201007777"))
    assert "18 dígitos" in respuesta.content.decode()
    assert not CuentaBancaria.objects.exists()
    assert c.post(reverse("banco:nueva"), datos_cuenta(clabe="002-010-07777777777-1")).status_code == 302
    cuenta = CuentaBancaria.objects.get()
    assert cuenta.clabe == CLABE_PRUEBA and cuenta.clabe_formateada == "002 010 07777777777 1"
    assert cuenta.contacto_dudas == "+52 55 1234 5678"
    evento = Evento.objects.get(accion="cuenta_bancaria_creada")
    assert evento.datos["cambios"]["CLABE"] == [None, "002 010 07777777777 1"]


def test_banco_propuesto_por_prefijo(personas):
    respuesta = cliente(personas["dir"]).post(reverse("banco:nueva"), datos_cuenta(), follow=True)
    assert CuentaBancaria.objects.get().banco.clave == "002"
    assert "Banco elegido según la CLABE" in respuesta.content.decode()


def test_banco_que_no_coincide_rechazado(personas):
    otro = Banco.objects.get(clave="012")
    respuesta = cliente(personas["dir"]).post(reverse("banco:nueva"), datos_cuenta(banco=otro.pk))
    texto = respuesta.content.decode()
    assert respuesta.status_code == 200 and "La CLABE empieza con 002" in texto and "clave 012" in texto
    assert not CuentaBancaria.objects.exists()


def test_prefijo_desconocido_con_otro(personas):
    desconocido = next(p for p in (f"{n:03d}" for n in range(999, 0, -1)) if not Banco.objects.filter(clave=p).exists())
    valor = clabe_con_prefijo(desconocido)
    assert clabe.es_valida(valor)
    c = cliente(personas["dir"])
    respuesta = c.post(reverse("banco:nueva"), datos_cuenta(clabe=valor))
    assert "no está en el catálogo" in respuesta.content.decode() and not CuentaBancaria.objects.exists()
    respuesta = c.post(reverse("banco:nueva"), datos_cuenta(clabe=valor, banco_otro="Banco Regional"), follow=True)
    banco = Banco.objects.get(clave=desconocido)
    assert banco.capturado_a_mano and banco.nombre == "Banco Regional" and banco.soporte == "sin_probar"
    assert "capturado a mano" in respuesta.content.decode()
    assert Evento.objects.filter(accion="banco_capturado_a_mano").exists()


def test_una_sola_cuenta_principal(personas):
    c = cliente(personas["dir"])
    c.post(reverse("banco:nueva"), datos_cuenta())
    c.post(reverse("banco:nueva"), datos_cuenta(clabe=clabe_con_prefijo("012"), beneficiario="Segunda"))
    assert CuentaBancaria.objects.filter(principal=True).count() == 1
    assert CuentaBancaria.objects.get(principal=True).beneficiario == "Segunda"
    with pytest.raises(IntegrityError), transaction.atomic():
        CuentaBancaria.objects.create(banco=Banco.objects.get(clave="002"), clabe=CLABE_PRUEBA, beneficiario="X", principal=True)


def test_primera_cuenta_activa_queda_como_principal(personas):
    cliente(personas["dir"]).post(reverse("banco:nueva"), datos_cuenta(principal=""))
    assert CuentaBancaria.objects.get().principal


def test_cuenta_requiere_reingreso_y_permiso(personas):
    assert cliente(personas["dir"], reingreso=False).get(reverse("banco:nueva")).url.startswith(reverse("confirmar"))
    assert cliente(personas["sup"]).get(reverse("banco:lista")).status_code == 403


def test_ficha_armada_con_campos_y_sin_texto_libre(personas):
    c = cliente(personas["dir"])
    medios = MedioPago.objects.filter(nombre__in=["Transferencia SPEI", "Efectivo en caja"])
    c.post(reverse("banco:nueva"), datos_cuenta(numero_cuenta="1234 5678", convenio="CV123", medios=[m.pk for m in medios], nota_adicional="Horario de caja de 9 a 14"))
    titular = crear_titular(personas["dir"], {"nombre": "Ana", "apellidos": "Prueba"})
    ficha = c.get(reverse("titulares:ficha_pago", args=[titular.pk])).content.decode()
    for esperado in ("BANAMEX", "002 010 07777777777 1", "Beneficiario de prueba", "12345678", "CV123", "Transferencia SPEI, Efectivo en caja", "+52 55 1234 5678", "Horario de caja de 9 a 14"):
        assert esperado in ficha
    assert f"Escribe <strong>{titular.matricula}</strong> (matrícula) en referencia numérica y en concepto." in ficha
    assert "Instrucciones de prueba" not in ficha
    CuentaBancaria.objects.update(referencia_en=CuentaBancaria.NUMERICA)
    ficha = c.get(reverse("titulares:ficha_pago", args=[titular.pk])).content.decode()
    assert "(matrícula) en referencia numérica." in ficha


def test_ficha_sin_cuenta_usa_nota_conservada(personas):
    titular = crear_titular(personas["op"], {"nombre": "Ana", "apellidos": "Prueba"})
    ficha = cliente(personas["op"]).get(reverse("titulares:ficha_pago", args=[titular.pk])).content.decode()
    assert "Instrucciones de prueba" in ficha and titular.matricula in ficha


def test_cargar_bancos_idempotente(db):
    total = len(leer())
    assert Banco.objects.count() == total
    Banco.objects.filter(clave="002").update(nombre="Renombrado")
    call_command("cargar_bancos")
    call_command("cargar_bancos")
    assert Banco.objects.count() == total
    assert Banco.objects.get(clave="002").nombre == "BANAMEX"
    assert MedioPago.objects.filter(nombre="Transferencia SPEI").exists()


def test_ajustes_avanzados_bloqueados_tras_primera_matricula(personas):
    c = cliente(personas["dir"])
    assert "SPEI" in c.get(reverse("configuracion:avanzado")).content.decode()
    c.post(reverse("configuracion:avanzado"), {"longitud_matricula": 8, "sede": 2, "ranuras": 10})
    negocio = Negocio.objects.get()
    assert (negocio.longitud_matricula, negocio.sede) == (8, 2)
    crear_titular(personas["dir"], {"nombre": "A", "apellidos": "B"})
    respuesta = c.post(reverse("configuracion:avanzado"), {"longitud_matricula": 9, "sede": 3, "ranuras": 10}, follow=True)
    negocio.refresh_from_db()
    assert (negocio.longitud_matricula, negocio.sede) == (8, 2)
    assert "no se pueden cambiar" in respuesta.content.decode()
    assert cliente(personas["sup"]).get(reverse("configuracion:avanzado")).status_code == 403


def test_pantalla_de_negocio_sin_texto_libre_de_pago(personas):
    pagina = cliente(personas["dir"]).get(reverse("configuracion:negocio")).content.decode()
    assert 'name="instrucciones_pago"' not in pagina and 'name="longitud_matricula"' not in pagina


@pytest.mark.django_db(transaction=True)
def test_migracion_conserva_instrucciones_como_nota():
    ejecutor = MigrationExecutor(connection)
    ejecutor.migrate([("configuracion", "0003_codigo_activacion")])
    viejo = ejecutor.loader.project_state([("configuracion", "0003_codigo_activacion")]).apps.get_model("configuracion", "Negocio")
    viejo.objects.create(pk=1, nombre="N", instrucciones_pago="Texto anterior de pago")
    ejecutor = MigrationExecutor(connection)
    ejecutor.loader.build_graph()
    ejecutor.migrate(ejecutor.loader.graph.leaf_nodes())
    assert Negocio.objects.get(pk=1).nota_ficha == "Texto anterior de pago"
