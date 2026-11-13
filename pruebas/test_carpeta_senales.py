import threading
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.db import connection
from django.urls import reverse

from auditoria.models import Evento
from banco import carpeta, conciliacion, lectura
from banco.models import Importacion, MovimientoBancario, TopeDiarioBanco
from cobros import libro
from cobros.models import Cargo, ConceptoCobro, Pago, ReversionPago
from configuracion.models import Negocio, Parametro, hoy_negocio
from titulares.models import Familia, Titular

from .banco_ayudas import cuenta_principal, estado, pdf, saldo_final, spei
from .conftest import cliente, configurar, nuevo_usuario
from .libro_ayudas import preparar_conceptos, titular_activo


def fijar(clave, valor):
    Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})


def topes(acumulado, diario=10000000):
    fijar("tope_aplicado_sin_respaldo", acumulado)
    for numero in range(7):
        TopeDiarioBanco.objects.update_or_create(dia=numero, defaults={"importe": diario})


def aprender(con_saldo=False):
    titulos = ["fecha", "referencia", "importe"] + (["saldo"] if con_saldo else [])
    conciliacion.recordar_columnas(cuenta_principal(), [titulos], 0, {papel: i for i, papel in enumerate(titulos)})


def hoja(filas, con_saldo=False):
    lineas = ["fecha,referencia,importe" + (",saldo" if con_saldo else "")]
    for fila in filas:
        lineas.append(",".join(str(v) for v in fila))
    return ("\n".join(lineas) + "\n").encode()


def importar(nombre, contenido):
    return carpeta.importar_contenido(nombre, contenido, lectura.huella_archivo(contenido))


def dia(atras=1):
    return (hoy_negocio() - timedelta(days=atras)).isoformat()


def pagos_banco():
    return Pago.objects.filter(medio=Pago.BANCO)


@pytest.fixture
def base(personas):
    cache.clear()
    preparar_conceptos()
    cuenta_principal()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    aprender()
    return personas, ana


def test_con_tope_cero_todo_archivo_editable_queda_retenido(base):
    personas, ana = base
    importacion = importar("movs.csv", hoja([[dia(), ana.matricula, "300.00"], [dia(), ana.matricula, "200.00"]]))
    assert importacion.retenida and not pagos_banco().exists()
    retenidos = list(conciliacion.retenidos(importacion))
    assert len(retenidos) == 2 and all("tope_exposicion" in m.retencion for m in retenidos)
    assert all(m.sugerencia == ana.matricula for m in retenidos)
    assert "retenidas" in cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    pagina = cliente(personas["sup"]).get(reverse("conciliacion:importacion", args=[importacion.pk])).content.decode()
    assert "Rebasaría el tope" in pagina and "Liberar los marcados" in pagina


def test_con_tope_suficiente_aplica_de_inmediato(base):
    personas, ana = base
    topes(10000000)
    importacion = importar("movs.csv", hoja([[dia(), ana.matricula, "300.00"]]))
    assert not importacion.retenida and importacion.aplicados == 1
    pago = pagos_banco().get()
    assert pago.registrado_por is None and pago.titular == ana and pago.importe == 30000
    assert conciliacion.expuesto() == 30000


