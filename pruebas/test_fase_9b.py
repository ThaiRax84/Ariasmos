import importlib
import re
import time
from datetime import date, timedelta

import pytest
from django.apps import apps as registro
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from auditoria.models import Evento
from caja.models import Caja
from caja.servicios import abrir_turno
from cobros import generacion, libro
from cobros.models import Cargo, CancelacionCargo, ConceptoCobro, Pago, Prorroga
from configuracion import esquema, plantillas
from configuracion.models import Parametro, hoy_negocio, parametro
from cortes import servicios as cortes
from cuentas.models import PermisoRol, Rol
from inventario import servicios as inventario
from inventario.models import Articulo, Conteo, Venta
from rezagos import calculo, presentacion
from rezagos.models import ExcepcionLimite, LimiteAdeudo, ReglaRezago
from solicitudes import motor
from solicitudes.models import PoliticaAccion, Solicitud
from tarifas import periodos
from tarifas.models import OpcionConcepto, OrigenCargo, TarifaAgrupacion
from titulares.models import Agrupacion, MotivoBaja, Titular

from .conftest import cliente, configurar, nuevo_usuario
from .libro_ayudas import preparar_conceptos, titular_activo


def fijar(clave, valor):
    Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})


@pytest.fixture
def base(personas):
    preparar_conceptos()
    return personas


def activo(personas, nombre, agrupacion=None):
    titular = titular_activo(personas["op"], personas["sup"], nombre, iniciales=())
    if agrupacion is not None:
        Titular.objects.filter(pk=titular.pk).update(agrupacion=agrupacion)
        titular.refresh_from_db()
    return titular


def deuda(titular, dias, importe=10000, concepto="Extras"):
    return libro.crear_cargo(titular, ConceptoCobro.objects.get(nombre=concepto), importe, hoy_negocio() - timedelta(days=dias), Cargo.MANUAL)


def limite(modo_importe="ilimitado", importe=0, modo_dias="ilimitado", dias=0):
    LimiteAdeudo.objects.update_or_create(pk=1, defaults={"modo_importe": modo_importe, "importe_maximo": importe, "modo_dias": modo_dias, "dias_maximos": dias})


def turno_de(usuario):
    return abrir_turno(usuario, Caja.objects.get_or_create(nombre="Caja 1")[0], 0)


def regla(**campos):
    datos = {"nombre": "Regla", "texto": "Con atraso"}
    datos.update(campos)
    return ReglaRezago.objects.create(**datos)


def test_periodos_por_periodicidad():
    assert periodos.periodo_de("semanal", date(2026, 11, 18)) == (date(2026, 11, 16), date(2026, 11, 22))
    assert periodos.periodo_de("quincenal", date(2026, 2, 20)) == (date(2026, 2, 16), date(2026, 2, 28))
    assert periodos.periodo_de("bimestral", date(2026, 4, 5)) == (date(2026, 3, 1), date(2026, 4, 30))
    assert periodos.periodo_de("anual", date(2026, 7, 1)) == (date(2026, 1, 1), date(2026, 12, 31))
    assert periodos.limites("mensual", "2026-03") == (date(2026, 3, 1), date(2026, 3, 31))
    assert periodos.limites("semanal", "2025-S53") is None
    assert periodos.limites("semanal", "2020-S53") == (date(2020, 12, 28), date(2021, 1, 3))
    assert periodos.limites("quincenal", "2026-02-2") == (date(2026, 2, 16), date(2026, 2, 28))
    assert periodos.limites("mensual", "basura") is None


def test_tarifa_por_agrupacion_y_solo_con_tarifa_en_los_cargos_automaticos(base):
    a, b = Agrupacion.objects.create(nombre="Primero A"), Agrupacion.objects.create(nombre="Segundo B")
    colegiatura = ConceptoCobro.objects.get(nombre="Colegiatura")
    TarifaAgrupacion.objects.create(concepto=colegiatura, agrupacion=a, importe_centavos=300000)
    TarifaAgrupacion.objects.create(concepto=colegiatura, agrupacion=b, importe_centavos=999, activa=False)
    con_tarifa, inactiva, sin_grupo = activo(base, "Ana", a), activo(base, "Beto", b), activo(base, "Caro")
    generacion.generar_recurrentes(hoy=date(2026, 1, 15))
    importes = {c.titular_id: c.importe_original for c in Cargo.objects.filter(concepto=colegiatura)}
    assert importes == {con_tarifa.pk: 300000, inactiva.pk: 250000, sin_grupo.pk: 250000}
    assert OrigenCargo.objects.get(cargo__titular=con_tarifa).tarifa.agrupacion == a
    assert OrigenCargo.objects.get(cargo__titular=sin_grupo).tarifa is None
    OpcionConcepto.objects.create(concepto=colegiatura, solo_con_tarifa=True)
    generacion.generar_recurrentes(hoy=date(2026, 2, 15))
    febrero = set(Cargo.objects.filter(concepto=colegiatura, periodo="2026-02").values_list("titular_id", flat=True))
    assert febrero == {con_tarifa.pk}


