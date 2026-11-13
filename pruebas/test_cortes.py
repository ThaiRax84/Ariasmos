import io
import json
import re
import threading
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.db import connection
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from auditoria.models import Evento
from banco import conciliacion
from banco.models import Importacion
from caja import servicios as caja
from caja.models import Turno
from cobros import libro
from cobros.models import Beca, Cargo, ConceptoCobro, Pago, PeriodoCerrado
from configuracion.models import Negocio, Parametro, hoy_negocio
from configuracion.trabajador import ejecutar_ciclo
from cortes import entrega, salida
from cortes import servicios as cortes
from cortes.models import COBRANZA, DIARIO, MAYOR, Corte, CorteCerrado, Destino, Entrega, ReglaDestino
from titulares.models import CampoContacto, Contacto, Familia, Titular
from titulares.servicios import crear_titular

from .banco_ayudas import cuenta_principal, estado, spei
from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo, turno_de, verificar_sumas


def mes_anterior():
    hoy = hoy_negocio()
    fin = hoy.replace(day=1) - timedelta(days=1)
    return fin.replace(day=1), fin


def destino(tmp_path, nombre="cortes", niveles=None):
    carpeta = tmp_path / nombre
    objeto = Destino.objects.create(nombre=nombre, ruta=str(carpeta))
    for tipo in (DIARIO, MAYOR, COBRANZA):
        ReglaDestino.objects.create(destino=objeto, tipo=tipo, nivel=(niveles or {}).get(tipo, "completo"))
    carpeta.mkdir(parents=True, exist_ok=True)
    return objeto


def cobrar(usuario, titular, importe, fecha=None):
    turno = caja.turno_abierto(usuario) or turno_de(usuario)
    return libro.registrar_pago(titular, importe, Pago.EFECTIVO, usuario, turno=turno, fecha=fecha)


def cerrar_caja(usuario):
    turno = caja.turno_abierto(usuario)
    return caja.cerrar_turno(turno, usuario, {"100000": 100}, nota="conteo de prueba")


def test_corte_diario_al_cerrar_turno_y_quien_lo_ve(personas, tmp_path):
    preparar_conceptos()
    destino(tmp_path)
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    cobrar(personas["op"], ana, 60000)
    cobrar(personas["op"], ana, 15000)
    cerrar_caja(personas["op"])
    corte = Corte.objects.get(tipo=DIARIO)
    assert corte.cerrado and corte.hash == salida.huella(corte.cifras) and corte.usuario == personas["op"]
    assert corte.cifras["totales"]["total_cobrado"] == 75000 and len(corte.cifras["secciones"][0]["filas"]) == 2
    assert corte.cifras["totales"]["contado"] == 10000000 and corte.cifras["totales"]["diferencia"] == 10000000 - 75000
    assert Entrega.objects.filter(corte=corte).count() == 1
    corte.cifras = {}
    with pytest.raises(CorteCerrado):
        corte.save()
    assert Corte.objects.filter(pk=corte.pk).update(cifras={}) == 0
    turno_de(personas["op2"])
    cerrar_caja(personas["op2"])
    assert Corte.objects.filter(tipo=DIARIO).count() == 1
    url = reverse("cortes:detalle", args=[corte.pk])
    assert cliente(personas["op"]).get(url).status_code == 200
    assert cliente(personas["op2"]).get(url).status_code == 403
    assert cliente(personas["op2"]).get(reverse("cortes:descargar", args=[corte.pk, "pdf"])).status_code == 403
    assert cliente(personas["sup"]).get(url).status_code == 200
    lista_op2 = cliente(personas["op2"]).get(reverse("cortes:lista")).content.decode()
    assert url not in lista_op2 and url in cliente(personas["op"]).get(reverse("cortes:lista")).content.decode()
    assert Evento.objects.filter(accion="acceso_denegado").exists()
    pdf = cliente(personas["op"]).get(reverse("cortes:descargar", args=[corte.pk, "pdf"]))
    assert pdf["Content-Type"] == "application/pdf" and ana.matricula in PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()