def test_liberar_parcial_exige_conciliacion_y_quien_libera_no_revisa(base):
    personas, ana = base
    importacion = importar("movs.csv", hoja([[dia(), ana.matricula, "300.00"], [dia(2), ana.matricula, "200.00"]]))
    primero, segundo = conciliacion.retenidos(importacion).order_by("id")
    url = reverse("conciliacion:liberar", args=[importacion.pk])
    assert cliente(personas["op"]).post(url, {"alcance": "elegidos", "movimiento": [primero.pk]}).status_code == 403
    with pytest.raises(conciliacion.ErrorLiberacion):
        conciliacion.liberar(importacion, personas["op"], movimientos=[primero.pk])
    cliente(personas["sup"]).post(url, {"alcance": "elegidos", "movimiento": [primero.pk]})
    primero.refresh_from_db()
    segundo.refresh_from_db()
    assert primero.estado == MovimientoBancario.APLICADO and primero.liberado_por == personas["sup"]
    assert segundo.retenido and pagos_banco().count() == 1
    importacion.refresh_from_db()
    assert importacion.liberada_por == personas["sup"] and importacion.liberada_en is None
    evento = Evento.objects.filter(accion="importacion_liberada").latest("numero")
    assert evento.usuario == personas["sup"] and evento.datos["parcial"] and evento.datos["liberados"][0]["movimiento"] == primero.pk
    with pytest.raises(conciliacion.RevisionPropia):
        conciliacion.marcar_revisada(importacion, personas["sup"])
    conciliacion.liberar(importacion, personas["sup2"])
    with pytest.raises(conciliacion.RevisionPropia):
        conciliacion.marcar_revisada(importacion, personas["sup2"])
    importacion.refresh_from_db()
    assert importacion.liberada_en is not None and pagos_banco().count() == 2
    with pytest.raises(conciliacion.ErrorLiberacion):
        conciliacion.liberar(importacion, personas["sup"])
    conciliacion.marcar_revisada(importacion, personas["dir"])


def test_confirmar_un_retenido_desde_la_cola_cuenta_como_liberarlo(base):
    personas, ana = base
    importacion = importar("movs.csv", hoja([[dia(), ana.matricula, "300.00"]]))
    movimiento = conciliacion.retenidos(importacion).get()
    conciliacion.confirmar(movimiento, ana, personas["sup"])
    movimiento.refresh_from_db()
    assert movimiento.liberado_por == personas["sup"]
    with pytest.raises(conciliacion.RevisionPropia):
        conciliacion.marcar_revisada(importacion, personas["sup"])


def test_segundo_pago_sin_adeudo_que_cubrir_se_retiene(base):
    personas, ana = base
    topes(10000000)
    familia = Familia.objects.create(nombre="Familia Señales")
    Titular.objects.filter(pk=ana.pk).update(familia=familia)
    beto = titular_activo(personas["op"], personas["sup"], "Beto", familia=familia)
    importacion = importar("movs.csv", hoja([[dia(), ana.matricula, "1500.00"], [dia(), beto.matricula, "600.00"]]))
    assert not importacion.retenida and importacion.aplicados == 1
    retenido = conciliacion.retenidos(importacion).get()
    assert retenido.importe == 60000 and retenido.retencion == "excede_adeudo"
    assert sum(p.saldo for p in libro.pendientes_de([ana.pk, beto.pk])) == 50000


def test_pago_mayor_que_el_adeudo_se_retiene(base):
    personas, ana = base
    topes(10000000)
    importacion = importar("movs.csv", hoja([[dia(), ana.matricula, "1000.01"]]))
    assert conciliacion.retenidos(importacion).get().retencion == "excede_adeudo" and not pagos_banco().exists()


def test_misma_matricula_dos_veces_retiene_la_segunda(base):
    personas, ana = base
    topes(10000000)
    importacion = importar("movs.csv", hoja([[dia(), ana.matricula, "300.00"], [dia(), ana.matricula, "200.00"]]))
    assert importacion.aplicados == 1 and pagos_banco().get().importe == 30000
    assert conciliacion.retenidos(importacion).get().retencion == "matricula_repetida"


def test_tope_individual_fecha_futura_y_titular_inactivo(base):
    personas, ana = base
    topes(10000000)
    fijar("tope_pago_carpeta", 50000)
    beto = titular_activo(personas["op"], personas["sup"], "Beto")
    Titular.objects.filter(pk=beto.pk).update(estado=Titular.BAJA)
    carlos = titular_activo(personas["op"], personas["sup"], "Carlos")
    importacion = importar("movs.csv", hoja([[dia(), ana.matricula, "900.00"], [dia(-3), carlos.matricula, "100.00"], [dia(), beto.matricula, "100.00"]]))
    motivos = {m.sugerencia: m.retencion for m in conciliacion.retenidos(importacion)}
    assert motivos == {ana.matricula: "tope_pago", carlos.matricula: "fecha_futura", beto.matricula: "titular_inactivo"}
    assert not pagos_banco().exists()


