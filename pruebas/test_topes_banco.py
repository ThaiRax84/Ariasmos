import importlib
import threading
from datetime import timedelta

import pytest
from django.apps import apps as registro_apps
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.urls import reverse

from auditoria import servicios as auditoria
from auditoria.models import Evento
from banco import carpeta, conciliacion, lectura
from banco.models import Importacion, MovimientoBancario, TopeDiarioBanco
from cobros import libro
from cobros.models import Cargo, ConceptoCobro, Pago
from configuracion.models import Parametro, hoy_negocio, parametro
from cuentas.models import PermisoRol, Rol

from .banco_ayudas import cuenta_principal
from .conftest import cliente, configurar, nuevo_usuario
from .libro_ayudas import preparar_conceptos, titular_activo

GRANDE = 10 ** 9


def fijar_topes(diario, acumulado=GRANDE, dias=None):
    for numero in range(7):
        valor = dias.get(numero, diario) if dias else diario
        TopeDiarioBanco.objects.update_or_create(dia=numero, defaults={"importe": valor})
    Parametro.objects.update_or_create(clave="tope_aplicado_sin_respaldo", defaults={"valor": str(acumulado)})


def aprender():
    titulos = ["fecha", "referencia", "importe"]
    conciliacion.recordar_columnas(cuenta_principal(), [titulos], 0, {papel: i for i, papel in enumerate(titulos)})


def hoja(filas):
    return ("\n".join(["fecha,referencia,importe"] + [",".join(str(v) for v in fila) for fila in filas]) + "\n").encode()


def importar(nombre, filas):
    contenido = hoja(filas)
    return carpeta.importar_contenido(nombre, contenido, lectura.huella_archivo(contenido))


def dia(atras=1, hoy=None):
    return ((hoy or hoy_negocio()) - timedelta(days=atras)).isoformat()


def con_adeudo(op, sup, nombre):
    titular = titular_activo(op, sup, nombre)
    libro.crear_cargo(titular, ConceptoCobro.objects.get(nombre="Libros"), 10000000, hoy_negocio(), Cargo.MANUAL, usuario=op)
    return titular


@pytest.fixture
def base(personas):
    cache.clear()
    preparar_conceptos()
    cuenta_principal()
    aprender()
    titulares = [con_adeudo(personas["op"], personas["sup"], nombre) for nombre in ("Ana", "Beto", "Caro", "Dario")]
    return personas, titulares


def pagos():
    return Pago.objects.filter(medio=Pago.BANCO)


def test_todo_en_cero_al_instalar(roles):
    assert conciliacion.topes_diarios() == [0] * 7
    assert parametro("tope_aplicado_sin_respaldo") == 0
    assert TopeDiarioBanco.objects.count() == 7


def test_justo_en_el_tope_aplica_y_un_centavo_arriba_retiene(base):
    personas, (ana, beto, *_) = base
    fijar_topes(50000)
    primera = importar("a.csv", [[dia(), ana.matricula, "500.00"]])
    assert primera.aplicados == 1 and conciliacion.aplicado_solo_en(hoy_negocio()) == 50000
    fijar_topes(50000 + 30000)
    segunda = importar("b.csv", [[dia(), beto.matricula, "300.01"]])
    assert segunda.aplicados == 0
    retenido = conciliacion.retenidos(segunda).get()
    assert retenido.retencion == "tope_dia" and "Tope del día" in retenido.motivos_retencion[0]
    assert not segunda.retenida


def test_se_evalua_en_el_orden_del_archivo_y_el_siguiente_puede_caber(base):
    personas, (ana, beto, caro, _) = base
    fijar_topes(100000)
    importacion = importar("a.csv", [[dia(), ana.matricula, "600.00"], [dia(), beto.matricula, "500.00"], [dia(), caro.matricula, "300.00"]])
    aplicados = sorted(MovimientoBancario.objects.filter(importacion=importacion, estado=MovimientoBancario.APLICADO).values_list("importe", flat=True))
    assert aplicados == [30000, 60000]
    assert list(conciliacion.retenidos(importacion).values_list("importe", "retencion")) == [(50000, "tope_dia")]
    assert conciliacion.aplicado_solo_en(hoy_negocio()) == 90000
    evento = Evento.objects.filter(accion="importacion_bancaria").latest("numero")
    assert evento.datos["tope_dia"] == 1


