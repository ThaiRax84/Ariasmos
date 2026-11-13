import importlib
import threading
from datetime import timedelta
from io import BytesIO

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from auditoria.models import Evento
from caja import comprobantes
from caja.models import MovimientoPiezas
from caja.servicios import esperado_de, neto_de
from cobros import libro
from cobros.models import Aplicacion, Cargo, ConceptoCobro, Pago, ReversionPago
from configuracion import esquema, plantillas
from configuracion.models import Parametro, parametro
from cortes import calculo
from cortes.salida import vista
from inventario import servicios as inventario
from inventario.models import Articulo, ComprobanteInventario, Conteo, Devolucion, MovimientoInventario, RegistroInmutable, RegistroInventario, RenglonConteo, RenglonVenta, Venta
from solicitudes import motor
from solicitudes.models import PoliticaAccion, Solicitud
from titulares.models import Familia, Titular

from .conftest import cliente, configurar, nuevo_usuario
from .libro_ayudas import preparar_conceptos, titular_activo, turno_de, verificar_sumas
from .test_retiros import MALICIOSOS, jpeg_con_ubicacion


def fijar(clave, valor):
    Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})


def cargar(personas, cantidades):
    conteo = inventario.subir_conteo({a.pk: n for a, n in cantidades.items()}, personas["op"], Conteo.PANTALLA)
    motor.aprobar(conteo.solicitud, personas["sup"])
    return conteo


@pytest.fixture
def base(personas):
    cache.clear()
    preparar_conceptos()
    fijar("modulo_inventario", 1)
    fijar("devoluciones_inventario", 1)
    libros = ConceptoCobro.objects.get(nombre="Libros")
    libro_a = Articulo.objects.create(clave="LIB-A", nombre="Libro A", precio=35000, minimo=1, concepto=libros)
    cuaderno = Articulo.objects.create(clave="CUA-1", nombre="Cuaderno", precio=5000, concepto=libros)
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    cargar(personas, {libro_a: 10, cuaderno: 20})
    return personas, ana, libro_a, cuaderno


def renglones(venta):
    return {r.articulo.clave: r for r in venta.renglones.select_related("articulo", "cargo")}


def cobrar_venta(c, titular, venta, importe):
    return c.post(reverse("cobros:cobrar", args=[titular.pk]), {"paso": "confirmar", "importe": str(importe), "ficha": f"ficha-de-prueba-{venta.pk:08d}", "venta": str(venta.pk)})


def test_existencia_es_suma_de_movimientos_inmutables(base):
    personas, ana, libro_a, cuaderno = base
    assert inventario.existencias() == {libro_a.pk: 10, cuaderno.pk: 20}
    assert MovimientoInventario.objects.filter(tipo=MovimientoInventario.CARGA_INICIAL).count() == 2
    movimiento = MovimientoInventario.objects.first()
    with pytest.raises(RegistroInmutable):
        movimiento.save()
    with pytest.raises(RegistroInmutable):
        MovimientoInventario.objects.update(cantidad=99)
    with pytest.raises(Exception):
        MovimientoInventario.objects.all().delete()
    with pytest.raises(RegistroInmutable):
        libro_a.delete()
    assert not hasattr(Articulo, "existencia")


def test_administrar_articulos_solo_supervision_y_con_bitacora(base):
    personas, ana, libro_a, cuaderno = base
    datos = {"clave": "uni-1", "nombre": "Uniforme", "precio": "250.00", "minimo": "2", "concepto": ConceptoCobro.objects.get(nombre="Extras").pk, "activo": "on"}
    assert cliente(personas["op"]).post(reverse("inventario:articulo_nuevo"), datos).status_code == 403
    assert cliente(personas["sup"]).post(reverse("inventario:articulo_nuevo"), datos).status_code == 302
    nuevo = Articulo.objects.get(clave="UNI-1")
    assert nuevo.precio == 25000 and Evento.objects.filter(accion="articulo_creado").exists()
    malo = cliente(personas["sup"]).post(reverse("inventario:articulo_nuevo"), {**datos, "clave": "=MAL"})
    assert malo.status_code == 200 and not Articulo.objects.filter(clave="=MAL").exists()
    cliente(personas["sup"]).post(reverse("inventario:articulo_editar", args=[nuevo.pk]), {**datos, "precio": "300.00"})
    assert Evento.objects.filter(accion="articulo_cambiado").latest("numero").datos["cambios"]["precio"] == [25000, 30000]


def test_venta_al_adeudo_con_precio_del_articulo_nunca_del_formulario(base):
    personas, ana, libro_a, cuaderno = base
    c = cliente(personas["op"])
    respuesta = c.post(reverse("inventario:vender_titular", args=[ana.pk]), {"articulo_0": libro_a.pk, "cantidad_0": "2", "articulo_1": cuaderno.pk, "cantidad_1": "3", "modo": "adeudo", "precio": "1", "precio_0": "1", "total": "1"})
    venta = Venta.objects.get()
    assert respuesta.url == reverse("inventario:venta", args=[venta.pk])
    filas = renglones(venta)
    assert filas["LIB-A"].cargo.importe_final == 70000 and filas["CUA-1"].cargo.importe_final == 15000 and venta.total == 85000
    assert filas["LIB-A"].precio_unitario == 35000 and libro.saldo_de(filas["LIB-A"].cargo) == 70000
    assert inventario.existencias() == {libro_a.pk: 8, cuaderno.pk: 17}
    assert Evento.objects.filter(accion="venta_registrada", usuario=personas["op"]).exists()


@pytest.mark.parametrize("cantidad", ["0", "-1", "10001", "1.5", "abc", "99999999999999999999"])
def test_cantidades_enteras_positivas_con_tope(base, cantidad):
    personas, ana, libro_a, cuaderno = base
    respuesta = cliente(personas["op"]).post(reverse("inventario:vender_titular", args=[ana.pk]), {"articulo_0": libro_a.pk, "cantidad_0": cantidad, "modo": "adeudo"})
    assert respuesta.status_code == 200 and not Venta.objects.exists()