def test_movimiento_en_periodo_de_un_estado_que_no_lo_trae_se_retiene(base):
    personas, ana = base
    topes(10000000)
    importar_pdf(personas["sup"], [spei(5, 1000)])
    importacion = importar("movs.csv", hoja([["2026-08-12", ana.matricula, "300.00"]]))
    assert conciliacion.retenidos(importacion).get().retencion == "fuera_de_estado"


def importar_pdf(usuario, movimientos, **opciones):
    contenido = pdf(estado(movimientos, **opciones))
    cuenta, lista, resumen = conciliacion.movimientos_de_pdf(lectura.lineas_de_pdf(contenido))
    return conciliacion.importar(cuenta, lista, Importacion.ESTADO_PDF, "agosto.pdf", lectura.huella_archivo(contenido), usuario, resumen)


def test_saldos_que_no_cuadran_retienen_todo_el_archivo_sin_rechazarlo(base):
    personas, ana = base
    topes(10000000)
    aprender(con_saldo=True)
    importacion = importar("movs.csv", hoja([[dia(2), ana.matricula, "300.00", "1300.00"], [dia(), ana.matricula, "100.00", "1500.00"]], con_saldo=True))
    assert importacion.retenida and not pagos_banco().exists()
    assert all(m.retencion == "saldos_no_cuadran" for m in conciliacion.retenidos(importacion))


def test_saldo_que_no_continua_retiene_y_el_que_continua_aplica(base):
    personas, ana = base
    topes(10000000)
    agosto = [spei(5, 1000)]
    importar_pdf(personas["sup"], agosto)
    conocido = saldo_final(agosto)
    aprender(con_saldo=True)
    roto = importar("roto.csv", hoja([["2026-09-02", ana.matricula, "300.00", f"{(conocido + 99999) / 100:.2f}"]], con_saldo=True))
    assert roto.retenida and conciliacion.retenidos(roto).get().retencion == "saldo_no_continua"
    sigue = importar("sigue.csv", hoja([["2026-09-03", ana.matricula, "200.00", f"{(conocido + 20000) / 100:.2f}"]], con_saldo=True))
    assert not sigue.retenida and sigue.aplicados == 1


def test_tope_de_exposicion_suma_lo_ya_aplicado_sin_respaldo(base):
    personas, ana = base
    topes(150000)
    otro = ConceptoCobro.objects.get(nombre="Libros")
    libro.crear_cargo(ana, otro, 500000, hoy_negocio(), Cargo.MANUAL, usuario=personas["op"])
    primero = importar("uno.csv", hoja([[dia(), ana.matricula, "1000.00"]]))
    assert primero.aplicados == 1
    segundo = importar("dos.csv", hoja([[dia(), ana.matricula, "600.00"]]))
    assert segundo.retenida and conciliacion.retenidos(segundo).get().retencion == "tope_exposicion"
    assert conciliacion.expuesto() == 100000
    pago = pagos_banco().get()
    libro.revertir_pago(pago, "prueba", personas["dir"])
    assert conciliacion.expuesto() == 0