def test_dos_archivos_el_mismo_dia_comparten_el_tope(base):
    personas, (ana, beto, caro, _) = base
    fijar_topes(100000)
    importar("a.csv", [[dia(), ana.matricula, "700.00"]])
    segunda = importar("b.csv", [[dia(), beto.matricula, "400.00"], [dia(), caro.matricula, "300.00"]])
    assert segunda.aplicados == 1
    assert conciliacion.retenidos(segunda).get().importe == 40000
    assert conciliacion.aplicado_solo_en(hoy_negocio()) == 100000


def test_cambio_de_dia_usa_el_tope_del_dia_en_que_se_aplica(base, monkeypatch):
    personas, (ana, beto, caro, dario) = base
    hoy = hoy_negocio()
    manana = hoy + timedelta(days=1)
    fijar_topes(0, dias={hoy.weekday(): 50000, manana.weekday(): 80000})
    importar("a.csv", [[dia(3), ana.matricula, "500.00"]])
    assert conciliacion.aplicado_solo_en(hoy) == 50000
    monkeypatch.setattr(conciliacion, "hoy_negocio", lambda: manana)
    segunda = importar("b.csv", [[dia(3), beto.matricula, "500.00"], [dia(3), caro.matricula, "300.00"], [dia(3), dario.matricula, "100.00"]])
    assert segunda.aplicados == 2
    assert conciliacion.aplicado_solo_en(manana) == 80000 and conciliacion.aplicado_solo_en(hoy) == 50000
    assert MovimientoBancario.objects.filter(dia_aplicado_solo=manana).count() == 2
    assert conciliacion.retenidos(segunda).get().importe == 10000


def test_el_dia_es_el_de_aplicar_y_no_la_fecha_del_movimiento(base):
    personas, (ana, *_) = base
    hoy = hoy_negocio()
    fijar_topes(0, dias={hoy.weekday(): 50000})
    importacion = importar("a.csv", [[dia(1), ana.matricula, "500.00"]])
    assert importacion.aplicados == 1
    assert MovimientoBancario.objects.get(importacion=importacion).dia_aplicado_solo == hoy


def test_dia_en_cero_retiene_todo_lo_de_ese_dia(base):
    personas, (ana, beto, *_) = base
    hoy = hoy_negocio()
    fijar_topes(GRANDE, dias={hoy.weekday(): 0})
    importacion = importar("a.csv", [[dia(), ana.matricula, "0.01"], [dia(), beto.matricula, "200.00"]])
    assert importacion.aplicados == 0 and not pagos().exists()
    assert set(conciliacion.retenidos(importacion).values_list("retencion", flat=True)) == {"tope_dia"}


def test_liberados_no_consumen_el_tope_y_liberar_nunca_se_bloquea(base):
    personas, (ana, beto, caro, _) = base
    fijar_topes(0)
    importacion = importar("a.csv", [[dia(), ana.matricula, "900.00"]])
    aplicados, _ = conciliacion.liberar(importacion, personas["sup"])
    assert aplicados == 1 and pagos().count() == 1
    assert conciliacion.aplicado_solo_en(hoy_negocio()) == 0
    assert MovimientoBancario.objects.get(importacion=importacion).dia_aplicado_solo is None
    assert conciliacion.expuesto() == 90000
    fijar_topes(50000, acumulado=GRANDE)
    segunda = importar("b.csv", [[dia(), beto.matricula, "500.00"]])
    assert segunda.aplicados == 1


def test_confirmar_desde_la_cola_no_consume_el_tope(base):
    personas, (ana, *_) = base
    fijar_topes(0)
    importacion = importar("a.csv", [[dia(), ana.matricula, "300.00"]])
    movimiento = conciliacion.retenidos(importacion).get()
    conciliacion.confirmar(movimiento, ana, personas["sup"])
    assert conciliacion.aplicado_solo_en(hoy_negocio()) == 0


def test_el_acumulado_sigue_siendo_senal_del_archivo(base):
    personas, (ana, beto, *_) = base
    fijar_topes(GRANDE, acumulado=60000)
    importacion = importar("a.csv", [[dia(), ana.matricula, "300.00"], [dia(), beto.matricula, "400.00"]])
    assert importacion.retenida and importacion.aplicados == 0
    assert set(conciliacion.retenidos(importacion).values_list("retencion", flat=True)) == {"tope_exposicion"}
    assert conciliacion.aplicado_solo_en(hoy_negocio()) == 0


