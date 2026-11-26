import itertools
from datetime import datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from cobros import libro
from cobros.models import CancelacionCargo, Cargo, ConceptoCobro, Prorroga
from configuracion import trabajador
from configuracion.models import Negocio, Parametro, parametro
from configuracion.moneda import formatear
from licencias import cliente as cliente_central
from licencias import servicios as licencias
from licencias.models import Instalacion
from mensajes import variables
from mensajes.models import Envio, PlantillaMensaje
from pruebas.conftest import cliente
from pruebas.libro_ayudas import preparar_conceptos, titular_activo
from selladas.mensajes_producto.test_mensajes_producto import ENVIAR, CentralFalso
from selladas.producto.test_licencia_producto import central, hora, licencia, local  # noqa: F401  fixtures de la fase 12
from selladas.producto.test_vuelta2_producto import carga_de
from titulares.models import Agrupacion, CampoContacto, Contacto, Titular

ZONA = ZoneInfo("America/Mexico_City")
PARAMETROS = ("avisos_hora_inicio", "avisos_hora_fin", "avisos_maximo_semana", "avisos_dias_sin_envio")
TELEFONOS = itertools.count(10)
TODOS = "Hola [nombre], [alumno] debe [concepto] por [importe] desde el [fecha], hace [dias] días. Adeudo: [adeudo]. Atentamente, [negocio]."


class Central(CentralFalso):
    perder_respuesta = False

    def responder(self, ruta, datos):
        if ruta == "/v1/mensajes/estado":
            self.plantillas = [
                {"clave": p.clave, "nombre": p.nombre, "texto": p.texto, "con_documento": p.con_documento, "estado": p.estado, "motivo": p.motivo}
                for p in PlantillaMensaje.objects.exclude(estado=PlantillaMensaje.BORRADOR)
            ]
        respuesta = super().responder(ruta, datos)
        if ruta == ENVIAR and self.perder_respuesta:
            raise cliente_central.SinConexion("Central recibió el envío pero la respuesta se perdió")
        return respuesta

    def datos(self):
        return [carga_de(cuerpo)["datos"] for cuerpo in self.envios()]

    def destinos(self):
        return [d["destino"] for d in self.datos()]


class RelojNegocio:
    def __init__(self, monkeypatch, hora):
        real = timezone.now
        hoy = timezone.localtime(real(), ZONA).date()
        self.dia = hoy + timedelta(days=(2 - hoy.weekday()) % 7 or 7)
        self.hora = hora
        self.actual = None
        monkeypatch.setattr(timezone, "now", lambda: self.actual or real())
        self.ir()

    def ir(self, dias=0, hh=10, mm=0):
        self.actual = datetime.combine(self.dia + timedelta(days=dias), time(hh, mm), tzinfo=ZONA)
        self.hora.momento = self.actual
        return self.actual

    def fecha(self, dias):
        return self.dia + timedelta(days=dias)


@pytest.fixture
def falso(central, hora, monkeypatch):
    simulado = Central(central, hora)
    monkeypatch.setattr(cliente_central, "enviar", simulado)
    return simulado


@pytest.fixture
def gente(personas):
    preparar_conceptos()
    return personas


@pytest.fixture
def whatsapp(central, hora, local, falso, gente):
    licencias.instalar(licencia(central, local.huella, hora.momento))
    Instalacion.objects.update(activada=True)
    PlantillaMensaje.objects.filter(clave__in=["recibo", "recordatorio", "atraso", "sin_acceso"]).update(estado=PlantillaMensaje.APROBADA)
    return falso


@pytest.fixture
def reloj(whatsapp, monkeypatch, hora):
    return RelojNegocio(monkeypatch, hora)