def test_servicio_rechaza_cantidades_y_articulos_no_validos(base):
    personas, ana, libro_a, cuaderno = base
    for malos in ([(libro_a.pk, 0)], [(libro_a.pk, -2)], [(libro_a.pk, True)], [(libro_a.pk, 2.0)], [(libro_a.pk, 6000), (libro_a.pk, 6000)], [("1", 1)], [(999999, 1)], []):
        with pytest.raises(inventario.ErrorInventario):
            inventario.vender(ana, malos, Venta.ADEUDO, personas["op"])
    Articulo.objects.filter(pk=cuaderno.pk).update(activo=False)
    with pytest.raises(inventario.ErrorInventario):
        inventario.vender(ana, [(cuaderno.pk, 1)], Venta.ADEUDO, personas["op"])
    assert not Venta.objects.exists() and not Cargo.objects.filter(concepto__nombre="Libros").exists()


def test_lo_paga_ahora_aplica_primero_a_la_venta(base):
    personas, ana, libro_a, cuaderno = base
    inscripcion = Cargo.objects.get(titular=ana, concepto__nombre="Inscripción")
    turno_de(personas["op"])
    c = cliente(personas["op"])
    respuesta = c.post(reverse("inventario:vender_titular", args=[ana.pk]), {"articulo_0": libro_a.pk, "cantidad_0": "1", "modo": "ahora"})
    venta = Venta.objects.get()
    assert respuesta.url == reverse("cobros:cobrar", args=[ana.pk]) + f"?venta={venta.pk}"
    pantalla = c.get(respuesta.url).content.decode()
    assert f'name="venta" value="{venta.pk}"' in pantalla and "350.00" in pantalla
    propuesta = c.post(reverse("cobros:cobrar", args=[ana.pk]), {"importe": "350.00", "venta": str(venta.pk)}).content.decode()
    assert "Libro A" in propuesta
    cobrar_venta(c, ana, venta, 35000)
    venta.refresh_from_db()
    pago = venta.pago
    assert pago is not None and list(pago.aplicaciones.values_list("cargo", "importe")) == [(renglones(venta)["LIB-A"].cargo_id, 35000)]
    assert libro.saldo_de(inscripcion) == 100000
    verificar_sumas()


def test_lo_paga_ahora_con_mas_dinero_reparte_el_resto(base):
    personas, ana, libro_a, cuaderno = base
    turno_de(personas["op"])
    venta = inventario.vender(ana, [(cuaderno.pk, 2)], Venta.AHORA, personas["op"])
    cobrar_venta(cliente(personas["op"]), ana, venta, 60000)
    venta.refresh_from_db()
    aplicaciones = list(venta.pago.aplicaciones.order_by("id").values_list("cargo__concepto__nombre", "importe"))
    assert aplicaciones == [("Libros", 10000), ("Inscripción", 50000)]
    otro = inventario.vender(ana, [(cuaderno.pk, 1)], Venta.ADEUDO, personas["op"])
    assert cliente(personas["op"]).get(reverse("cobros:cobrar", args=[ana.pk]) + f"?venta={otro.pk}").context["venta"] is None


def test_sin_existencia_no_bloquea_y_lo_revisa_otra_persona(base):
    personas, ana, libro_a, cuaderno = base
    c = cliente(personas["op"])
    c.post(reverse("inventario:vender_titular", args=[ana.pk]), {"articulo_0": libro_a.pk, "cantidad_0": "12", "modo": "adeudo"})
    renglon = RenglonVenta.objects.get()
    assert renglon.sin_existencia and renglon.existencia_antes == 10 and inventario.existencia(libro_a) == -2
    assert "Supervisión la revisará" in "".join(str(m) for m in c.get(reverse("inventario:venta", args=[renglon.venta_id])).context["messages"])
    assert "Libro A" in cliente(personas["sup"]).get(reverse("inventario:revision")).content.decode()
    inventario.vender(ana, [(cuaderno.pk, 25)], Venta.ADEUDO, personas["sup"])
    propio = RenglonVenta.objects.get(articulo=cuaderno)
    assert cliente(personas["sup"]).post(reverse("inventario:renglon_revisar", args=[propio.pk])).status_code == 403
    cliente(personas["sup"]).post(reverse("inventario:renglon_revisar", args=[renglon.pk]))
    renglon.refresh_from_db()
    assert renglon.revisado_por == personas["sup"]


def test_venta_publico_en_una_transaccion_y_cuenta_oculta(base):
    personas, ana, libro_a, cuaderno = base
    c = cliente(personas["op"])
    assert c.post(reverse("inventario:vender_publico"), {"articulo_0": cuaderno.pk, "cantidad_0": "2"}).url == reverse("caja:inicio")
    turno = turno_de(personas["op"])
    previa = c.post(reverse("inventario:vender_publico"), {"articulo_0": cuaderno.pk, "cantidad_0": "2"})
    assert previa.context["total"] == 10000 and not Venta.objects.exists()
    respuesta = c.post(reverse("inventario:vender_publico"), {"articulo_0": cuaderno.pk, "cantidad_0": "2", "paso": "confirmar", "ficha": previa.context["ficha"], "precio": "1"})
    venta = Venta.objects.get()
    publico = venta.titular
    assert publico.interno and venta.pago.importe == 10000 and venta.pago.turno == turno
    assert respuesta.url == reverse("cobros:recibo", args=[venta.pago.recibo.pk])
    assert sum(p.saldo for p in libro.pendientes_de([publico.pk])) == 0
    otra = c.post(reverse("inventario:vender_publico"), {"articulo_0": cuaderno.pk, "cantidad_0": "2", "paso": "confirmar", "ficha": previa.context["ficha"]})
    assert Venta.objects.count() == 1 and otra.url == respuesta.url
    assert not Titular.objects.filter(pk=publico.pk).exists() and Titular.todos.filter(pk=publico.pk).exists()
    assert "Público" not in cliente(personas["sup"]).get(reverse("titulares:lista")).content.decode()
    assert "en general" not in cliente(personas["sup"]).get(reverse("cobros:buscar") + "?q=Público").content.decode()
    for nombre in ("titulares:detalle", "cobros:cobrar", "cobros:cargo_manual", "cobros:beca", "titulares:baja", "titulares:editar", "titulares:cambiar_familia", "inventario:vender_titular"):
        assert cliente(personas["dir"]).get(reverse(nombre, args=[publico.pk])).status_code == 404, nombre
    recibo = cliente(personas["op"]).get(reverse("cobros:recibo", args=[venta.pago.recibo.pk])).content.decode()
    assert "Público en general" in recibo and "PUBLICO" not in recibo
    assert neto_de(turno) == 10000