def test_la_importacion_manual_no_se_limita_ni_consume_el_tope_del_dia(base):
    from django.core.files.uploadedfile import SimpleUploadedFile

    personas, (ana, *_) = base
    fijar_topes(0, acumulado=0)
    c = cliente(personas["sup"])
    r = c.post(reverse("conciliacion:importar"), {"archivo": SimpleUploadedFile("m.csv", hoja([[dia(), ana.matricula, "300.00"]])), "cuenta": cuenta_principal().pk})
    c.post(r.url, {"fecha": "0", "referencia": "1", "importe": "2"})
    c.post(reverse("conciliacion:previa", args=[r.url.split("/")[-3]]))
    importacion = Importacion.objects.get(origen=Importacion.MANUAL)
    assert importacion.aplicados == 1
    assert conciliacion.aplicado_solo_en(hoy_negocio()) == 0


@pytest.mark.django_db(transaction=True)
def test_dos_importaciones_a_la_vez_no_rebasan_juntas_el_tope_del_dia():
    roles = configurar("escuela")
    op, sup = nuevo_usuario("operacion", roles["Operación"]), nuevo_usuario("supervision", roles["Supervisión"])
    preparar_conceptos()
    cuenta_principal()
    aprender()
    ana, beto = con_adeudo(op, sup, "Ana"), con_adeudo(op, sup, "Beto")
    fijar_topes(150000)
    archivos = [("a0.csv", [[dia(), ana.matricula, "1000.00"]]), ("a1.csv", [[dia(2), beto.matricula, "1000.00"]])]
    barrera = threading.Barrier(2)
    errores = []

    def trabajar(nombre, filas):
        try:
            barrera.wait()
            importar(nombre, filas)
        except Exception as error:
            errores.append(error)
        finally:
            connection.close()

    hilos = [threading.Thread(target=trabajar, args=archivo) for archivo in archivos]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert not errores, errores
    assert pagos().count() == 1
    assert MovimientoBancario.objects.filter(retencion="tope_dia").count() == 1
    assert conciliacion.aplicado_solo_en(hoy_negocio()) == 100000


def test_pantalla_de_topes_con_permiso_reingreso_y_bitacora(base):
    personas, (ana, *_) = base
    url = reverse("conciliacion:topes")
    assert cliente(personas["op"]).get(url).status_code == 403
    sin_reingreso = cliente(personas["sup"], reingreso=False).get(url)
    assert sin_reingreso.status_code == 302 and reverse("confirmar") in sin_reingreso.url
    c = cliente(personas["sup"])
    pagina = c.get(url).content.decode()
    assert "Aplicado solo hoy" in pagina and "Acumulado sin respaldo" in pagina and 'name="tope_lunes"' in pagina
    datos = {f"tope_{clave}": "5,000.00" for clave in conciliacion.DIAS_SEMANA}
    datos.update({"tope_domingo": "0", "tope_acumulado": "20,000.00"})
    assert c.post(url, datos).status_code == 302
    assert conciliacion.topes_diarios() == [500000] * 6 + [0]
    assert parametro("tope_aplicado_sin_respaldo") == 2000000
    evento = Evento.objects.filter(accion="topes_banco_cambiados").latest("numero")
    assert evento.usuario == personas["sup"]
    assert evento.datos["antes"]["lunes"] == 0 and evento.datos["despues"]["lunes"] == 500000
    assert evento.datos["antes"]["acumulado"] == 0 and evento.datos["despues"]["acumulado"] == 2000000
    assert "domingo" not in evento.datos["cambios"]
    total = Evento.objects.filter(accion="topes_banco_cambiados").count()
    c.post(url, datos)
    assert Evento.objects.filter(accion="topes_banco_cambiados").count() == total
    assert c.post(url, {**datos, "tope_lunes": "-5"}).status_code == 200
    assert conciliacion.topes_diarios()[0] == 500000