def persona(gente, nombre, acepta=True, baja=False, con_telefono=True, agrupacion=None):
    titular = titular_activo(gente["op"], gente["sup"], nombre, iniciales=())
    if agrupacion is not None:
        Titular.objects.filter(pk=titular.pk).update(agrupacion=agrupacion)
        titular.refresh_from_db()
    final = f"{next(TELEFONOS):04d}"
    campo = CampoContacto.objects.get(tipo=CampoContacto.TELEFONO)
    contacto = titular.contactos.get(principal=True)
    Contacto.objects.filter(pk=contacto.pk).update(
        nombre=f"Contacto de {nombre}",
        valores={str(campo.pk): f"55 1234 {final}"} if con_telefono else {},
        acepta_whatsapp=acepta,
        baja_whatsapp=baja,
    )
    contacto.refresh_from_db()
    return SimpleNamespace(titular=titular, contacto=contacto, destino=f"+52551234{final}")


def cargo(titular, vence, importe=125000, concepto="Colegiatura"):
    return libro.crear_cargo(titular, ConceptoCobro.objects.get(nombre=concepto), importe, vence, Cargo.MANUAL, descripcion=f"{concepto} de prueba")


def aviso(momento, dias, clave, activo=True, agrupaciones=()):
    from mensajes.models import Aviso

    creado = Aviso.objects.create(
        momento=momento,
        dias=dias,
        plantilla=PlantillaMensaje.objects.get(clave=clave),
        activo=activo,
        activado=timezone.now() if activo else None,
    )
    creado.agrupaciones.set(agrupaciones)
    return creado


def ciclo(reloj):
    from mensajes import avisos

    return avisos.ejecutar(ahora=reloj.actual)


def clave(un_aviso, un_cargo):
    return f"aviso-{un_aviso.pk}-{un_cargo.pk}"


def fijar(clave_parametro, valor):
    Parametro.objects.update_or_create(clave=clave_parametro, defaults={"valor": valor})


def foto_de_avisos():
    from mensajes.models import Aviso

    return (
        [(a.pk, a.activo, a.momento, a.dias, a.plantilla_id, a.activado, sorted(a.agrupaciones.values_list("pk", flat=True))) for a in Aviso.objects.order_by("pk")],
        [parametro(c) for c in PARAMETROS],
        sorted(Parametro.objects.filter(clave__in=PARAMETROS).values_list("clave", "valor")),
    )


def test_1_sin_permiso_las_cuatro_rutas_se_niegan_y_nada_cambia(whatsapp, gente):
    blanco = aviso("atraso", 5, "atraso", activo=False)
    rutas = [reverse("mensajes:avisos"), reverse("mensajes:aviso_nuevo"), reverse("mensajes:aviso", args=[blanco.pk]), reverse("mensajes:faltan")]
    limites = {"accion": "limites", "avisos_hora_inicio": "00:00", "avisos_hora_fin": "23:59", "avisos_maximo_semana": "14", "avisos_dias_sin_envio": ""}
    antes = foto_de_avisos()
    for quien in ("op", "sup"):
        assert "administrar_mensajes" not in gente[quien].rol.permisos()
        c = cliente(gente[quien])
        for ruta in rutas:
            assert c.get(ruta).status_code == 403, (quien, ruta)
        for ruta, datos in [
            (rutas[0], limites),
            (rutas[1], limites),
            (rutas[2], {"accion": "activar"}),
            (rutas[2], {"accion": "desactivar"}),
            (rutas[2], {"accion": "borrar"}),
            (rutas[3], {"accion": "limites"}),
        ]:
            assert c.post(ruta, datos).status_code == 403, (quien, ruta, datos)
    assert foto_de_avisos() == antes
    direccion = cliente(gente["dir"])
    assert all(direccion.get(ruta).status_code == 200 for ruta in rutas)