def test_tarifa_con_periodicidad_propia_y_cambio_de_agrupacion_desde_el_siguiente_periodo(base):
    mensual, semanal = Agrupacion.objects.create(nombre="Mensual"), Agrupacion.objects.create(nombre="Semanal")
    colegiatura = ConceptoCobro.objects.get(nombre="Colegiatura")
    TarifaAgrupacion.objects.create(concepto=colegiatura, agrupacion=mensual, importe_centavos=200000)
    TarifaAgrupacion.objects.create(concepto=colegiatura, agrupacion=semanal, importe_centavos=50000, periodicidad="semanal", dia_vencimiento=5)
    ana = activo(base, "Ana", mensual)
    generacion.generar_recurrentes(hoy=date(2026, 1, 20))
    enero = Cargo.objects.get(titular=ana, concepto=colegiatura)
    assert (enero.periodo, enero.importe_original) == ("2026-01", 200000)
    Titular.objects.filter(pk=ana.pk).update(agrupacion=semanal)
    generacion.generar_recurrentes(hoy=date(2026, 2, 14))
    cargos = list(Cargo.objects.filter(titular=ana, concepto=colegiatura).order_by("vencimiento"))
    assert cargos[0].pk == enero.pk and cargos[0].importe_original == 200000
    semanas = cargos[1:]
    assert [c.periodo for c in semanas] == ["2026-S06", "2026-S07"]
    assert all(c.importe_original == 50000 and c.vencimiento.weekday() == 4 for c in semanas)
    assert all(OrigenCargo.objects.get(cargo=c).inicio >= date(2026, 2, 1) for c in semanas)
    Titular.objects.filter(pk=ana.pk).update(agrupacion=mensual)
    generacion.generar_recurrentes(hoy=date(2026, 3, 20))
    nuevos = Cargo.objects.filter(titular=ana, concepto=colegiatura, periodo__regex=r"^\d{4}-\d{2}$").values_list("periodo", flat=True)
    assert sorted(nuevos) == ["2026-01", "2026-03"]


def test_cargo_de_alta_toma_la_tarifa_de_su_agrupacion(base):
    grupo = Agrupacion.objects.create(nombre="Avanzado")
    inscripcion = ConceptoCobro.objects.get(nombre="Inscripción")
    TarifaAgrupacion.objects.create(concepto=inscripcion, agrupacion=grupo, importe_centavos=70000)
    from titulares.servicios import crear_titular

    nuevo = crear_titular(base["op"], {"nombre": "Dora", "apellidos": "Prueba", "agrupacion": grupo}, contacto={"nombre": "Resp", "valores": {}}, conceptos=[inscripcion])
    motor.ejecutar("alta", base["sup"], nuevo)
    assert Cargo.objects.get(titular=nuevo, concepto=inscripcion).importe_original == 70000


def _cargo_manual(usuario, titular, concepto, cantidad, unitario=""):
    return cliente(usuario).post(reverse("cobros:cargo_manual", args=[titular.pk]), {"concepto": concepto.pk, "cantidad": cantidad, "importe_unitario": unitario})