def test_corte_diario_tardio_y_alerta(personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    cobrar(personas["op"], ana, 10000)
    Parametro.objects.update_or_create(clave="hora_limite_corte_diario", defaults={"valor": "00:00"})
    pendientes = cortes.diarios_pendientes()
    assert [p["persona"] for p in pendientes] == [personas["op"]]
    inicio = cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    assert "Corte diario pendiente" in inicio and "Persona operacion" in inicio
    assert "Corte diario pendiente" not in cliente(personas["op2"]).get(reverse("inicio")).content.decode()
    Parametro.objects.update_or_create(clave="hora_limite_corte_diario", defaults={"valor": "23:59"})
    turno = caja.turno_abierto(personas["op"])
    Turno.objects.filter(pk=turno.pk).update(abierto_en=timezone.now() - timedelta(days=1))
    assert cortes.diarios_pendientes()[0]["dia_anterior"]
    cerrar_caja(personas["op"])
    corte = Corte.objects.get(tipo=DIARIO)
    assert corte.tardio and corte.fecha == (timezone.localtime(timezone.now() - timedelta(days=1))).date()
    assert cortes.diarios_pendientes() == []


def test_flujo_completo_de_un_mes(personas, tmp_path, django_capture_on_commit_callbacks):
    inicio, fin = mes_anterior()
    preparar_conceptos()
    Negocio.objects.filter(pk=1).update(cobro_desde=inicio)
    cuenta_principal()
    carpeta = destino(tmp_path)
    colegiatura = ConceptoCobro.objects.get(nombre="Colegiatura")
    familia = Familia.objects.create(nombre="Familia Flujo")
    ana = titular_activo(personas["op"], personas["sup"], "Ana", familia=familia)
    beto = titular_activo(personas["op"], personas["sup"], "Beto")
    beca = Beca.objects.create(titular=ana, concepto=colegiatura, puntos_base=5000, vigente_desde=inicio, motivo="beca de prueba", creada_por=personas["sup"])
    libro.crear_cargo(ana, colegiatura, 250000, inicio + timedelta(days=9), Cargo.AUTOMATICO, periodo=f"{inicio:%Y-%m}", beca=beca, descuento=125000)
    libro.crear_cargo(beto, colegiatura, 250000, inicio + timedelta(days=9), Cargo.AUTOMATICO, periodo=f"{inicio:%Y-%m}")
    efectivo = cobrar(personas["op"], ana, 50000, fecha=timezone.now() - timedelta(days=(hoy_negocio() - inicio).days - 5))
    with django_capture_on_commit_callbacks(execute=True):
        cerrar_caja(personas["op"])
    lineas = estado([spei(12, 80000, referencia=beto.matricula), spei(14, 30000, referencia=ana.matricula)], mes=inicio.month, anio=inicio.year)
    cuenta, movimientos, resumen = conciliacion.movimientos_de_pdf(lineas)
    conciliacion.importar(cuenta, movimientos, Importacion.ESTADO_PDF, "estado.pdf", "0" * 64, personas["sup"], resumen)
    banco_ana = Pago.objects.get(titular=ana, medio=Pago.BANCO)
    assert banco_ana.fecha.date() == inicio.replace(day=14) and banco_ana.fecha_banco is None
    libro.revertir_pago(banco_ana, "pago de otra cuenta", personas["dir"])
    corte_diario = Corte.objects.get(tipo=DIARIO)
    with django_capture_on_commit_callbacks(execute=True):
        assert cortes.ejecutar_entregas() == (1, 0)
    assert (Path(carpeta.ruta) / f"{salida.nombre_base(corte_diario)}.pdf").exists()
    with django_capture_on_commit_callbacks(execute=True):
        creados = cortes.generar_mayores()
    assert [c.fecha for c in creados] == [inicio] and creados[0].estado == Corte.BORRADOR
    assert cortes.generar_mayores() == []
    mayor = Corte.objects.get(tipo=MAYOR)
    cifras = mayor.cifras
    por_medio = {f["medio"]: f["importe"] for f in cifras["secciones"][0]["filas"]}
    assert por_medio == {"Efectivo": 50000, "Banco": 80000}
    fila = next(f for f in cifras["secciones"][1]["filas"] if f["concepto"] == "Colegiatura")
    assert fila["esperado"] == 125000 + 250000 and fila["cobrado_de_lo_esperado"] == 50000 + 80000
    estados = {f["titular"]["matricula"]: f["Colegiatura"] for f in cifras["secciones"][2]["filas"]}
    assert estados == {ana.matricula: "parcial", beto.matricula: "parcial"}
    assert any("Colegiatura 50%" in b for f in cifras["secciones"][2]["filas"] for b in f["becas"])
    reversos = next(s for s in cifras["secciones"] if s["clave"] == "reversos")["filas"]
    assert reversos == []
    assert cifras["totales"]["efectivo_cuadra"] is True and cifras["totales"]["banco"]["estado_oficial_importado"] is True
    assert cliente(personas["op"]).post(reverse("cortes:cerrar", args=[mayor.pk])).status_code == 403
    assert cliente(personas["op"]).get(reverse("cortes:detalle", args=[mayor.pk])).status_code == 403
    with django_capture_on_commit_callbacks(execute=True):
        respuesta = cliente(personas["sup"]).post(reverse("cortes:cerrar", args=[mayor.pk]))
    assert respuesta.status_code == 302
    mayor.refresh_from_db()
    assert mayor.cerrado and mayor.cerrado_por == personas["sup"] and mayor.hash == salida.huella(mayor.cifras)
    assert Negocio.objects.get().periodo_cerrado_hasta == fin
    foto = dict(mayor.cifras)
    with django_capture_on_commit_callbacks(execute=True):
        assert cortes.ejecutar_entregas() == (1, 0)
    assert entrega.verificar(carpeta.ruta) == []
    call_command("verificar_entrega", carpeta.ruta)
    manifiesto = json.loads((Path(carpeta.ruta) / "manifiesto.json").read_text())
    nombres = {a["nombre"] for a in manifiesto["archivos"]}
    assert f"corte-mensual-{inicio:%Y-%m}.pdf" in nombres and manifiesto["ancla"]["numero"] > 0
    tardio = estado([spei(20, 40000, referencia=beto.matricula, rastreo="TARDE1")], mes=inicio.month, anio=inicio.year)
    cuenta, movimientos, resumen = conciliacion.movimientos_de_pdf(tardio)
    with pytest.raises(conciliacion.ErrorConciliacion):
        conciliacion.importar(cuenta, movimientos, Importacion.ESTADO_PDF, "estado.pdf", "0" * 64, personas["sup"], resumen)
    datos = [{**movimientos[0], "huella": "tardio-1"}]
    conciliacion.importar(cuenta, datos, Importacion.ARCHIVO, "tardio.csv", "0" * 64, personas["sup"])
    pago_tardio = Pago.objects.get(titular=beto, medio=Pago.BANCO, importe=40000)
    assert pago_tardio.fecha.date() == timezone.now().date() and pago_tardio.fecha_banco == inicio.replace(day=20)
    nuevo_efectivo = cobrar(personas["op"], beto, 1000, fecha=timezone.now() - timedelta(days=(hoy_negocio() - inicio).days - 3))
    assert nuevo_efectivo.fecha.date() == timezone.now().date() and nuevo_efectivo.fecha_banco is not None
    with pytest.raises(PeriodoCerrado):
        Pago.objects.create(titular=beto, importe=100, medio=Pago.BANCO, registrado_por=personas["sup"], fecha=timezone.now() - timedelta(days=(hoy_negocio() - inicio).days - 2))
    mayor.refresh_from_db()
    assert mayor.cifras == foto
    cliente(personas["sup"]).get(reverse("cortes:detalle", args=[mayor.pk]))
    mayor.refresh_from_db()
    assert mayor.cifras == foto
    (Path(carpeta.ruta) / f"corte-mensual-{inicio:%Y-%m}.csv").write_text("alterado")
    assert any("no coincide" in p for p in entrega.verificar(carpeta.ruta))
    with pytest.raises(CommandError):
        call_command("verificar_entrega", carpeta.ruta)
    verificar_sumas()


def test_no_se_cierra_un_mes_si_el_anterior_sigue_en_borrador_ni_uno_sin_terminar(personas):
    from datetime import date

    Negocio.objects.filter(pk=1).update(cobro_desde=date(2026, 1, 1))
    cortes.generar_mayores(date(2026, 3, 10))
    enero, febrero = Corte.objects.filter(tipo=MAYOR).order_by("fecha")
    with pytest.raises(cortes.ErrorCorte, match="anterior"):
        cortes.cerrar_mayor(febrero, personas["sup"], hoy=date(2026, 3, 10))
    abierto = Corte.objects.create(tipo=MAYOR, fecha=hoy_negocio().replace(day=1), periodo_inicio=hoy_negocio().replace(day=1), periodo_fin=hoy_negocio() + timedelta(days=40), cifras={})
    with pytest.raises(cortes.ErrorCorte, match="no termina"):
        cortes.cerrar_mayor(abierto, personas["sup"])
    cortes.cerrar_mayor(enero, personas["sup"], hoy=date(2026, 3, 10))
    cortes.cerrar_mayor(febrero, personas["sup"], hoy=date(2026, 3, 10))
    assert Negocio.objects.get().periodo_cerrado_hasta == date(2026, 2, 28)


def test_trabajador_se_pone_al_dia_con_los_cortes_tras_meses_apagado(personas, django_capture_on_commit_callbacks):
    from datetime import date

    preparar_conceptos()
    titular_activo(personas["op"], personas["sup"], "Ana")
    with django_capture_on_commit_callbacks(execute=True):
        informe = dict((n, t) for n, _, t in ejecutar_ciclo(date(2026, 6, 10)))
    assert informe["generar_cortes_mayores"] == "5 cortes mayores generados"
    assert informe["cerrar_cortes_vencidos"] == "5 cortes mayores cerrados sin revisar"
    mayores = list(Corte.objects.filter(tipo=MAYOR).order_by("fecha"))
    assert [c.fecha.month for c in mayores] == [1, 2, 3, 4, 5] and all(c.sin_revisar and c.cerrado for c in mayores)
    assert Negocio.objects.get().periodo_cerrado_hasta == date(2026, 5, 31)
    ejecutar_ciclo(date(2026, 6, 10))
    assert Corte.objects.filter(tipo=MAYOR).count() == 5
    ejecutar_ciclo(date(2026, 7, 2))
    junio = Corte.objects.get(tipo=MAYOR, fecha=date(2026, 6, 1))
    assert junio.estado == Corte.BORRADOR and not junio.sin_revisar


def test_lista_de_cobranza_programada_y_a_demanda(personas):
    from datetime import date

    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    libro.crear_cargo(ana, ConceptoCobro.objects.get(nombre="Colegiatura"), 250000, date(2026, 1, 10), Cargo.AUTOMATICO, periodo="2026-01")
    lunes = date(2026, 6, 8)
    assert cortes.cobranza_programada(lunes) is not None
    assert cortes.cobranza_programada(lunes) is None
    assert cortes.cobranza_programada(date(2026, 6, 9)) is None
    assert cliente(personas["op"]).post(reverse("cortes:cobranza")).status_code == 403
    respuesta = cliente(personas["sup"]).post(reverse("cortes:cobranza"))
    corte = Corte.objects.filter(tipo=COBRANZA).order_by("-id").first()
    assert respuesta.url == reverse("cortes:detalle", args=[corte.pk])
    filas = corte.cifras["secciones"][0]["filas"]
    assert any(f["titular"]["matricula"] == ana.matricula and f["dias_atraso"] > 0 for f in filas)


def preparar_cobranza(personas):
    from datetime import date

    preparar_conceptos()
    cuenta_principal()
    telefono = CampoContacto.objects.filter(tipo=CampoContacto.TELEFONO).first()
    correo = CampoContacto.objects.filter(tipo=CampoContacto.CORREO).first() or CampoContacto.objects.create(etiqueta="Correo", tipo=CampoContacto.CORREO)
    familia = Familia.objects.create(nombre="Zavaleta Quintero")
    titular = crear_titular(
        personas["dir"],
        {"nombre": "Xochitl", "apellidos": "Zavaleta Quintero", "familia": familia},
        contacto={"nombre": "Wenceslao Yáñez", "valores": {str(telefono.pk): "525598761234", str(correo.pk): "wenceslao.prueba@example.com"}},
    )
    Titular.objects.filter(pk=titular.pk).update(estado=Titular.ACTIVO, activo_desde=date(2026, 1, 1))
    Contacto.objects.filter(familia=familia).update(principal=True)
    titular.refresh_from_db()
    peligroso = crear_titular(personas["dir"], {"nombre": "=HYPERLINK(1)", "apellidos": "Ñandú Prueba"}, contacto={"nombre": "Otra Persona", "valores": {}})
    Titular.objects.filter(pk=peligroso.pk).update(estado=Titular.ACTIVO)
    concepto = ConceptoCobro.objects.get(nombre="Colegiatura")
    libro.crear_cargo(titular, concepto, 250000, date(2026, 1, 10), Cargo.AUTOMATICO, periodo="2026-01")
    libro.crear_cargo(peligroso, concepto, 250000, date(2026, 1, 10), Cargo.AUTOMATICO, periodo="2026-01")
    return titular


def textos_entregados(carpeta):
    textos = {}
    for archivo in Path(carpeta).iterdir():
        crudo = archivo.read_bytes()
        texto = crudo.decode("utf-8", "ignore")
        if archivo.suffix == ".pdf":
            texto += "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(crudo)).pages)
        textos[archivo.name] = texto
    return textos


def test_niveles_de_detalle_sin_fugas_en_ningun_archivo(personas, tmp_path, django_capture_on_commit_callbacks):
    titular = preparar_cobranza(personas)
    carpetas = {nivel: destino(tmp_path, nivel, {COBRANZA: nivel, MAYOR: nivel}) for nivel in ("completo", "solo_nombres", "sin_nombres")}
    with django_capture_on_commit_callbacks(execute=True):
        cortes.generar_cobranza(usuario=personas["sup"])
        assert cortes.ejecutar_entregas() == (3, 0)
    matriculas = [titular.matricula, f"{titular.matricula[:3]} {titular.matricula[3:]}"]
    telefonos = ["5598761234", "55 9876 1234", "525598761234"]
    correo = "wenceslao.prueba@example.com"
    contacto = "Wenceslao"
    nombres = ["Xochitl", "Zavaleta"]
    completo = textos_entregados(carpetas["completo"].ruta)
    todo = "\n".join(completo.values())
    for buscado in [titular.matricula, "55 9876 1234", correo, contacto, "Xochitl"]:
        assert buscado in todo, buscado
    for nombre, texto in textos_entregados(carpetas["solo_nombres"].ruta).items():
        for prohibido in matriculas + telefonos + [correo, contacto]:
            assert prohibido not in texto, (nombre, prohibido)
    assert "Xochitl" in "".join(textos_entregados(carpetas["solo_nombres"].ruta).values())
    sin_nombres = textos_entregados(carpetas["sin_nombres"].ruta)
    for nombre, texto in sin_nombres.items():
        for prohibido in nombres + telefonos + [correo, contacto]:
            assert prohibido not in texto, (nombre, prohibido)
    assert titular.matricula in "".join(sin_nombres.values())
    assert all(entrega.verificar(c.ruta) == [] for c in carpetas.values())
    csv_completo = next(t for n, t in completo.items() if n.endswith(".csv"))
    assert "'=HYPERLINK(1)" in csv_completo and "\n=HYPERLINK" not in csv_completo and ",=HYPERLINK" not in csv_completo
    encabezado = json.loads(next(t for n, t in completo.items() if n.endswith(".json") and n.startswith("cobranza")))["encabezado"]
    assert encabezado["clabe"].replace(" ", "") == cuenta_principal().clabe and encabezado["donde_va_la_matricula"]


def test_rutas_de_destino_invalidas(personas, tmp_path, settings):
    c = cliente(personas["dir"])
    for ruta in ("relativa/cortes", str(Path(settings.RAIZ) / "cortes"), str(Path(settings.RAIZ) / "instancia" / "x"), str(Path(settings.RAIZ).parent)):
        respuesta = c.post(reverse("cortes:destino_nuevo"), {"nombre": "x", "ruta": ruta, "activo": "on"})
        assert respuesta.status_code == 200, ruta
    archivo = tmp_path / "soy-archivo"
    archivo.write_text("x")
    assert c.post(reverse("cortes:destino_nuevo"), {"nombre": "x", "ruta": str(archivo), "activo": "on"}).status_code == 200
    assert not Destino.objects.exists()
    nueva = tmp_path / "nueva" / "carpeta"
    datos = {"nombre": "Nube", "ruta": str(nueva), "activo": "on", "entregar_mayor": "on", "nivel_mayor": "sin_nombres", "nivel_diario": "solo_nombres", "nivel_cobranza": "completo"}
    assert c.post(reverse("cortes:destino_nuevo"), datos).status_code == 302
    guardado = Destino.objects.get()
    assert nueva.is_dir() and guardado.ruta == str(nueva.resolve())
    assert dict(guardado.reglas.values_list("tipo", "entregar")) == {"diario": False, "mayor": True, "cobranza": False}
    assert cliente(personas["sup"]).get(reverse("cortes:destinos")).status_code == 403


def test_entrega_fallida_se_reintenta_y_alerta(personas, tmp_path, django_capture_on_commit_callbacks):
    preparar_cobranza(personas)
    objeto = destino(tmp_path)
    Path(objeto.ruta).rmdir()
    Path(objeto.ruta).write_text("ya no es carpeta")
    with django_capture_on_commit_callbacks(execute=True):
        corte = cortes.generar_cobranza(usuario=personas["sup"])
        assert cortes.ejecutar_entregas() == (0, 1)
    assert corte.cerrado
    pendiente = Entrega.objects.get()
    assert pendiente.estado == Entrega.PENDIENTE and pendiente.intentos == 1 and pendiente.ultimo_error and pendiente.proximo_intento > timezone.now()
    assert cortes.ejecutar_entregas() == (0, 0)
    assert "entrega de cortes con problemas" in cliente(personas["dir"]).get(reverse("inicio")).content.decode()
    Path(objeto.ruta).unlink()
    Entrega.objects.filter(pk=pendiente.pk).update(proximo_intento=timezone.now() - timedelta(minutes=1))
    with django_capture_on_commit_callbacks(execute=True):
        assert cortes.ejecutar_entregas() == (1, 0)
    assert Entrega.objects.get().estado == Entrega.ENTREGADA


@pytest.mark.django_db(transaction=True)
def test_cierres_simultaneos_trabajadores_y_entregas_dobles(tmp_path):
    from datetime import date

    from .conftest import configurar, nuevo_usuario

    roles = configurar("escuela")
    supervision = nuevo_usuario("supervision", roles["Supervisión"])
    Negocio.objects.filter(pk=1).update(cobro_desde=date(2026, 1, 1))
    objeto = destino(tmp_path)
    cortes.generar_mayores(date(2026, 2, 3))
    enero = Corte.objects.get(tipo=MAYOR)
    resultados = []

    def cerrar():
        try:
            cortes.cerrar_mayor(Corte.objects.get(pk=enero.pk), supervision, hoy=date(2026, 2, 3))
            resultados.append("ok")
        except cortes.ErrorCorte:
            resultados.append("ya")
        finally:
            connection.close()

    hilos = [threading.Thread(target=cerrar) for _ in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(resultados) == ["ok", "ya", "ya"] and Entrega.objects.count() == 1

    def ciclo():
        try:
            ejecutar_ciclo(date(2026, 4, 6))
        finally:
            connection.close()

    hilos = [threading.Thread(target=ciclo) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert Corte.objects.filter(tipo=MAYOR).count() == 3
    assert Corte.objects.filter(tipo=COBRANZA, automatico=True, fecha=date(2026, 4, 6)).count() == 1
    assert Entrega.objects.filter(corte__tipo=MAYOR).count() == Corte.objects.filter(tipo=MAYOR, estado=Corte.CERRADO).count()

    def entregar():
        try:
            cortes.ejecutar_entregas()
        finally:
            connection.close()

    hilos = [threading.Thread(target=entregar) for _ in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert all(e.estado == Entrega.ENTREGADA and e.intentos == 1 for e in Entrega.objects.all())
    manifiesto = json.loads((Path(objeto.ruta) / "manifiesto.json").read_text())
    nombres = [a["nombre"] for a in manifiesto["archivos"]]
    assert len(nombres) == len(set(nombres)) == 3 * Entrega.objects.count()
    assert entrega.verificar(objeto.ruta) == []


def test_nada_que_escriba_un_usuario_llega_a_un_nombre_de_archivo(personas):
    from caja.models import Caja

    corte = Corte(tipo=DIARIO, fecha=hoy_negocio(), numero=2, caja=Caja(nombre="../../etc/Caja Ñ 1 <x>"))
    assert re.fullmatch(r"corte-diario-\d{4}-\d{2}-\d{2}-[a-z0-9-]+-2", salida.nombre_base(corte))
    assert "/" not in salida.nombre_base(corte) and ".." not in salida.nombre_base(corte)


def test_periodo_cerrado_no_se_salta_por_ninguna_via(personas):
    from cobros.models import CancelacionCargo, ReversionPago
    from titulares import padron

    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    pago = cobrar(personas["op"], ana, 20000)
    cargo = Cargo.objects.filter(titular=ana).first()
    Negocio.objects.filter(pk=1).update(periodo_cerrado_hasta=hoy_negocio())
    antes = (Pago.objects.count(), ReversionPago.objects.count(), CancelacionCargo.objects.count(), Cargo.objects.count())
    with pytest.raises(PeriodoCerrado):
        cobrar(personas["op"], ana, 1000)
    with pytest.raises(PeriodoCerrado):
        libro.revertir_pago(pago, "error", personas["dir"], turno=caja.turno_abierto(personas["op"]))
    with pytest.raises(PeriodoCerrado):
        libro.cancelar_cargo(cargo, 100, CancelacionCargo.CANCELACION, "x", personas["dir"])
    with pytest.raises(PeriodoCerrado):
        libro.crear_cargo(ana, cargo.concepto, 100, hoy_negocio(), Cargo.MANUAL)
    analisis = {"filas": [{"numero": 2, "nombre": "Pía", "apellidos": "Prueba Pago", "agrupacion": "", "responsable": "", "telefono": "5512341234", "correo": "", "saldos": [[cargo.concepto_id, -500]], "errores": [], "duplicado": "", "familia": None}], "familias": []}
    with pytest.raises(PeriodoCerrado):
        padron.aplicar(analisis, [], personas["dir"], "p.csv", "0" * 64)
    respuesta = cliente(personas["op"]).post(reverse("cobros:cobrar", args=[ana.pk]), {"importe": "10"})
    assert respuesta.status_code in (200, 302)
    assert (Pago.objects.count(), ReversionPago.objects.count(), CancelacionCargo.objects.count(), Cargo.objects.count()) == antes


def test_corte_mayor_del_mes_en_curso_lista_reversos_con_quien_los_hizo(personas):
    preparar_conceptos()
    cuenta_principal()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    pago = libro.registrar_pago(ana, 30000, Pago.BANCO, personas["sup"])
    libro.revertir_pago(pago, "abono de otra persona", personas["sup2"], autorizador=personas["dir"])
    hoy = hoy_negocio()
    from cortes import calculo

    reversos = next(s for s in calculo.cifras_mayor(hoy.replace(day=1), hoy)["secciones"] if s["clave"] == "reversos")["filas"]
    assert reversos[0]["importe"] == 30000 and reversos[0]["ejecuto"] == personas["sup2"].nombre and reversos[0]["autorizo"] == personas["dir"].nombre


@pytest.mark.django_db
def test_paso_del_asistente_de_cortes_y_respaldo(tmp_path, settings):
    from django.test import Client

    from nucleo import sobre

    from .test_asistente import paso_inicio

    c = Client()
    c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE))
    pagina = c.get(reverse("asistente:cortes"))
    texto = sobre.clave_a_texto(bytes(settings.CLAVE_RESPALDO))
    assert texto in pagina.content.decode() and pagina["Cache-Control"] == "no-store"
    datos = {"carpeta_entrega": "relativa", "hora_limite_corte_diario": "19:30", "carpeta_respaldo": "", "nivel_diario": "solo_nombres", "nivel_mayor": "sin_nombres", "nivel_cobranza": "completo"}
    assert c.post(reverse("asistente:cortes"), datos).status_code == 200
    datos.update({"carpeta_entrega": str(tmp_path / "cortes"), "carpeta_respaldo": str(tmp_path / "respaldos")})
    assert c.post(reverse("asistente:cortes"), datos).status_code == 200
    datos["guardada"] = "on"
    assert c.post(reverse("asistente:cortes"), datos).url == reverse("asistente:usuario")
    negocio = Negocio.objects.get()
    assert negocio.carpeta_respaldo == str((tmp_path / "respaldos").resolve()) and not negocio.clave_recuperacion_pendiente
    destino_creado = Destino.objects.get()
    assert dict(destino_creado.reglas.values_list("tipo", "nivel")) == {"diario": "solo_nombres", "mayor": "sin_nombres", "cobranza": "completo"}
    assert Parametro.objects.get(clave="hora_limite_corte_diario").valor == "19:30"
    assert texto not in c.get(reverse("asistente:cortes")).content.decode()