def test_2_plantilla_no_aprobada_o_con_documento_no_activa_ni_envia(reloj, whatsapp, gente):
    from mensajes.models import Aviso

    direccion = cliente(gente["dir"])
    atrasado = aviso("atraso", 5, "atraso", activo=False)
    url = reverse("mensajes:aviso", args=[atrasado.pk])

    PlantillaMensaje.objects.filter(clave="atraso").update(estado=PlantillaMensaje.EN_REVISION)
    assert direccion.post(url, {"accion": "activar"}).status_code < 500
    assert not Aviso.objects.get(pk=atrasado.pk).activo

    PlantillaMensaje.objects.filter(clave="atraso").update(estado=PlantillaMensaje.APROBADA, con_documento=True)
    assert direccion.post(url, {"accion": "activar"}).status_code < 500
    assert not Aviso.objects.get(pk=atrasado.pk).activo

    PlantillaMensaje.objects.filter(clave="atraso").update(con_documento=False)
    assert direccion.post(url, {"accion": "activar"}).status_code < 500
    assert Aviso.objects.get(pk=atrasado.pk).activo

    ana = persona(gente, "Ana")
    cargo(ana.titular, reloj.fecha(-6))
    PlantillaMensaje.objects.filter(clave="atraso").update(estado=PlantillaMensaje.EN_REVISION)
    assert ciclo(reloj) == 0
    assert ENVIAR not in whatsapp.rutas() and not Envio.objects.exists()

    PlantillaMensaje.objects.filter(clave="atraso").update(estado=PlantillaMensaje.APROBADA)
    assert ciclo(reloj) == 1
    assert whatsapp.destinos() == [ana.destino]


def test_3_sin_consentimiento_con_baja_o_sin_telefono_no_se_llama_a_central(reloj, whatsapp, gente):
    atrasado = aviso("atraso", 5, "atraso")
    sin_permiso = persona(gente, "Ana", acepta=False)
    dado_de_baja = persona(gente, "Beto", baja=True)
    sin_telefono = persona(gente, "Carla", con_telefono=False)
    for alguien in (sin_permiso, dado_de_baja, sin_telefono):
        cargo(alguien.titular, reloj.fecha(-6))

    assert ciclo(reloj) == 0
    assert ENVIAR not in whatsapp.rutas()
    assert not Envio.objects.filter(aviso=atrasado).exists()

    Contacto.objects.filter(pk=sin_permiso.contacto.pk).update(acepta_whatsapp=True)
    assert ciclo(reloj) == 1
    assert whatsapp.destinos() == [sin_permiso.destino]


def test_4_un_solo_envio_por_aviso_y_cargo_y_el_incierto_repite_la_clave(reloj, whatsapp, gente):
    atrasado = aviso("atraso", 5, "atraso")
    ana = persona(gente, "Ana")
    de_ana = cargo(ana.titular, reloj.fecha(-6))

    ciclo(reloj)
    reloj.ir(hh=11)
    ciclo(reloj)
    assert [d["clave_envio"] for d in whatsapp.datos()] == [clave(atrasado, de_ana)]
    assert list(Envio.objects.filter(aviso=atrasado).values_list("cargo", "estado")) == [(de_ana.pk, Envio.ACEPTADO)]

    beto = persona(gente, "Beto")
    de_beto = cargo(beto.titular, reloj.fecha(-7))
    whatsapp.perder_respuesta = True
    ciclo(reloj)
    assert Envio.objects.get(aviso=atrasado, cargo=de_beto).estado == Envio.INCIERTO
    whatsapp.perder_respuesta = False
    reloj.ir(hh=12)
    ciclo(reloj)
    reloj.ir(hh=13)
    ciclo(reloj)
    claves_de_beto = [d["clave_envio"] for d in whatsapp.datos() if d["destino"] == beto.destino]
    assert len(claves_de_beto) == 2 and set(claves_de_beto) == {clave(atrasado, de_beto)}
    envio = Envio.objects.get(aviso=atrasado, cargo=de_beto)
    assert envio.estado == Envio.ACEPTADO and str(envio.id_central) == whatsapp.ids[clave(atrasado, de_beto)]
    assert Envio.objects.filter(aviso=atrasado).count() == 2