@pytest.mark.django_db(transaction=True)
def test_dos_archivos_a_la_vez_no_rebasan_juntos_el_tope():
    roles = configurar("escuela")
    op, sup = nuevo_usuario("operacion", roles["Operación"]), nuevo_usuario("supervision", roles["Supervisión"])
    preparar_conceptos()
    cuenta_principal()
    ana = titular_activo(op, sup, "Ana")
    libro.crear_cargo(ana, ConceptoCobro.objects.get(nombre="Libros"), 900000, hoy_negocio(), Cargo.MANUAL, usuario=op)
    aprender()
    topes(150000)
    contenidos = [hoja([[dia(), ana.matricula, "1000.00"]]), hoja([[dia(2), ana.matricula, "1000.00"]])]
    barrera = threading.Barrier(2)
    errores = []

    def trabajar(contenido, nombre):
        try:
            barrera.wait()
            importar(nombre, contenido)
        except Exception as error:
            errores.append(error)
        finally:
            connection.close()

    hilos = [threading.Thread(target=trabajar, args=(c, f"a{i}.csv")) for i, c in enumerate(contenidos)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert not errores, errores
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 1
    assert MovimientoBancario.objects.exclude(retencion="").filter(retencion__contains="tope_exposicion").count() == 1


def test_estado_sin_el_pago_lo_marca_sin_respaldo_y_no_lo_revierte(base):
    personas, ana = base
    topes(10000000)
    importar("movs.csv", hoja([["2026-08-12", ana.matricula, "300.00"]]))
    pago = pagos_banco().get()
    importar_pdf(personas["sup"], [spei(5, 1000)])
    movimiento = MovimientoBancario.objects.get(pago=pago)
    assert movimiento.sin_respaldo and not ReversionPago.objects.exists()
    assert Evento.objects.filter(accion="pago_sin_respaldo", objeto_id=str(movimiento.pk)).exists()
    for quien in ("sup", "dir"):
        inicio = cliente(personas[quien]).get(reverse("inicio")).content.decode()
        assert "Pagos sin respaldo en el estado" in inicio and reverse("cobros:revertir", args=[pago.pk]) in inicio
    assert "Pagos sin respaldo en el estado" not in cliente(personas["op"]).get(reverse("inicio")).content.decode()


def test_alerta_de_antiguedad_sin_estado(base):
    personas, ana = base
    topes(10000000)
    importar("movs.csv", hoja([[dia(50), ana.matricula, "300.00"]]))
    assert list(conciliacion.antiguos_sin_respaldo()) == list(MovimientoBancario.objects.filter(estado=MovimientoBancario.APLICADO))
    assert "Pagos sin un estado que los respalde" in cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    fijar("dias_sin_respaldo_alerta", 60)
    assert not conciliacion.antiguos_sin_respaldo().exists()


def test_la_carpeta_aplica_por_el_camino_vigilado(base, tmp_path):
    personas, ana = base
    topes(10000000)
    vigilada = tmp_path / "banco"
    Negocio.objects.filter(pk=1).update(carpeta_banco=carpeta.validar_carpeta(str(vigilada)))
    (vigilada / "hoy.csv").write_bytes(hoja([[dia(), ana.matricula, "300.00"]]))
    carpeta.revisar()
    assert carpeta.revisar()["importados"] == 1
    assert pagos_banco().get().movimiento.importacion.origen == Importacion.CARPETA


def test_importacion_manual_de_archivo_no_cambia(base):
    personas, ana = base
    from django.core.files.uploadedfile import SimpleUploadedFile

    c = cliente(personas["sup"])
    r = c.post(reverse("conciliacion:importar"), {"archivo": SimpleUploadedFile("m.csv", hoja([[dia(), ana.matricula, "300.00"]])), "cuenta": cuenta_principal().pk})
    c.post(r.url, {"fecha": "0", "referencia": "1", "importe": "2"})
    c.post(reverse("conciliacion:previa", args=[r.url.split("/")[-3]]))
    importacion = Importacion.objects.get(origen=Importacion.MANUAL)
    assert not importacion.retenida and importacion.aplicados == 1 and not conciliacion.retenidos(importacion).exists()


def test_configuracion_pide_el_tope_por_pago_y_los_topes_viven_en_su_pantalla(base, tmp_path):
    personas, ana = base
    c = cliente(personas["dir"])
    pagina = c.get(reverse("configuracion:carpeta_banco")).content.decode()
    assert "tope_aplicado_sin_respaldo" not in pagina and "tope_pago_carpeta" in pagina
    respuesta = c.post(reverse("configuracion:carpeta_banco"), {"carpeta_banco": str(tmp_path / "v"), "tope_aplicado_sin_respaldo": "5000.00", "tope_pago_carpeta": "1500.00"})
    assert respuesta.status_code == 302
    from configuracion.models import parametro

    assert parametro("tope_aplicado_sin_respaldo") == 0 and parametro("tope_pago_carpeta") == 150000
    evento = Evento.objects.filter(accion="carpeta_banco_cambiada").latest("numero")
    assert evento.datos["cambios"]["tope_pago_carpeta"] == [0, 150000] and "tope_aplicado_sin_respaldo" not in evento.datos["cambios"]