def test_cargo_por_cantidad_con_tarifa_se_calcula_en_el_servidor(base):
    grupo = Agrupacion.objects.create(nombre="Tercero")
    libros = ConceptoCobro.objects.get(nombre="Libros")
    assert OpcionConcepto.objects.get(concepto=libros).por_cantidad
    TarifaAgrupacion.objects.create(concepto=libros, agrupacion=grupo, importe_centavos=12000)
    ana = activo(base, "Ana", grupo)
    assert _cargo_manual(base["op"], ana, libros, 3).status_code == 302
    cargo = Cargo.objects.get(titular=ana, concepto=libros)
    assert (cargo.cantidad, cargo.importe_original, cargo.importe_original // cargo.cantidad, cargo.descripcion) == (3, 36000, 12000, "Libros × 3")
    for malo in (31, 0, -2, "dos", "3.5", ""):
        respuesta = _cargo_manual(base["op"], ana, libros, malo)
        assert respuesta.status_code == 200, malo
    assert Cargo.objects.filter(titular=ana, concepto=libros).count() == 1
    rechazo = _cargo_manual(base["op"], ana, libros, 2, "1.00")
    assert rechazo.status_code == 200 and "permiso de ajustes" in rechazo.content.decode()
    assert _cargo_manual(base["dir"], ana, libros, 2, "1.00").status_code == 302
    assert Cargo.objects.filter(titular=ana, concepto=libros).order_by("-id").first().importe_original == 200
    extras = ConceptoCobro.objects.get(nombre="Extras")
    extras.importe_centavos = 5000
    extras.save()
    OpcionConcepto.objects.create(concepto=extras, por_cantidad=False)
    assert _cargo_manual(base["op"], ana, extras, 2).status_code == 302
    assert Cargo.objects.filter(titular=ana, concepto=extras).get().cantidad == 1


def test_concepto_solo_con_tarifa_no_se_carga_sin_tarifa(base):
    libros = ConceptoCobro.objects.get(nombre="Libros")
    OpcionConcepto.objects.filter(concepto=libros).update(solo_con_tarifa=True)
    ana = activo(base, "Ana")
    respuesta = _cargo_manual(base["op"], ana, libros, 1)
    assert respuesta.status_code == 200 and "solo se cobra con tarifa" in respuesta.content.decode()


def test_pantallas_de_tarifas_guardan_con_bitacora(base):
    grupo = Agrupacion.objects.create(nombre="Cuarto")
    libros = ConceptoCobro.objects.get(nombre="Libros")
    c = cliente(base["sup"])
    assert c.get(reverse("tarifas:indice")).status_code == 200
    assert c.post(reverse("tarifas:nueva", args=[libros.pk]), {"agrupacion": grupo.pk, "importe_centavos": "150.00", "activa": "on"}).status_code == 302
    tarifa = TarifaAgrupacion.objects.get(concepto=libros, agrupacion=grupo)
    assert tarifa.importe_centavos == 15000 and tarifa.periodicidad == ""
    assert c.post(reverse("tarifas:editar", args=[tarifa.pk]), {"importe_centavos": "175.00", "activa": "on"}).status_code == 302
    evento = Evento.objects.filter(accion="tarifa_cambiada").latest("numero")
    assert evento.datos["antes"]["importe"] == 15000 and evento.datos["despues"]["importe"] == 17500
    assert c.post(reverse("tarifas:nueva", args=[libros.pk]), {"agrupacion": grupo.pk, "importe_centavos": "1.00", "activa": "on"}).status_code == 200
    assert c.post(reverse("tarifas:nueva", args=[libros.pk]), {"agrupacion": Agrupacion.objects.create(nombre="Quinto").pk, "importe_centavos": "0", "activa": "on"}).status_code == 200
    assert c.post(reverse("tarifas:concepto", args=[libros.pk]), {"por_cantidad": "on", "cantidad_maxima": "12"}).status_code == 302
    assert OpcionConcepto.objects.get(concepto=libros).cantidad_maxima == 12
    assert Evento.objects.filter(accion="opciones_concepto_cambiadas").exists()
    assert c.post(reverse("tarifas:concepto", args=[libros.pk]), {"por_cantidad": "on", "cantidad_maxima": "100000"}).status_code == 200
    colegiatura = ConceptoCobro.objects.get(nombre="Colegiatura")
    assert c.post(reverse("tarifas:nueva", args=[colegiatura.pk]), {"agrupacion": grupo.pk, "importe_centavos": "10", "periodicidad": "semanal", "dia_vencimiento": "9", "activa": "on"}).status_code == 200
    assert cliente(base["op"]).get(reverse("tarifas:indice")).status_code == 403


def test_recargos_tras_el_alta(base):
    assert parametro("recargos_tras_alta") == "siguiente_periodo"
    ana = activo(base, "Ana")
    Titular.objects.filter(pk=ana.pk).update(activo_desde=date(2026, 3, 20))
    Parametro.objects.filter(clave="dia_generacion_cargos").delete()
    generacion.generar_recurrentes(hoy=date(2026, 4, 20))
    marzo = Cargo.objects.get(titular=ana, periodo="2026-03", origen=Cargo.AUTOMATICO)
    abril = Cargo.objects.get(titular=ana, periodo="2026-04", origen=Cargo.AUTOMATICO)
    generacion.generar_recargos(hoy=date(2026, 4, 20))
    assert not Cargo.objects.filter(cargo_base=marzo).exists() and Cargo.objects.filter(cargo_base=abril).exists()
    inicial = libro.crear_cargo(ana, ConceptoCobro.objects.get(nombre="Colegiatura"), 1000, date(2026, 3, 25), Cargo.SALDO_INICIAL)
    generacion.generar_recargos(hoy=date(2026, 4, 20))
    assert Cargo.objects.filter(cargo_base=inicial).exists()
    fijar("recargos_tras_alta", "desde_alta")
    generacion.generar_recargos(hoy=date(2026, 4, 20))
    assert Cargo.objects.filter(cargo_base=marzo).exists()


def test_reactivar_cuenta_como_alta_nueva(base):
    ana = activo(base, "Ana")
    motivo = MotivoBaja.objects.first()
    motor.ejecutar("baja", base["sup"], ana, {"motivo": motivo.pk})
    motor.ejecutar("reactivacion", base["sup"], ana)
    ana.refresh_from_db()
    assert ana.activo_desde == hoy_negocio()
    colegiatura = ConceptoCobro.objects.get(nombre="Colegiatura")
    nuevo = libro.crear_cargo(ana, colegiatura, 1000, hoy_negocio().replace(day=1), Cargo.MANUAL)
    vencido_antes = libro.crear_cargo(ana, colegiatura, 1000, (hoy_negocio().replace(day=1) - timedelta(days=40)), Cargo.MANUAL)
    from rezagos import tras_alta

    evaluar = tras_alta.evaluador()
    assert evaluar(Cargo.objects.select_related("titular", "concepto").get(pk=nuevo.pk))
    assert not evaluar(Cargo.objects.select_related("titular", "concepto").get(pk=vencido_antes.pk))


def test_pantalla_de_recargos_tras_alta(base):
    c = cliente(base["sup"])
    assert c.post(reverse("rezagos:recargos_alta"), {"recargos_tras_alta": "desde_alta"}).status_code == 302
    assert parametro("recargos_tras_alta") == "desde_alta"
    assert Evento.objects.filter(accion="recargos_tras_alta_cambiado").exists()
    assert c.post(reverse("rezagos:recargos_alta"), {"recargos_tras_alta": "otro"}).status_code == 200
    assert cliente(base["op"]).post(reverse("rezagos:recargos_alta"), {"recargos_tras_alta": "siguiente_periodo"}).status_code == 403


def test_limite_ilimitado_de_fabrica_y_por_valor(base):
    ana, beto = activo(base, "Ana"), activo(base, "Beto")
    deuda(ana, 40, 50000)
    deuda(beto, 3, 900)
    assert LimiteAdeudo.actual().modo_importe == "ilimitado" and calculo.evaluar() == {}
    limite("valor", 1000)
    situaciones = calculo.evaluar()
    assert set(situaciones) == {ana.pk} and situaciones[ana.pk].rebasa_importe and situaciones[ana.pk].sin_credito
    limite("ilimitado", 0, "valor", 30)
    situaciones = calculo.evaluar()
    assert set(situaciones) == {ana.pk} and situaciones[ana.pk].rebasa_dias and situaciones[ana.pk].dias == 40
    limite("valor", 0, "valor", 0)
    assert set(calculo.evaluar()) == {ana.pk, beto.pk}


def test_excepciones_por_titular(base):
    ana = activo(base, "Ana")
    deuda(ana, 40, 50000)
    limite("valor", 1000, "valor", 10)
    excepcion = ExcepcionLimite.objects.create(titular=ana, modo_importe="ilimitado", modo_dias="negocio", motivo="Acuerdo", creada_por=base["dir"])
    situacion = calculo.de(ana)
    assert not situacion.rebasa_importe and situacion.rebasa_dias
    ExcepcionLimite.objects.filter(pk=excepcion.pk).update(modo_dias="valor", dias_maximos=60)
    assert calculo.de(ana) is None
    ExcepcionLimite.objects.filter(pk=excepcion.pk).update(vigente_hasta=hoy_negocio() - timedelta(days=1))
    assert calculo.de(ana).rebasa


def test_prorroga_cuenta_para_el_atraso(base):
    ana = activo(base, "Ana")
    cargo = deuda(ana, 40, 5000)
    limite("ilimitado", 0, "valor", 10)
    assert calculo.de(ana).dias == 40
    Prorroga.objects.create(cargo=cargo, fecha_limite=hoy_negocio() + timedelta(days=5), motivo="Acuerdo", creada_por=base["sup"])
    assert calculo.de(ana) is None


def test_pantallas_de_limites_y_excepcion_con_bitacora_y_aviso_a_quien_audita(base):
    ana = activo(base, "Ana")
    c = cliente(base["sup"])
    assert c.post(reverse("rezagos:limites"), {"modo_importe": "valor", "importe_maximo": "", "modo_dias": "ilimitado"}).status_code == 200
    assert c.post(reverse("rezagos:limites"), {"modo_importe": "valor", "importe_maximo": "1500.00", "modo_dias": "ilimitado", "dias_maximos": ""}).status_code == 302
    actual = LimiteAdeudo.actual()
    assert (actual.modo_importe, actual.importe_maximo, actual.modo_dias) == ("valor", 150000, "ilimitado")
    evento = Evento.objects.get(accion="limites_adeudo_cambiados")
    assert evento.datos["antes"]["modo_importe"] == "ilimitado" and evento.datos["despues"]["importe_maximo"] == 150000
    assert c.post(reverse("rezagos:excepcion", args=[ana.pk]), {"modo_importe": "ilimitado", "modo_dias": "negocio", "motivo": ""}).status_code == 200
    assert c.post(reverse("rezagos:excepcion", args=[ana.pk]), {"modo_importe": "ilimitado", "modo_dias": "negocio", "motivo": "Beca de transporte"}).status_code == 302
    assert ExcepcionLimite.objects.get(titular=ana).modo_importe == "ilimitado"
    assert Evento.objects.filter(accion="excepcion_limite_guardada", titular=ana.pk).exists()
    inicio = cliente(base["dir"]).get(reverse("inicio")).content.decode()
    assert "Cambios en los límites de adeudo" in inicio and "Ilimitado" in inicio
    assert "Cambios en los límites de adeudo" not in cliente(base["sup"]).get(reverse("inicio")).content.decode()
    assert c.post(reverse("rezagos:excepcion", args=[ana.pk]), {"quitar": "on"}).status_code == 302
    assert not ExcepcionLimite.objects.filter(titular=ana).exists()
    assert cliente(base["op"]).get(reverse("rezagos:limites")).status_code == 403


def test_rezagado_paga_consulta_y_genera_cargos_automaticos(base):
    ana = activo(base, "Ana")
    deuda(ana, 40, 50000)
    limite("valor", 0)
    assert calculo.sin_credito(ana)
    turno = turno_de(base["op"])
    pago = libro.registrar_pago(ana, 20000, Pago.EFECTIVO, base["op"], turno=turno)
    assert pago.aplicaciones.exists()
    op = cliente(base["op"])
    assert op.get(reverse("cobros:cobrar", args=[ana.pk])).status_code == 200
    assert op.get(reverse("titulares:estado_pdf", args=[ana.pk])).status_code == 200
    assert op.get(reverse("titulares:detalle", args=[ana.pk])).status_code == 200
    antes = Cargo.objects.filter(titular=ana, origen=Cargo.AUTOMATICO).count()
    generacion.generar_recurrentes(hoy=hoy_negocio())
    assert Cargo.objects.filter(titular=ana, origen=Cargo.AUTOMATICO).count() > antes
    total = sum(c.saldo for c in libro.con_saldo(Cargo.objects.filter(titular=ana)))
    libro.registrar_pago(ana, total, Pago.EFECTIVO, base["op"], turno=turno)
    assert calculo.de(ana) is None


def test_sin_credito_el_cargo_manual_pasa_a_solicitud(base):
    ana = activo(base, "Ana")
    deuda(ana, 40, 50000)
    limite("valor", 0)
    libros = ConceptoCobro.objects.get(nombre="Libros")
    respuesta = _cargo_manual(base["op"], ana, libros, 2)
    solicitud = Solicitud.objects.get(accion="cargo_sin_credito")
    assert respuesta.url == reverse("solicitudes:detalle", args=[solicitud.pk])
    assert not Cargo.objects.filter(titular=ana, concepto=libros).exists()
    assert solicitud.datos == {"concepto": libros.pk, "cantidad": 2, "importe_unitario": 50000}
    with pytest.raises(motor.ErrorSolicitud):
        motor.aprobar(solicitud, base["op"])
    detalle = cliente(base["sup"]).get(reverse("solicitudes:detalle", args=[solicitud.pk])).content.decode()
    assert "sin crédito" in detalle and "$1,000.00" in detalle
    motor.aprobar(solicitud, base["sup"])
    cargo = Cargo.objects.get(titular=ana, concepto=libros)
    assert cargo.importe_original == 100000 and cargo.cantidad == 2 and cargo.creado_por == base["op"]
    _cargo_manual(base["sup"], ana, libros, 1)
    forzada = Solicitud.objects.filter(accion="cargo_sin_credito", solicitante=base["sup"]).get()
    assert forzada.estado == Solicitud.PENDIENTE
    with pytest.raises(motor.ErrorSolicitud):
        motor.aprobar(forzada, base["sup"])


def test_sin_credito_la_venta_al_adeudo_pasa_a_solicitud_y_la_de_contado_no(base):
    fijar("modulo_inventario", 1)
    libros = ConceptoCobro.objects.get(nombre="Libros")
    cuaderno = Articulo.objects.create(clave="CUA-1", nombre="Cuaderno", precio=5000, concepto=libros)
    conteo = inventario.subir_conteo({cuaderno.pk: 20}, base["op"], Conteo.PANTALLA)
    motor.aprobar(conteo.solicitud, base["sup"])
    ana = activo(base, "Ana")
    deuda(ana, 40, 50000)
    limite("valor", 0)
    op = cliente(base["op"])
    ruta = reverse("inventario:vender_titular", args=[ana.pk])
    respuesta = op.post(ruta, {f"cantidad_{cuaderno.pk}": "2", "modo": Venta.ADEUDO})
    solicitud = Solicitud.objects.get(accion="venta_sin_credito")
    assert respuesta.url == reverse("solicitudes:detalle", args=[solicitud.pk]) and not Venta.objects.exists()
    motor.aprobar(solicitud, base["sup"])
    venta = Venta.objects.get()
    assert venta.modo == Venta.ADEUDO and venta.total == 10000 and venta.usuario == base["op"]
    sin_turno = op.post(ruta, {f"cantidad_{cuaderno.pk}": "1", "modo": Venta.AHORA})
    assert sin_turno.status_code == 302 and not Venta.objects.filter(modo=Venta.AHORA).exists()
    assert Solicitud.objects.filter(accion="venta_sin_credito").count() == 2
    from caja import servicios as servicios_caja
    from caja.models import Caja

    servicios_caja.abrir_turno(base["op"], Caja.objects.get_or_create(nombre="Caja de ventas")[0], 0)
    con_turno = op.post(ruta, {f"cantidad_{cuaderno.pk}": "1", "modo": Venta.AHORA})
    assert con_turno.status_code == 302 and "/cobr" in con_turno.url
    assert Venta.objects.filter(modo=Venta.AHORA).count() == 1


def test_sin_credito_la_prorroga_pasa_a_solicitud_aunque_se_pueda_directo(base):
    ana = activo(base, "Ana")
    cargo = deuda(ana, 40, 50000)
    datos = {"cargo": cargo.pk, "fecha_limite": (hoy_negocio() + timedelta(days=10)).isoformat(), "motivo": "Acuerdo"}
    limite("valor", 0)
    resultado = motor.ejecutar("prorroga", base["sup"], ana, datos)
    assert resultado.via == "solicitud" and not Prorroga.objects.exists()
    motor.aprobar(resultado.solicitud, base["dir"])
    assert Prorroga.objects.filter(cargo=cargo).exists()
    limite()
    otro = deuda(ana, 50, 1000)
    directo = motor.ejecutar("prorroga", base["sup"], ana, {**datos, "cargo": otro.pk})
    assert directo.via == "directa"


def test_al_ponerse_al_corriente_recupera_el_credito(base):
    ana = activo(base, "Ana")
    cargo = deuda(ana, 40, 50000)
    limite("valor", 0)
    libros = ConceptoCobro.objects.get(nombre="Libros")
    libro.registrar_pago(ana, libro.saldo_de(cargo), Pago.EFECTIVO, base["op"], turno=turno_de(base["op"]))
    assert _cargo_manual(base["op"], ana, libros, 1).status_code == 302
    assert Cargo.objects.filter(titular=ana, concepto=libros).exists() and not Solicitud.objects.filter(accion="cargo_sin_credito").exists()


def test_regla_con_sin_credito_y_regla_propia_mas_tolerante(base):
    grupo = Agrupacion.objects.create(nombre="Sexto")
    ana, beto = activo(base, "Ana", grupo), activo(base, "Beto", grupo)
    deuda(ana, 40)
    deuda(beto, 40)
    regla(nombre="General", texto="No puede pasar", dias_minimos=30, marca=True, sin_credito=True, aviso_inicio=True)
    regla(nombre="Tolerancia", texto="Tiene acuerdo", alcance=ReglaRezago.TITULAR, titular=ana, dias_minimos=90, marca=True, sin_credito=True)
    situaciones = calculo.evaluar()
    assert situaciones[beto.pk].sin_credito and situaciones[beto.pk].marcas() == ["No puede pasar", "Sin crédito"]
    assert not situaciones[ana.pk].sin_credito and situaciones[ana.pk].marcas() == [] and situaciones[ana.pk].aviso
    regla(nombre="Estricta", texto="Revisar", alcance=ReglaRezago.AGRUPACION, agrupacion=grupo, dias_minimos=60, aviso_inicio=True)
    assert not calculo.evaluar()[beto.pk].aviso


def test_varias_reglas_valen_todas_y_el_aviso_usa_la_mas_grave(base):
    ana = activo(base, "Ana")
    deuda(ana, 40, 30000)
    regla(nombre="Pronto", texto="Pago atrasado", dias_minimos=10, aviso_inicio=True, cobranza=True)
    regla(nombre="Tarde", texto="No puede pasar", dias_minimos=30, aviso_inicio=True, marca=True)
    regla(nombre="Importe", texto="Adeudo alto", importe_minimo=20000, marca=True)
    regla(nombre="Lejos", texto="Nunca", dias_minimos=400, aviso_inicio=True)
    situacion = calculo.de(ana)
    assert situacion.texto_aviso() == "No puede pasar" and situacion.cobranza and set(situacion.marcas()) == {"No puede pasar", "Adeudo alto"}
    cobranza = cortes.generar_cobranza(usuario=base["sup"])
    seccion = next(s for s in cobranza.cifras["secciones"] if s["clave"] == "rezagados")
    assert seccion["filas"][0]["aviso"] == "No puede pasar" and seccion["filas"][0]["importe_pendiente"] == 30000


def test_reglas_por_pantalla_con_validacion_y_bitacora(base):
    ana = activo(base, "Ana")
    c = cliente(base["sup"])
    vacio = c.post(reverse("rezagos:regla_nueva"), {"nombre": "X", "texto": "Y", "alcance": "todos"})
    assert vacio.status_code == 200 and "al menos una condición" in vacio.content.decode() and "al menos una acción" in vacio.content.decode()
    largo = c.post(reverse("rezagos:regla_nueva"), {"nombre": "X", "texto": "x" * 61, "alcance": "todos", "dias_minimos": "5", "marca": "on"})
    assert largo.status_code == 200 and not ReglaRezago.objects.exists()
    nadie = c.post(reverse("rezagos:regla_nueva"), {"nombre": "X", "texto": "Y", "alcance": "titular", "matricula": "999", "dias_minimos": "5", "marca": "on"})
    assert nadie.status_code == 200
    respuesta = c.post(reverse("rezagos:regla_nueva"), {"nombre": "Propia", "texto": "<b>Ojo</b>", "alcance": "titular", "matricula": ana.matricula_formateada, "dias_minimos": "5", "marca": "on", "activa": "on"})
    assert respuesta.status_code == 302
    creada = ReglaRezago.objects.get()
    assert creada.titular == ana and creada.alcance == "titular" and creada.agrupacion is None
    assert Evento.objects.filter(accion="regla_rezago_creada", titular=ana.pk).exists()
    deuda(ana, 10)
    pagina = cliente(base["op"]).get(reverse("titulares:lista")).content.decode()
    assert "&lt;b&gt;Ojo&lt;/b&gt;" in pagina and "<b>Ojo</b>" not in pagina
    assert c.post(reverse("rezagos:regla_editar", args=[creada.pk]), {"nombre": "Propia", "texto": "Ojo", "alcance": "todos", "dias_minimos": "5", "marca": "on"}).status_code == 302
    creada.refresh_from_db()
    assert creada.titular is None and not creada.activa
    assert cliente(base["op"]).get(reverse("rezagos:reglas")).status_code == 403


@pytest.fixture
def mostrador(base):
    rol = Rol.objects.create(nombre="Mostrador", nivel=1)
    PermisoRol.objects.create(rol=rol, permiso="turno_caja")
    return nuevo_usuario("mostrador", rol)


def test_aviso_del_inicio_para_todos_sin_importes_para_quien_no_ve_saldos(base, mostrador):
    grupo = Agrupacion.objects.create(nombre="Séptimo")
    ana = activo(base, "Ana", grupo)
    deuda(ana, 40, 123456)
    regla(nombre="Tarde", texto="No puede pasar", dias_minimos=30, aviso_inicio=True)
    pagina = cliente(mostrador).get(reverse("inicio")).content.decode()
    assert "Ana Prueba" in pagina and ana.matricula_formateada in pagina and "Séptimo" in pagina and "40 días de atraso" in pagina and "No puede pasar" in pagina
    for rastro in ("1,234.56", "123456", "1234.56", "adeudo vencido"):
        assert rastro not in pagina
    assert reverse("titulares:detalle", args=[ana.pk]) not in pagina
    lista = cliente(mostrador).get(reverse("rezagos:lista") + "?orden=adeudo").content.decode()
    assert "Ana Prueba" in lista and "1,234.56" not in lista and "123456" not in lista and "Exportar" not in lista
    assert cliente(mostrador).get(reverse("rezagos:exportar")).status_code == 403
    con_saldos = cliente(base["op"]).get(reverse("inicio")).content.decode()
    assert "$1,234.56" in con_saldos


def test_texto_de_regla_propia_no_lo_ve_quien_no_ve_la_ficha(base, mostrador):
    ana = activo(base, "Ana")
    deuda(ana, 40)
    regla(nombre="Propia", texto="Acuerdo privado", alcance=ReglaRezago.TITULAR, titular=ana, dias_minimos=5, aviso_inicio=True)
    pagina = cliente(mostrador).get(reverse("inicio")).content.decode()
    assert "Ana Prueba" in pagina and "Acuerdo privado" not in pagina
    assert "Acuerdo privado" in cliente(base["op"]).get(reverse("inicio")).content.decode()


def test_aviso_lista_veinte_y_lista_completa_ordenable_y_exportable(base):
    regla(nombre="Atraso", texto="Pago atrasado", dias_minimos=1, aviso_inicio=True)
    for numero in range(25):
        deuda(activo(base, f"Nombre{numero:02d}"), numero + 2, 1000 * (25 - numero))
    aviso = presentacion.aviso_para(base["op"])
    assert len(aviso["filas"]) == 20 and aviso["total"] == 25 and aviso["mas"] and aviso["filas"][0]["dias"] == 26
    c = cliente(base["op"])
    assert "Ver la lista completa (25)" in c.get(reverse("inicio")).content.decode()
    por_adeudo = [f["dias"] for f in presentacion.lista_para(base["op"], "adeudo")]
    assert por_adeudo[0] == 2
    assert c.get(reverse("rezagos:lista") + "?orden=__import__").status_code == 200
    archivo = c.get(reverse("rezagos:exportar"))
    texto = archivo.content.decode("utf-8-sig")
    assert archivo["Content-Disposition"].endswith('"rezagados.csv"') and texto.count("\n") == 26


def test_exportacion_neutraliza_formulas(base):
    nombre = activo(base, "=HYPERLINK(1)")
    deuda(nombre, 10)
    regla(nombre="Atraso", texto="+sumar", dias_minimos=1, aviso_inicio=True)
    texto = cliente(base["op"]).get(reverse("rezagos:exportar")).content.decode("utf-8-sig")
    assert "'=HYPERLINK" in texto and "'+sumar" in texto


def test_plantillas_traen_por_cantidad_y_reglas_de_arranque_con_su_vocabulario():
    for nombre in plantillas.disponibles():
        datos = plantillas.leer(nombre)
        assert datos["rezagos"] and all(r["dias_minimos"] and r["acciones"] for r in datos["rezagos"])
        assert any(c.get("por_cantidad") for c in datos["conceptos"])
        assert all("importe" not in r for r in datos["rezagos"])
        for rol in datos["roles"]:
            assert ("configurar_limites_adeudo" in rol["permisos"]) == (rol["nivel"] >= 2)
    escuela = plantillas.leer("escuela")
    assert next(c for c in escuela["conceptos"] if c["nombre"] == "Libros")["por_cantidad"]
    assert "No puede pasar" in {r["texto"] for r in escuela["rezagos"]}
    assert "Acceso suspendido" in {r["texto"] for r in plantillas.leer("gimnasio")["rezagos"]}


def test_esquema_rechaza_reglas_y_cantidades_invalidas():
    base_datos = plantillas.leer("generico")
    for cambio, ruta in (
        ({"rezagos": [{"nombre": "X", "texto": "Y", "acciones": ["marca"]}]}, "condición"),
        ({"rezagos": [{"nombre": "X", "texto": "Y", "dias_minimos": 5, "acciones": ["borrar"]}]}, "acciones"),
        ({"rezagos": [{"nombre": "X", "texto": "Y", "dias_minimos": 5, "importe_minimo": 100, "acciones": ["marca"]}]}, "no permitidas"),
        ({"rezagos": [{"nombre": "X", "texto": "Y" * 61, "dias_minimos": 5, "acciones": ["marca"]}]}, "texto"),
        ({"conceptos": [{"nombre": "X", "tipo": "recurrente", "periodicidad": "mensual", "por_cantidad": True}]}, "por cantidad"),
        ({"conceptos": [{"nombre": "X", "tipo": "por_evento", "por_cantidad": True, "cantidad_maxima": 0}]}, "cantidad_maxima"),
    ):
        with pytest.raises(esquema.PlantillaInvalida, match=ruta):
            esquema.validar({**base_datos, **cambio})


def test_exportar_configuracion_lleva_opciones_y_reglas_generales(base):
    ana = activo(base, "Ana")
    regla(nombre="General", texto="Pago atrasado", dias_minimos=10, aviso_inicio=True)
    regla(nombre="Propia", texto="Privado", alcance=ReglaRezago.TITULAR, titular=ana, dias_minimos=5, marca=True)
    regla(nombre="Por importe", texto="Alto", importe_minimo=5000, marca=True)
    datos = plantillas.exportar()
    assert [r["nombre"] for r in datos["rezagos"]] == ["General"]
    assert next(c for c in datos["conceptos"] if c["nombre"] == "Libros")["por_cantidad"]
    esquema.validar(datos)


def test_instalacion_existente_queda_igual(base):
    assert not ReglaRezago.objects.exists() and not TarifaAgrupacion.objects.exists()
    assert LimiteAdeudo.actual().modo_importe == "ilimitado" and LimiteAdeudo.actual().modo_dias == "ilimitado"
    extras = ConceptoCobro.objects.get(nombre="Extras")
    assert not OpcionConcepto.objects.filter(concepto=extras).exists()
    from tarifas.servicios import cantidad_maxima

    assert cantidad_maxima(extras) == 1000
    PermisoRol.objects.filter(permiso__in=("configurar_limites_adeudo", "configurar_rezagos")).delete()
    PoliticaAccion.objects.filter(accion__in=("cargo_sin_credito", "venta_sin_credito")).delete()
    importlib.import_module("cuentas.migrations.0009_permisos_de_rezagos").otorgar(registro, None)
    importlib.import_module("solicitudes.migrations.0011_acciones_sin_credito").politicas(registro, None)
    con_limites = set(PermisoRol.objects.filter(permiso="configurar_limites_adeudo").values_list("rol__nombre", flat=True))
    assert con_limites == {"Supervisión", "Dirección"}
    assert PoliticaAccion.objects.get(accion="venta_sin_credito").permiso_solicitar == "vender_articulos"


@pytest.mark.django_db
def test_el_asistente_trae_las_reglas_de_arranque_solo_en_instalacion_nueva():
    from django.conf import settings
    from django.test import Client

    from .test_asistente import paso_inicio

    configurar("escuela")
    assert not ReglaRezago.objects.exists()
    from configuracion.models import Negocio

    Negocio.objects.filter(pk=1).update(configurado=False)
    c = Client()
    assert c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE)).url == reverse("asistente:personalizar")
    assert set(ReglaRezago.objects.values_list("texto", flat=True)) == {"Pago atrasado", "No puede pasar"}
    c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE, plantilla="gimnasio"))
    assert ReglaRezago.objects.count() == 2