def test_5_pagado_cancelado_recargo_prorroga_baja_o_interno_no_reciben_atraso(reloj, whatsapp, gente):
    atrasado = aviso("atraso", 5, "atraso")
    vencido = reloj.fecha(-6)

    pagado = persona(gente, "Ana")
    libro.registrar_pago(pagado.titular, cargo(pagado.titular, vencido).importe_final, "banco", gente["op"])

    cancelado = persona(gente, "Beto")
    del_cancelado = cargo(cancelado.titular, vencido)
    libro.cancelar_cargo(del_cancelado, del_cancelado.importe_final, CancelacionCargo.CANCELACION, "Cancelación de prueba", gente["dir"])

    con_recargo = persona(gente, "Carla")
    base = cargo(con_recargo.titular, reloj.fecha(-40))
    libro.cancelar_cargo(base, base.importe_final, CancelacionCargo.CANCELACION, "Cancelación de prueba", gente["dir"])
    libro.crear_cargo(con_recargo.titular, base.concepto, 20000, vencido, Cargo.RECARGO, cargo_base=base, fecha_recargo=vencido)

    con_prorroga = persona(gente, "Diego")
    Prorroga.objects.create(cargo=cargo(con_prorroga.titular, vencido), fecha_limite=reloj.fecha(3), motivo="Prórroga de prueba", creada_por=gente["sup"])

    de_baja = persona(gente, "Elena")
    cargo(de_baja.titular, vencido)
    Titular.objects.filter(pk=de_baja.titular.pk).update(estado=Titular.BAJA)

    interno = persona(gente, "Fausto")
    cargo(interno.titular, vencido)
    Titular.todos.filter(pk=interno.titular.pk).update(interno=True)

    deudor = persona(gente, "Gabriela")
    del_deudor = cargo(deudor.titular, vencido)

    assert ciclo(reloj) == 1
    assert whatsapp.destinos() == [deudor.destino]
    assert list(Envio.objects.filter(aviso=atrasado).values_list("cargo", flat=True)) == [del_deudor.pk]


def test_6_fuera_de_horario_o_en_dia_sin_envios_no_sale_nada(reloj, whatsapp, gente):
    atrasado = aviso("atraso", 5, "atraso")
    ana = persona(gente, "Ana")
    del_ana = cargo(ana.titular, reloj.fecha(-6))

    for dias, hh, mm, sin_envio in [(1, 8, 59, "6"), (1, 19, 0, "6"), (2, 10, 0, "4,6"), (4, 10, 0, "6")]:
        fijar("avisos_dias_sin_envio", sin_envio)
        reloj.ir(dias, hh, mm)
        assert ciclo(reloj) == 0, (dias, hh, mm, sin_envio)
    assert ENVIAR not in whatsapp.rutas() and not Envio.objects.exists()

    fijar("avisos_dias_sin_envio", "6")
    reloj.ir(5, 18, 59)
    assert ciclo(reloj) == 1
    assert [d["clave_envio"] for d in whatsapp.datos()] == [clave(atrasado, del_ana)]


def test_7_a_un_contacto_solo_le_llega_el_maximo_por_semana(reloj, whatsapp, gente):
    fijar("avisos_maximo_semana", "2")
    antes = aviso("antes", 3, "recordatorio")
    atraso_corto = aviso("atraso", 5, "atraso")
    atraso_largo = aviso("atraso", 15, "sin_acceso")
    ana = persona(gente, "Ana")
    cargo(ana.titular, reloj.fecha(2))
    cargo(ana.titular, reloj.fecha(-6))
    cargo(ana.titular, reloj.fecha(-16))
    cargo(ana.titular, reloj.fecha(-17))
    beto = persona(gente, "Beto")
    cargo(beto.titular, reloj.fecha(-6))

    ciclo(reloj)
    reloj.ir(1)
    ciclo(reloj)
    reloj.ir(2)
    ciclo(reloj)

    a_ana = Envio.objects.filter(contacto=ana.contacto, aviso__in=[antes, atraso_corto, atraso_largo]).exclude(estado=Envio.NO_ENVIADO)
    assert a_ana.count() == 2
    assert whatsapp.destinos().count(ana.destino) == 2
    assert whatsapp.destinos().count(beto.destino) == 1