def test_la_pantalla_muestra_lo_aplicado_hoy_contra_el_tope(base):
    personas, (ana, *_) = base
    fijar_topes(100000, acumulado=300000)
    importar("a.csv", [[dia(), ana.matricula, "250.00"]])
    uso = conciliacion.uso_de_topes()
    assert (uso["aplicado_hoy"], uso["tope_hoy"], uso["acumulado"], uso["tope_acumulado"]) == (25000, 100000, 25000, 300000)
    pagina = cliente(personas["dir"]).get(reverse("conciliacion:topes")).content.decode()
    assert "$250.00" in pagina and "$1,000.00" in pagina and "$3,000.00" in pagina


def test_inicio_de_quien_audita_lista_cambios_ajenos_de_los_ultimos_7_dias(base, monkeypatch):
    personas, _ = base
    conciliacion.guardar_topes({clave: 100000 for clave in conciliacion.CLAVES_TOPES}, usuario=personas["sup"])
    pagina = cliente(personas["dir"]).get(reverse("inicio")).content.decode()
    assert "Cambios en los topes del banco" in pagina and "Persona supervision" in pagina and "$0.00 MXN → $1,000.00 MXN" in pagina
    assert "Cambios en los topes del banco" not in cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    assert "Cambios en los topes del banco" not in cliente(personas["op"]).get(reverse("inicio")).content.decode()
    conciliacion.guardar_topes({clave: 200000 for clave in conciliacion.CLAVES_TOPES}, usuario=personas["dir"])
    propios = conciliacion.cambios_de_topes_ajenos(personas["dir"])
    assert len(propios) == 1 and propios[0]["quien"] == "Persona supervision"


def test_cambios_viejos_ya_no_aparecen(base, monkeypatch):
    personas, _ = base
    hace = auditoria.timezone.now() - timedelta(days=8)
    monkeypatch.setattr(auditoria.timezone, "now", lambda: hace)
    conciliacion.guardar_topes({clave: 100000 for clave in conciliacion.CLAVES_TOPES}, usuario=personas["sup"])
    monkeypatch.undo()
    assert conciliacion.cambios_de_topes_ajenos(personas["dir"]) == []


def test_permiso_en_la_plantilla_y_la_migracion_lo_otorga_a_los_roles_existentes(roles):
    assert "configurar_topes_banco" in roles["Supervisión"].permisos() and "configurar_topes_banco" in roles["Dirección"].permisos()
    assert "configurar_topes_banco" not in roles["Operación"].permisos()
    PermisoRol.objects.filter(permiso="configurar_topes_banco").delete()
    propio = Rol.objects.create(nombre="Solo configuración")
    PermisoRol.objects.create(rol=propio, permiso="administrar_configuracion")
    migracion = importlib.import_module("cuentas.migrations.0007_topes_del_banco")
    migracion.otorgar(registro_apps, None)
    con_permiso = set(PermisoRol.objects.filter(permiso="configurar_topes_banco").values_list("rol__nombre", flat=True))
    assert con_permiso == {"Supervisión", "Dirección", "Solo configuración"}


def test_carpeta_banco_ya_no_pide_el_acumulado_y_el_asistente_pide_los_topes(db):
    c = Client()
    datos_inicio = {"token": settings.TOKEN_ASISTENTE, "nombre": "Mi negocio", "plantilla": "escuela", "zona_horaria": "America/Mexico_City"}
    assert c.post(reverse("asistente:inicio"), datos_inicio).status_code == 302
    pagina = c.get(reverse("asistente:cortes")).content.decode()
    assert 'name="tope_lunes"' in pagina and 'name="tope_acumulado"' in pagina and 'name="tope_aplicado_sin_respaldo"' not in pagina
    datos = {f"nivel_{tipo}": "solo_nombres" for tipo in ("diario", "mayor", "cobranza")}
    datos.update({f"tope_{clave}": "5000" for clave in conciliacion.DIAS_SEMANA[:6]})
    datos.update({"tope_domingo": "", "tope_acumulado": "15000", "guardada": "on", "tope_pago_carpeta": "0"})
    respuesta = c.post(reverse("asistente:cortes"), datos)
    assert respuesta.status_code == 302, respuesta.content.decode()[:2000]
    assert conciliacion.topes_diarios() == [500000] * 6 + [0]
    assert parametro("tope_aplicado_sin_respaldo") == 1500000
    evento = Evento.objects.filter(accion="topes_banco_cambiados").latest("numero")
    assert evento.usuario is None and evento.datos["origen"] == "asistente"