def test_marcas_en_buscadores_y_al_cobrar(base):
    fijar("modulo_inventario", 1)
    ana = activo(base, "Ana")
    deuda(ana, 40)
    regla(nombre="Tarde", texto="No puede pasar", dias_minimos=30, marca=True)
    c = cliente(base["op"])
    for ruta in (reverse("cobros:buscar") + "?q=Ana", reverse("inventario:vender") + "?q=Ana", reverse("titulares:lista"), reverse("titulares:detalle", args=[ana.pk]), reverse("cobros:cobrar", args=[ana.pk])):
        assert "No puede pasar" in c.get(ruta).content.decode(), ruta


def test_rendimiento_con_consultas_agregadas(base):
    usuario = base["op"]
    grupo = Agrupacion.objects.create(nombre="Masivo")
    regla(nombre="Atraso", texto="Pago atrasado", dias_minimos=5, aviso_inicio=True, marca=True)
    regla(nombre="Grupo", texto="Revisar", alcance=ReglaRezago.AGRUPACION, agrupacion=grupo, dias_minimos=20, aviso_inicio=True)
    limite("valor", 500000, "valor", 300)

    def cargar(cuantos, por_titular, desde):
        titulares = Titular.objects.bulk_create([Titular(matricula=f"{desde + n:09d}", nombre=f"N{n}", apellidos="Prueba", estado=Titular.ACTIVO, agrupacion=grupo if n % 3 == 0 else None, creado_por=usuario) for n in range(cuantos)])
        extras = ConceptoCobro.objects.get(nombre="Extras")
        hoy = hoy_negocio()
        Cargo.objects.bulk_create(
            [Cargo(titular=t, concepto=extras, importe_original=1000 + i, importe_final=1000 + i, vencimiento=hoy - timedelta(days=(i * 7 + n) % 400 - 30), origen=Cargo.MANUAL) for n, t in enumerate(titulares) for i in range(por_titular)],
            batch_size=5000,
        )
        primeros = list(Cargo.objects.filter(titular__in=titulares[:50]).values_list("pk", flat=True)[:100])
        CancelacionCargo.objects.bulk_create([CancelacionCargo(cargo_id=pk, tipo=CancelacionCargo.CANCELACION, importe=500, motivo="Prueba", ejecutada_por=usuario) for pk in primeros])
        Prorroga.objects.bulk_create([Prorroga(cargo_id=pk, fecha_limite=hoy + timedelta(days=30), motivo="Prueba", creada_por=usuario) for pk in primeros[:50]])

    cargar(10, 20, 100000000)
    usuario.olvidar_permisos()
    with CaptureQueriesContext(connection) as pocos:
        presentacion.aviso_para(usuario)
    cargar(4990, 20, 200000000)
    assert Titular.objects.count() >= 5000 and Cargo.objects.count() >= 100000
    usuario.olvidar_permisos()
    inicio = time.monotonic()
    with CaptureQueriesContext(connection) as muchos:
        aviso = presentacion.aviso_para(usuario)
    duracion = time.monotonic() - inicio
    assert len(muchos) == len(pocos) <= 8
    assert aviso["total"] > 1000 and len(aviso["filas"]) == 20
    assert duracion < 30
    with CaptureQueriesContext(connection) as inicio_consultas:
        assert cliente(usuario).get(reverse("inicio")).status_code == 200
    assert sum(1 for q in inicio_consultas.captured_queries if re.search(r'"cobros_cargo"', q["sql"])) <= 6