def test_8_aviso_de_una_agrupacion_no_escribe_a_otra(reloj, whatsapp, gente):
    primero, segundo = Agrupacion.objects.create(nombre="Grupo uno"), Agrupacion.objects.create(nombre="Grupo dos")
    atrasado = aviso("atraso", 5, "atraso", agrupaciones=[primero])
    de_uno = persona(gente, "Ana", agrupacion=primero)
    de_dos = persona(gente, "Beto", agrupacion=segundo)
    sin_grupo = persona(gente, "Carla")
    for alguien in (de_uno, de_dos, sin_grupo):
        cargo(alguien.titular, reloj.fecha(-6))

    assert ciclo(reloj) == 1
    assert whatsapp.destinos() == [de_uno.destino]
    assert set(Envio.objects.filter(aviso=atrasado).values_list("titular", flat=True)) == {de_uno.titular.pk}


def test_9_valores_del_titular_y_cargo_correctos_y_solo_las_variables_usadas(reloj, whatsapp, gente):
    PlantillaMensaje.objects.filter(clave="atraso").update(texto=TODOS)
    PlantillaMensaje.objects.filter(clave="recordatorio").update(texto="Hola [nombre], tu saldo pendiente es de [adeudo].")
    PlantillaMensaje.objects.filter(clave="sin_acceso").update(texto="Hola [nombre], tu recibo [folio] sigue pendiente.")
    atrasado = aviso("atraso", 5, "atraso")
    antes = aviso("antes", 3, "recordatorio")
    con_folio = aviso("atraso", 15, "sin_acceso")

    ana = persona(gente, "Ana")
    del_ana = cargo(ana.titular, reloj.fecha(-20), importe=125000)
    Prorroga.objects.create(cargo=del_ana, fecha_limite=reloj.fecha(-6), motivo="Prórroga de prueba", creada_por=gente["sup"])
    libro.registrar_pago(ana.titular, 25000, "banco", gente["op"], primero=[del_ana.pk])
    cargo(ana.titular, reloj.fecha(20), importe=50000, concepto="Libros")

    beto = persona(gente, "Beto")
    cargo(beto.titular, reloj.fecha(2), importe=70000, concepto="Libros")
    cargo(beto.titular, reloj.fecha(30), importe=10000, concepto="Libros")

    carla = persona(gente, "Carla")
    del_carla = cargo(carla.titular, reloj.fecha(-16))

    ciclo(reloj)
    por_destino = {d["destino"]: d for d in whatsapp.datos()}
    assert set(por_destino) == {ana.destino, beto.destino}

    a_ana = por_destino[ana.destino]
    assert (a_ana["clave_envio"], a_ana["plantilla"]) == (clave(atrasado, del_ana), "atraso")
    assert set(a_ana["valores"]) == set(variables.usadas(TODOS))
    assert a_ana["valores"] == {
        "nombre": "Contacto de Ana",
        "alumno": ana.titular.nombre_completo,
        "concepto": "Colegiatura",
        "importe": formatear(100000),
        "fecha": reloj.fecha(-6).strftime("%d/%m/%Y"),
        "dias": "6",
        "adeudo": formatear(150000),
        "negocio": Negocio.actual().nombre,
    }

    a_beto = por_destino[beto.destino]
    assert a_beto["plantilla"] == "recordatorio" and a_beto["clave_envio"].startswith(f"aviso-{antes.pk}-")
    assert a_beto["valores"] == {"nombre": "Contacto de Beto", "adeudo": formatear(80000)}

    assert not Envio.objects.filter(aviso=con_folio).exists()
    assert clave(con_folio, del_carla) not in whatsapp.ids