def test_cuenta_publico_no_recibe_cargos_ni_pagos_por_otra_via(base):
    personas, ana, libro_a, cuaderno = base
    publico = inventario.cuenta_publico(personas["op"])
    concepto = ConceptoCobro.objects.get(nombre="Colegiatura")
    with pytest.raises(libro.ErrorLibro):
        libro.crear_cargo(publico, concepto, 1000, timezone.now().date(), Cargo.MANUAL)
    with pytest.raises(libro.ErrorLibro):
        libro.crear_cargo(publico, concepto, 1000, timezone.now().date(), Cargo.AUTOMATICO, permitir_interno=True)
    with pytest.raises(libro.ErrorLibro):
        libro.registrar_pago(publico, 1000, Pago.EFECTIVO, personas["op"], turno=turno_de(personas["op"]))
    with pytest.raises(libro.ErrorLibro):
        libro.registrar_pago(publico, 1000, Pago.BANCO, personas["op"], permitir_interno=True)
    for accion, datos in (("baja", {"motivo": 1}), ("correccion_nombre", {"nombre": "X", "apellidos": "Y"}), ("cambio_familia", {"modo": "crear", "nombre": "F"}), ("beca", {}), ("cancelar_cargo", {})):
        with pytest.raises(motor.ErrorSolicitud, match="cuenta interna"):
            motor.ejecutar(accion, personas["dir"], publico, datos)
    familia = Familia.objects.create(nombre="F")
    with pytest.raises(IntegrityError), transaction.atomic():
        Titular.todos.filter(pk=publico.pk).update(familia=familia)
    from cobros import generacion

    ConceptoCobro.objects.filter(nombre="Colegiatura").update(aplica_a="todos")
    generacion.generar_recurrentes()
    assert not Cargo.objects.filter(titular=publico).exists()
    assert inventario.cuenta_publico(personas["sup"]).pk == publico.pk and Titular.todos.filter(interno=True).count() == 1


def test_venta_publico_no_pasa_del_tope_individual(base):
    personas, ana, libro_a, cuaderno = base
    turno = turno_de(personas["op"])
    fijar("tope_pago_individual", 30000)
    with pytest.raises(inventario.ErrorInventario, match="tope"):
        inventario.vender_publico([(libro_a.pk, 1)], personas["op"], turno, "f" * 20)
    assert not Venta.objects.exists() and not Titular.todos.filter(interno=True, cargos__isnull=False).exists()


def test_revertir_pago_publico_cancela_sus_cargos_y_pregunta_si_regreso(base):
    personas, ana, libro_a, cuaderno = base
    turno_de(personas["op"])
    libro.registrar_pago(ana, 100000, Pago.EFECTIVO, personas["sup"], turno=turno_de(personas["sup"], "Caja 2"))
    venta = inventario.vender_publico([(libro_a.pk, 1), (cuaderno.pk, 2)], personas["op"], inventario_turno(personas["op"]), "g" * 20)
    pantalla = cliente(personas["sup"]).get(reverse("cobros:revertir", args=[venta.pago.pk])).content.decode()
    assert "¿Regresó Libro A × 1?" in pantalla
    filas = renglones(venta)
    respuesta = cliente(personas["sup"]).post(reverse("cobros:revertir", args=[venta.pago.pk]), {"motivo": "cliente se arrepintió", f"regreso_{filas['LIB-A'].pk}": "on"})
    assert respuesta.status_code == 302 and "/titulares/" not in respuesta.url
    assert ReversionPago.objects.filter(pago=venta.pago).exists()
    assert sum(p.saldo for p in libro.pendientes_de([venta.titular_id])) == 0
    assert inventario.existencias() == {libro_a.pk: 10, cuaderno.pk: 18}
    assert Devolucion.objects.get().medio == Devolucion.REVERSION


def inventario_turno(usuario):
    from caja.servicios import turno_abierto

    return turno_abierto(usuario)


def test_reversion_de_venta_a_titular_regresa_solo_lo_que_volvio(base):
    personas, ana, libro_a, cuaderno = base
    turno_de(personas["op"])
    venta = inventario.vender(ana, [(libro_a.pk, 1), (cuaderno.pk, 1)], Venta.AHORA, personas["op"])
    cobrar_venta(cliente(personas["op"]), ana, venta, 40000)
    venta.refresh_from_db()
    filas = renglones(venta)
    libro.registrar_pago(ana, 100000, Pago.EFECTIVO, personas["sup"], turno=turno_de(personas["sup"], "Caja 2"))
    cliente(personas["sup"]).post(reverse("cobros:revertir", args=[venta.pago.pk]), {"motivo": "error", f"regreso_{filas['CUA-1'].pk}": "on"})
    assert libro.saldo_de(filas["CUA-1"].cargo) == 0 and libro.saldo_de(filas["LIB-A"].cargo) == 35000
    assert inventario.existencias()[cuaderno.pk] == 20 and inventario.existencias()[libro_a.pk] == 9


def test_devoluciones_apagadas_o_fuera_de_plazo(base):
    personas, ana, libro_a, cuaderno = base
    venta = inventario.vender(ana, [(cuaderno.pk, 2)], Venta.ADEUDO, personas["op"])
    cantidades = {str(venta.renglones.get().pk): [1, True]}
    fijar("devoluciones_inventario", 0)
    with pytest.raises(inventario.ErrorInventario, match="no acepta"):
        inventario.devolver(venta, cantidades, Devolucion.SALDO, personas["op"], "x")
    fijar("devoluciones_inventario", 1)
    fijar("dias_devolucion", 3)
    with connection.cursor() as cursor:
        cursor.execute("UPDATE inventario_venta SET creada = %s WHERE id = %s", [timezone.now() - timedelta(days=10), venta.pk])
    with pytest.raises(inventario.ErrorInventario, match="plazo"):
        inventario.devolver(venta, cantidades, Devolucion.SALDO, personas["op"], "x")
    assert cliente(personas["op"]).get(reverse("inventario:devolver_venta", args=[venta.pk])).status_code == 302


def test_devolucion_de_lo_no_pagado_cancela_sin_mover_dinero(base):
    personas, ana, libro_a, cuaderno = base
    venta = inventario.vender(ana, [(cuaderno.pk, 3)], Venta.ADEUDO, personas["op"])
    renglon = venta.renglones.get()
    respuesta = cliente(personas["op"]).post(reverse("inventario:devolver_venta", args=[venta.pk]), {f"cantidad_{renglon.pk}": "2", "medio": "saldo", "motivo": "sobraron"})
    assert respuesta.url == reverse("inventario:venta", args=[venta.pk])
    devolucion = Devolucion.objects.get()
    assert devolucion.medio == Devolucion.SIN_DINERO and devolucion.importe_cancelado == 10000 and devolucion.importe_dinero == 0
    assert libro.saldo_de(renglon.cargo) == 5000 and not Pago.objects.filter(medio=Pago.DEVOLUCION).exists()
    assert inventario.existencias()[cuaderno.pk] == 19 and devolucion.revision == "por_revisar"


def test_devolucion_a_saldo_a_favor_y_revision_ajena(base):
    personas, ana, libro_a, cuaderno = base
    turno_de(personas["op"])
    venta = inventario.vender(ana, [(libro_a.pk, 1)], Venta.AHORA, personas["op"])
    cobrar_venta(cliente(personas["op"]), ana, venta, 35000)
    renglon = venta.renglones.get()
    cliente(personas["op"]).post(reverse("inventario:devolver_venta", args=[venta.pk]), {f"cantidad_{renglon.pk}": "1", f"mal_{renglon.pk}": "on", "medio": "saldo", "motivo": "venía roto"})
    devolucion = Devolucion.objects.get()
    credito = devolucion.pago_credito
    assert devolucion.medio == Devolucion.SALDO and credito.medio == Pago.DEVOLUCION and credito.importe == 35000 and credito.turno is None
    assert credito.recibo.serie == "D"
    assert inventario.existencias()[libro_a.pk] == 9
    assert list(MovimientoInventario.objects.filter(devolucion=devolucion).values_list("tipo", "cantidad")) == [("devolucion", 1), ("merma", -1)]
    assert Aplicacion.objects.filter(pago=credito, cargo__concepto__nombre="Inscripción").exists()
    url = reverse("inventario:devolucion_revisar", args=[devolucion.pk])
    assert cliente(personas["op"]).post(url, {"resultado": "revisado"}).status_code == 403
    with pytest.raises(inventario.RevisionPropia):
        inventario.revisar_devolucion(devolucion, personas["op"], "revisado")
    cliente(personas["sup"]).post(url, {"resultado": "observado", "nota": "revisar el libro"})
    devolucion.refresh_from_db()
    assert devolucion.revision == "observado" and devolucion.revisado_por == personas["sup"]
    verificar_sumas()