def test_10_solo_consulta_omite_tope_detiene_y_no_se_escribe_por_adeudos_viejos(reloj, whatsapp, gente, monkeypatch):
    tareas = {nombre: diaria for nombre, _, diaria in trabajador.TAREAS}
    assert tareas.get("avisos") is False and "avisos" in trabajador.ESCRIBEN_DATOS
    atrasado = aviso("atraso", 5, "atraso")
    ana = persona(gente, "Ana")
    cargo(ana.titular, reloj.fecha(-6))
    beto = persona(gente, "Beto")
    cargo(beto.titular, reloj.fecha(-7))

    monkeypatch.setattr(trabajador, "TAREAS", tuple(t for t in trabajador.TAREAS if t[0] == "avisos"))
    monkeypatch.setattr(licencias, "permite_escribir", lambda: False)
    informe = trabajador.ejecutar_ciclo(reloj.dia)
    assert [(nombre, "omitida" in texto) for nombre, _, texto in informe] == [("avisos", True)]
    assert ENVIAR not in whatsapp.rutas() and not Envio.objects.exists()

    monkeypatch.setattr(licencias, "permite_escribir", lambda: True)
    whatsapp.resultado_envio = "tope"
    trabajador.ejecutar_ciclo(reloj.dia)
    assert len(whatsapp.envios()) == 1
    assert Envio.objects.filter(aviso=atrasado).exclude(estado=Envio.NO_ENVIADO).count() == 0

    whatsapp.resultado_envio = "aceptado"
    whatsapp.llamadas.clear()
    viejo = persona(gente, "Carla")
    cargo(viejo.titular, reloj.fecha(-13))
    limite = persona(gente, "Diego")
    cargo(limite.titular, reloj.fecha(-12))
    reciente = persona(gente, "Elena")
    cargo(reciente.titular, reloj.fecha(-4))
    reloj.ir(hh=11)
    ciclo(reloj)
    assert sorted(whatsapp.destinos()) == sorted([ana.destino, beto.destino, limite.destino])


def test_11_recibo_automatico_una_vez_sin_revertidos_ni_anteriores(whatsapp, gente):
    from mensajes import avisos
    from mensajes.models import Aviso

    del_pago = Aviso.objects.get(momento="pago")
    assert del_pago.plantilla.clave == "recibo" and not del_pago.activo
    anterior = persona(gente, "Ana")
    recibo_anterior = libro.registrar_pago(anterior.titular, 50000, "banco", gente["op"]).recibo

    assert cliente(gente["dir"]).post(reverse("mensajes:aviso", args=[del_pago.pk]), {"accion": "activar"}).status_code < 500
    assert Aviso.objects.get(pk=del_pago.pk).activo

    revertido = persona(gente, "Beto")
    pago_revertido = libro.registrar_pago(revertido.titular, 60000, "banco", gente["op"])
    libro.revertir_pago(pago_revertido, "Reversión de prueba", gente["dir"])
    nuevo = persona(gente, "Carla")
    recibo_nuevo = libro.registrar_pago(nuevo.titular, 70000, "banco", gente["op"]).recibo

    for _ in range(3):
        avisos.ejecutar(ahora=timezone.now())

    assert whatsapp.destinos() == [nuevo.destino]
    assert [d["plantilla"] for d in whatsapp.datos()] == ["recibo"]
    assert Envio.objects.filter(recibo=recibo_nuevo).count() == 1
    assert not Envio.objects.filter(recibo__in=[recibo_anterior, pago_revertido.recibo]).exists()
    assert Envio.objects.filter(recibo=recibo_nuevo).get().enviado_por is None