def test_no_se_devuelve_mas_de_lo_vendido(base):
    personas, ana, libro_a, cuaderno = base
    venta = inventario.vender(ana, [(cuaderno.pk, 2)], Venta.ADEUDO, personas["op"])
    renglon = venta.renglones.get()
    with pytest.raises(inventario.ErrorInventario, match="más de lo vendido"):
        inventario.devolver(venta, {str(renglon.pk): [3, True]}, Devolucion.SALDO, personas["op"], "x")
    inventario.devolver(venta, {str(renglon.pk): [2, True]}, Devolucion.SALDO, personas["op"], "x")
    with pytest.raises(inventario.ErrorInventario, match="más de lo vendido"):
        inventario.devolver(venta, {str(renglon.pk): [1, True]}, Devolucion.SALDO, personas["op"], "x")
    otra = inventario.vender(ana, [(libro_a.pk, 1)], Venta.ADEUDO, personas["op"])
    with pytest.raises(inventario.ErrorInventario, match="no es de esta venta"):
        inventario.devolver(otra, {str(renglon.pk): [1, True]}, Devolucion.SALDO, personas["op"], "x")
    respuesta = cliente(personas["op"]).post(reverse("inventario:devolver_venta", args=[otra.pk]), {f"cantidad_{otra.renglones.get().pk}": "5", "medio": "saldo", "motivo": "x"})
    assert respuesta.status_code == 200 and Devolucion.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_dos_devoluciones_simultaneas_no_devuelven_de_mas():
    roles = configurar("escuela")
    op, sup = nuevo_usuario("operacion", roles["Operación"]), nuevo_usuario("supervision", roles["Supervisión"])
    preparar_conceptos()
    fijar("modulo_inventario", 1)
    fijar("devoluciones_inventario", 1)
    articulo = Articulo.objects.create(clave="CUA-1", nombre="Cuaderno", precio=5000, concepto=ConceptoCobro.objects.get(nombre="Libros"))
    ana = titular_activo(op, sup, "Ana")
    venta = inventario.vender(ana, [(articulo.pk, 2)], Venta.ADEUDO, op)
    renglon = venta.renglones.get()
    barrera = threading.Barrier(2)
    errores, hechas = [], []

    def trabajar():
        try:
            barrera.wait()
            hechas.append(inventario.devolver(venta, {str(renglon.pk): [2, True]}, Devolucion.SALDO, op, "doble"))
        except inventario.ErrorInventario as error:
            errores.append(error)
        finally:
            connection.close()

    hilos = [threading.Thread(target=trabajar) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert len(hechas) == 1 and len(errores) == 1
    assert sum(r.cantidad for d in Devolucion.objects.all() for r in d.renglones.all()) == 2
    assert inventario.existencias()[articulo.pk] == 0


def test_devolucion_en_efectivo_siempre_por_solicitud_de_otra_persona(base):
    personas, ana, libro_a, cuaderno = base
    turno_op = turno_de(personas["op"])
    venta = inventario.vender(ana, [(cuaderno.pk, 2)], Venta.AHORA, personas["sup"])
    turno_sup = turno_de(personas["sup"], "Caja 2")
    cobrar_venta(cliente(personas["sup"]), ana, venta, 10000)
    libro.registrar_pago(ana, 50000, Pago.EFECTIVO, personas["op"], turno=turno_op)
    renglon = venta.renglones.get()
    with pytest.raises(inventario.ErrorInventario, match="siempre se solicita"):
        inventario.devolver(venta, {str(renglon.pk): [1, True]}, Devolucion.EFECTIVO, personas["dir"], "x", turno=turno_sup)
    respuesta = cliente(personas["op"]).post(reverse("inventario:devolver_venta", args=[venta.pk]), {f"cantidad_{renglon.pk}": "1", "medio": "efectivo", "motivo": "no lo quiso"})
    solicitud = Solicitud.objects.get(accion="devolucion_efectivo")
    assert respuesta.url == reverse("solicitudes:detalle", args=[solicitud.pk]) and not Devolucion.objects.exists()
    pagina = cliente(personas["op"]).get(respuesta.url).content.decode()
    assert "Cuaderno × 1" in pagina and str(neto_de(turno_op)) not in pagina
    with pytest.raises(motor.ErrorSolicitud):
        motor.aprobar(solicitud, personas["op"])
    with pytest.raises(motor.ErrorSolicitud, match="cobró"):
        motor.aprobar(solicitud, personas["sup"])
    antes = esperado_de(turno_op)
    motor.aprobar(solicitud, personas["dir"])
    devolucion = Devolucion.objects.get()
    assert devolucion.medio == Devolucion.EFECTIVO and devolucion.turno == turno_op and devolucion.usuario == personas["op"] and devolucion.autorizada_por == personas["dir"]
    assert esperado_de(turno_op) == antes - 5000 and inventario.existencias()[cuaderno.pk] == 19


def test_devolucion_en_efectivo_sin_efectivo_suficiente_no_dice_cuanto(base):
    personas, ana, libro_a, cuaderno = base
    turno_op = turno_de(personas["op"])
    turno_sup = turno_de(personas["sup"], "Caja 2")
    venta = inventario.vender_publico([(libro_a.pk, 1)], personas["sup"], turno_sup, "h" * 20)
    renglon = venta.renglones.get()
    inventario.solicitar_efectivo(venta, {renglon.pk: [1, True]}, personas["op"], "no le sirvió")
    solicitud = Solicitud.objects.get(accion="devolucion_efectivo")
    with pytest.raises(motor.ErrorSolicitud) as error:
        motor.aprobar(solicitud, personas["dir"])
    assert "no tiene lo suficiente" in str(error.value) and "$" not in str(error.value) and "0.00" not in str(error.value)
    solicitud.refresh_from_db()
    assert solicitud.estado == Solicitud.PENDIENTE and not Devolucion.objects.exists()
    with pytest.raises(inventario.ErrorInventario, match="solo se devuelve en efectivo"):
        inventario.devolver(venta, {str(renglon.pk): [1, True]}, Devolucion.SALDO, personas["op"], "x")
    libro.registrar_pago(ana, 100000, Pago.EFECTIVO, personas["op"], turno=turno_op)
    with pytest.raises(inventario.ErrorInventario, match="Ya hay una solicitud"):
        inventario.solicitar_efectivo(venta, {renglon.pk: [1, True]}, personas["op"], "otra vez")
    motor.aprobar(solicitud, personas["dir"])
    assert sum(p.saldo for p in libro.pendientes_de([venta.titular_id])) == 0
    assert inventario.existencias()[libro_a.pk] == 10


def test_devolucion_en_efectivo_con_piezas_y_en_el_corte(base):
    personas, ana, libro_a, cuaderno = base
    fijar("control_denominaciones", 1)
    turno_op = turno_de(personas["op"])
    libro.registrar_pago(ana, 50000, Pago.EFECTIVO, personas["op"], turno=turno_op, piezas={"recibidas": {"50000": 1}, "cambio": {}})
    turno_sup = turno_de(personas["sup"], "Caja 2")
    venta = inventario.vender_publico([(cuaderno.pk, 1)], personas["sup"], turno_sup, "k" * 20, piezas={"recibidas": {"5000": 1}, "cambio": {}})
    renglon = venta.renglones.get()
    inventario.solicitar_efectivo(venta, {renglon.pk: [1, True]}, personas["op"], "x", piezas={"1000": 5})
    motor.aprobar(Solicitud.objects.get(accion="devolucion_efectivo"), personas["dir"])
    devolucion = Devolucion.objects.get()
    assert sum(m.piezas for m in MovimientoPiezas.objects.filter(devolucion_articulos=devolucion)) == -5
    from caja import servicios as caja

    caja.cerrar_turno(turno_op, personas["op"], {"50000": 1}, nota="faltan")
    cifras = calculo.cifras_diario(turno_op, turno_op.arqueo)
    seccion = next(s for s in cifras["secciones"] if s["clave"] == "devoluciones_articulos")
    assert seccion["filas"][0]["importe"] == 5000 and cifras["totales"]["total_devuelto_articulos"] == 5000


def test_entrada_y_merma_con_comprobante_seguro_y_revision_ajena(base, comprobantes_temporales):
    personas, ana, libro_a, cuaderno = base
    c = cliente(personas["op"])
    respuesta = c.post(reverse("inventario:registro_nuevo"), {"tipo": "entrada", "articulo": libro_a.pk, "cantidad": "5", "motivo": "Compra", "comprobante": SimpleUploadedFile("ticket.jpg", jpeg_con_ubicacion(), content_type="image/jpeg")})
    registro = RegistroInventario.objects.get()
    assert respuesta.url == reverse("inventario:registro", args=[registro.pk]) and inventario.existencias()[libro_a.pk] == 15
    archivo = registro.archivo_comprobante
    from PIL import Image

    guardado = comprobantes.leer(archivo)
    assert not Image.open(BytesIO(guardado)).getexif() and (archivo.archivo, archivo.sha256) in comprobantes.todos()
    descarga = c.get(reverse("inventario:registro_descargar", args=[registro.pk]))
    assert descarga["Content-Disposition"].startswith("attachment") and descarga["X-Content-Type-Options"] == "nosniff" and descarga["Content-Security-Policy"] == "sandbox"
    assert cliente(personas["op2"]).get(reverse("inventario:registro_descargar", args=[registro.pk])).status_code == 403
    assert cliente(personas["op"]).post(reverse("inventario:registro_revisar", args=[registro.pk]), {"resultado": "revisado"}).status_code == 403
    with pytest.raises(inventario.RevisionPropia):
        inventario.revisar_registro(registro, personas["op"], "revisado")
    inventario.vender(ana, [(cuaderno.pk, 1)], Venta.ADEUDO, personas["sup"])
    inventario.registrar_movimiento("merma", cuaderno, 2, "Se mojaron", "", personas["sup"])
    assert inventario.existencias()[cuaderno.pk] == 17
    merma = RegistroInventario.objects.get(tipo="merma")
    with pytest.raises(inventario.RevisionPropia):
        inventario.revisar_registro(merma, personas["sup"], "revisado")
    inventario.revisar_registro(merma, personas["sup2"], "revisado")
    merma.refresh_from_db()
    assert merma.revision == "revisado" and merma.revisado_por == personas["sup2"]


@pytest.mark.parametrize("nombre", ["html", "pdf_javascript", "pdf_lanzar", "jpeg_falso", "pdf_cifrado", "ejecutable"])
def test_comprobante_malicioso_no_registra_nada(base, nombre):
    personas, ana, libro_a, cuaderno = base
    respuesta = cliente(personas["op"]).post(reverse("inventario:registro_nuevo"), {"tipo": "entrada", "articulo": libro_a.pk, "cantidad": "5", "motivo": "Compra", "comprobante": SimpleUploadedFile("ticket.pdf", MALICIOSOS[nombre] or b"x", content_type="application/pdf")})
    assert respuesta.status_code == 200 and not RegistroInventario.objects.exists() and not ComprobanteInventario.objects.exists()
    assert inventario.existencias()[libro_a.pk] == 10


def test_lista_para_contar_sin_existencias_y_sin_formulas(base):
    personas, ana, libro_a, cuaderno = base
    Articulo.objects.create(clave="X-1", nombre='=HYPERLINK("http://ejemplo.invalid","x")', precio=100, concepto=ConceptoCobro.objects.get(nombre="Extras"))
    contenido = cliente(personas["op"]).get(reverse("inventario:conteo_lista")).content.decode("utf-8-sig")
    lineas = contenido.splitlines()
    assert lineas[0] == "clave,nombre,cantidad"
    assert all(linea.endswith(",") for linea in lineas[1:]) and "10" not in contenido and "20" not in contenido
    assert "'=HYPERLINK" in contenido
    existencias = cliente(personas["sup"]).get(reverse("inventario:existencias_csv")).content.decode("utf-8-sig")
    assert "'=HYPERLINK" in existencias and "LIB-A,Libro A,350.00,10" in existencias
    assert cliente(personas["op"]).get(reverse("inventario:existencias_csv")).status_code == 403
    assert "Existencia" not in cliente(personas["op"]).get(reverse("inventario:indice")).content.decode()


def subir(usuario, nombre, contenido):
    return cliente(usuario).post(reverse("inventario:conteo"), {"forma": "archivo", "archivo": SimpleUploadedFile(nombre, contenido)})


def xlsx(filas):
    libro_xlsx = Workbook()
    hoja = libro_xlsx.active
    for fila in filas:
        hoja.append(fila)
    salida = BytesIO()
    libro_xlsx.save(salida)
    return salida.getvalue()


@pytest.mark.parametrize(
    "nombre,contenido,mensaje",
    [
        ("c.csv", b"clave,cantidad\nNOEXISTE,3\n", "clave desconocida"),
        ("c.csv", b"clave,cantidad\nLIB-A,3\nlib-a,4\n", "se repite"),
        ("c.csv", b"clave,cantidad\nLIB-A,-3\n", "fórmula o un signo"),
        ("c.csv", b"clave,cantidad\nLIB-A,2.5\n", "número entero"),
        ("c.csv", b"clave,cantidad\nLIB-A,=1+2\n", "fórmula"),
        ("c.csv", b"clave,cantidad\n=CMD(),1\n", "fórmula"),
        ("c.csv", b"codigo,cosa\nLIB-A,3\n", "columnas"),
        ("c.csv", b"clave,cantidad\n" + b"LIB-A,1\n" * 5001, "renglones"),
        ("c.csv", b"clave,cantidad\nLIB-A,1\n" + b"x" * (1024 * 1024), "1 MB"),
        ("c.csv", b"%PDF-1.4 no es una hoja", "Excel"),
        ("c.xlsx", b"PK\x03\x04 no es un excel", "Excel"),
    ],
    ids=["clave_desconocida", "clave_repetida", "cantidad_negativa", "cantidad_decimal", "formula_en_cantidad", "formula_en_clave", "sin_columnas", "demasiados_renglones", "mas_de_un_mega", "pdf_disfrazado", "zip_roto"],
)
def test_conteo_subido_es_dato_no_confiable(base, nombre, contenido, mensaje):
    personas, ana, libro_a, cuaderno = base
    respuesta = subir(personas["op"], nombre, contenido)
    assert respuesta.status_code == 200 and mensaje in respuesta.content.decode()
    assert Conteo.objects.count() == 1


def test_conteo_xlsx_con_formula_se_rechaza(base):
    personas, ana, libro_a, cuaderno = base
    respuesta = subir(personas["op"], "c.xlsx", xlsx([["clave", "cantidad"], ["LIB-A", "=2+3"]]))
    assert "fórmulas" in respuesta.content.decode() and Conteo.objects.count() == 1
    bueno = subir(personas["op"], "c.xlsx", xlsx([["clave", "cantidad"], ["LIB-A", 8], ["cua-1", 20]]))
    conteo = Conteo.objects.latest("id")
    assert bueno.url == reverse("inventario:conteo_detalle", args=[conteo.pk])
    assert {r.articulo.clave: (r.contado, r.esperado, r.diferencia) for r in conteo.renglones.select_related("articulo")} == {"LIB-A": (8, 10, -2), "CUA-1": (20, 20, 0)}


def test_conteo_fijo_un_solo_en_espera_y_ajuste_del_momento(base):
    personas, ana, libro_a, cuaderno = base
    subir(personas["op"], "c.csv", b"clave,cantidad\nLIB-A,7\n")
    conteo = Conteo.objects.latest("id")
    assert not conteo.inicial and conteo.solicitud.estado == Solicitud.PENDIENTE
    renglon = conteo.renglones.get()
    with pytest.raises(RegistroInmutable):
        renglon.save()
    with pytest.raises(RegistroInmutable):
        RenglonConteo.objects.update(contado=10)
    with pytest.raises(RegistroInmutable):
        Conteo.objects.filter(pk=conteo.pk).update(usuario=personas["sup"])
    otra = subir(personas["op2"], "c.csv", b"clave,cantidad\nLIB-A,9\n")
    assert "Ya hay un conteo en espera" in otra.content.decode() and Conteo.objects.count() == 2
    inventario.vender(ana, [(libro_a.pk, 2)], Venta.ADEUDO, personas["op"])
    with pytest.raises(motor.ErrorSolicitud):
        motor.aprobar(conteo.solicitud, personas["op"])
    with pytest.raises(motor.ErrorSolicitud):
        motor.autorizar_con_codigo(conteo.solicitud, personas["op"], personas["op"], "000000")
    motor.aprobar(conteo.solicitud, personas["sup"])
    conteo.refresh_from_db()
    assert conteo.aplicado_por == personas["sup"]
    assert MovimientoInventario.objects.get(conteo=conteo).cantidad == -3
    assert inventario.existencias()[libro_a.pk] == 5
    assert subir(personas["op"], "c.csv", b"clave,cantidad\nLIB-A,5\n").status_code == 302


def test_conteo_rechazado_o_caducado_libera_la_espera(base):
    personas, ana, libro_a, cuaderno = base
    primero = inventario.subir_conteo({libro_a.pk: 1}, personas["op"], Conteo.PANTALLA)
    motor.rechazar(primero.solicitud, personas["sup"], "recontar")
    segundo = inventario.subir_conteo({libro_a.pk: 2}, personas["op"], Conteo.PANTALLA)
    Solicitud.objects.filter(pk=segundo.solicitud_id).update(caduca_en=timezone.now() - timedelta(minutes=1))
    tercero = inventario.subir_conteo({libro_a.pk: 3}, personas["op"], Conteo.PANTALLA)
    assert tercero.solicitud.estado == Solicitud.PENDIENTE and not MovimientoInventario.objects.filter(conteo__in=[primero, segundo]).exists()


@pytest.mark.django_db(transaction=True)
def test_dos_conteos_simultaneos_solo_uno_queda_en_espera():
    roles = configurar("escuela")
    op, op2 = nuevo_usuario("operacion", roles["Operación"]), nuevo_usuario("operacion2", roles["Operación"])
    fijar("modulo_inventario", 1)
    articulo = Articulo.objects.create(clave="CUA-1", nombre="Cuaderno", precio=5000, concepto=ConceptoCobro.objects.get(nombre="Libros"))
    barrera = threading.Barrier(2)
    errores, hechos = [], []

    def trabajar(usuario, cantidad):
        try:
            barrera.wait()
            hechos.append(inventario.subir_conteo({articulo.pk: cantidad}, usuario, Conteo.PANTALLA))
        except inventario.ErrorInventario as error:
            errores.append(error)
        finally:
            connection.close()

    hilos = [threading.Thread(target=trabajar, args=(u, n)) for u, n in ((op, 4), (op2, 5))]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert len(hechos) == 1 and len(errores) == 1
    assert Solicitud.objects.filter(accion="conteo_inventario", estado=Solicitud.PENDIENTE).count() == 1


def test_carga_inicial_y_aviso_de_conteo_sin_aprobar(base):
    personas, ana, libro_a, cuaderno = base
    assert set(MovimientoInventario.objects.values_list("tipo", flat=True)) == {MovimientoInventario.CARGA_INICIAL}
    conteo = inventario.subir_conteo({cuaderno.pk: 19}, personas["op"], Conteo.PANTALLA)
    with connection.cursor() as cursor:
        cursor.execute("UPDATE inventario_conteo SET creado = %s WHERE id = %s", [timezone.now() - timedelta(days=5), conteo.pk])
    assert "espera aprobación" in cliente(personas["dir"]).get(reverse("inicio")).content.decode()
    assert "espera aprobación" not in cliente(personas["op"]).get(reverse("inicio")).content.decode()
    motor.aprobar(conteo.solicitud, personas["sup"])
    assert MovimientoInventario.objects.get(conteo=conteo).tipo == MovimientoInventario.AJUSTE


def test_conteo_ajeno_solo_lo_ven_quien_lo_subio_y_quien_aprueba(base):
    personas, ana, libro_a, cuaderno = base
    conteo = inventario.subir_conteo({cuaderno.pk: 19}, personas["op"], Conteo.PANTALLA)
    url = reverse("inventario:conteo_detalle", args=[conteo.pk])
    assert cliente(personas["op"]).get(url).status_code == 200
    assert cliente(personas["op2"]).get(url).status_code == 403
    assert cliente(personas["sup"]).get(url).status_code == 200


def test_aviso_de_minimo_y_resumen_en_el_corte_mayor(base):
    personas, ana, libro_a, cuaderno = base
    inventario.vender(ana, [(libro_a.pk, 9)], Venta.ADEUDO, personas["op"])
    assert "Libro A" in cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    hoy = timezone.localdate()
    cifras = calculo.cifras_mayor(hoy.replace(day=1), hoy)
    seccion = next(s for s in cifras["secciones"] if s["clave"] == "inventario")
    fila = next(f for f in seccion["filas"] if f["clave"] == "LIB-A")
    assert fila["ventas"] == 9 and fila["existencia_al_cierre"] == 1 and fila["ajustes"] == 10
    for nivel in ("completo", "solo_nombres", "sin_nombres"):
        assert any(s["clave"] == "inventario" and s["filas"] for s in vista(cifras, nivel)["secciones"])


def test_ingresos_del_corte_no_cuentan_el_saldo_a_favor_por_devolucion(base):
    personas, ana, libro_a, cuaderno = base
    turno = turno_de(personas["op"])
    venta = inventario.vender(ana, [(libro_a.pk, 1)], Venta.AHORA, personas["op"])
    cobrar_venta(cliente(personas["op"]), ana, venta, 35000)
    inventario.devolver(venta, {str(venta.renglones.get().pk): [1, True]}, Devolucion.SALDO, personas["op"], "x")
    hoy = timezone.localdate()
    cifras = calculo.cifras_mayor(hoy.replace(day=1), hoy)
    assert cifras["totales"]["ingresos"] == 35000
    assert all(f["medio"] != "Saldo a favor por devolución de artículos" for f in next(s for s in cifras["secciones"] if s["clave"] == "ingresos_por_medio")["filas"])
    assert turno.pk


def test_modulo_apagado_oculta_todo(base):
    personas, ana, libro_a, cuaderno = base
    c = cliente(personas["dir"])
    assert 'href="/inventario/"' in c.get(reverse("inicio")).content.decode()
    fijar("modulo_inventario", 0)
    assert 'href="/inventario/"' not in c.get(reverse("inicio")).content.decode()
    for nombre in ("inventario:indice", "inventario:vender", "inventario:vender_publico", "inventario:conteo", "inventario:revision", "inventario:articulos"):
        assert c.get(reverse(nombre)).status_code == 404, nombre
    with pytest.raises(inventario.ErrorInventario):
        inventario.vender(ana, [(libro_a.pk, 1)], Venta.ADEUDO, personas["dir"])
    assert "Vender artículos" not in c.get(reverse("titulares:detalle", args=[ana.pk])).content.decode()


def test_configuracion_del_inventario_con_bitacora(base):
    personas, ana, libro_a, cuaderno = base
    c = cliente(personas["dir"])
    assert cliente(personas["sup"]).get(reverse("configuracion:inventario")).status_code == 403
    respuesta = c.post(reverse("configuracion:inventario"), {"modulo_inventario": "on", "dias_devolucion": "7", "dias_conteo_sin_aprobar": "4"})
    assert respuesta.url == reverse("configuracion:indice")
    assert parametro("devoluciones_inventario") == 0 and parametro("dias_devolucion") == 7
    assert Evento.objects.filter(accion="inventario_configurado").latest("numero").datos["cambios"]["devoluciones_inventario"] == [True, False]


def test_plantillas_llevan_permisos_politicas_y_parametros_sin_articulos(db):
    for nombre in ("escuela", "generico"):
        datos = plantillas.leer(nombre)
        assert datos["inventario"] == {"modulo_inventario": False, "devoluciones_inventario": True, "dias_devolucion": 15, "dias_conteo_sin_aprobar": 2}
        roles = {r["nivel"]: set(r["permisos"]) for r in datos["roles"]}
        assert {"vender_articulos", "registrar_movimientos_inventario", "subir_conteo_inventario", "devolver_articulos"} <= roles[1]
        assert not {"revisar_inventario", "administrar_articulos"} & roles[1]
        assert {"revisar_inventario", "administrar_articulos"} <= roles[2] <= roles[3] | roles[2]
        assert {"conteo_inventario", "devolucion_efectivo"} <= {p["accion"] for p in datos["politicas"]}
        assert "articulos" not in datos
    with pytest.raises(esquema.PlantillaInvalida):
        esquema.validar({**plantillas.leer("escuela"), "inventario": {"modulo_inventario": "sí"}})
    with pytest.raises(esquema.PlantillaInvalida):
        esquema.validar({**plantillas.leer("escuela"), "inventario": {"articulos": []}})
    configurar("escuela")
    assert plantillas.exportar()["inventario"]["dias_devolucion"] == 15


def test_migracion_agrega_politicas_y_permisos_a_instalaciones_existentes(db):
    from django.apps import apps as registro

    configurar("escuela")
    PoliticaAccion.objects.filter(accion__in=["conteo_inventario", "devolucion_efectivo"]).delete()
    from cuentas.models import PermisoRol

    nuevos = ["vender_articulos", "registrar_movimientos_inventario", "subir_conteo_inventario", "devolver_articulos", "revisar_inventario", "administrar_articulos"]
    PermisoRol.objects.filter(permiso__in=nuevos).delete()
    migracion = importlib.import_module("solicitudes.migrations.0008_inventario_en_instalaciones")
    migracion.agregar(registro, None)
    assert PoliticaAccion.objects.get(accion="conteo_inventario").permiso_solicitar == "subir_conteo_inventario"
    assert PoliticaAccion.objects.get(accion="devolucion_efectivo").permiso_aprobar == "aprobar_solicitudes"
    operacion = set(PermisoRol.objects.filter(rol__nombre="Operación").values_list("permiso", flat=True))
    supervision = set(PermisoRol.objects.filter(rol__nombre="Supervisión").values_list("permiso", flat=True))
    assert {"vender_articulos", "devolver_articulos", "registrar_movimientos_inventario", "subir_conteo_inventario"} <= operacion
    assert not {"revisar_inventario", "administrar_articulos"} & operacion
    assert set(nuevos) <= supervision


def test_asistente_pregunta_por_el_inventario(db, credencial):
    from django.test import Client

    from configuracion.models import Negocio
    from proyecto.ajustes_pruebas import TOKEN_ASISTENTE

    c = Client()
    from django.conf import settings

    c.cookies[settings.COOKIE_DISPOSITIVO] = credencial
    pagina = c.get(reverse("asistente:inicio")).content.decode()
    assert 'name="inventario"' in pagina
    c.post(reverse("asistente:inicio"), {"token": TOKEN_ASISTENTE, "nombre": "Negocio de prueba", "zona_horaria": "America/Mexico_City", "moneda": "MXN", "plantilla": "escuela", "inventario": "on"})
    assert parametro("modulo_inventario") == 1 and Negocio.objects.exists()
    assert Evento.objects.filter(accion="asistente_inventario").exists()
