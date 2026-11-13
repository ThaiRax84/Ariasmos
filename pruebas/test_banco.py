import threading
from datetime import date

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.urls import reverse

from auditoria.models import Evento
from banco import conciliacion, lectura
from banco.models import Banco, CargaTemporal, CuentaBancaria, Importacion, MovimientoBancario, ReglaPagador
from caja import servicios as caja
from caja.models import Traslado
from cobros import libro
from cobros.models import Cargo, Pago
from configuracion.models import Parametro
from titulares.models import Titular

from .banco_ayudas import CLABE, cuenta_principal, efectivo, enlace, estado, pdf, retiro, saldo_final, spei
from .conftest import cliente
from .libro_ayudas import familia_con_dos, preparar_conceptos, titular_activo, turno_de, verificar_sumas

PAGADOR = "032180000118359719"


@pytest.fixture
def base(personas):
    cache.clear()
    preparar_conceptos()
    cuenta_principal()
    return personas, titular_activo(personas["op"], personas["sup"], "Ana")


def subir(usuario, contenido, nombre="estado.pdf", cuenta=None):
    datos = {"archivo": SimpleUploadedFile(nombre, contenido)}
    if cuenta is not None:
        datos["cuenta"] = cuenta.pk
    c = cliente(usuario)
    return c, c.post(reverse("conciliacion:importar"), datos)


def importar_pdf(usuario, movimientos, **opciones):
    c, r = subir(usuario, pdf(estado(movimientos, **opciones)))
    assert r.status_code == 302, r.content.decode()[-1500:]
    previa = c.get(r.url)
    assert previa.status_code == 200
    final = c.post(r.url)
    assert final.status_code == 302
    return Importacion.objects.order_by("-id").first()


def importar_texto(usuario, movimientos, **opciones):
    cuenta, datos, resumen = conciliacion.movimientos_de_pdf(estado(movimientos, **opciones))
    return conciliacion.importar(cuenta, datos, Importacion.ESTADO_PDF, "estado.pdf", "0" * 64, usuario, resumen)


def mov(**filtro):
    return MovimientoBancario.objects.get(**filtro)


def parametro(clave, valor):
    Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})


def test_estado_sintetico_en_texto_y_en_pdf_real(base):
    personas, ana = base
    movimientos = [spei(3, 100000, referencia=ana.matricula), retiro(4, 5000), enlace(5, 1234, "sin datos")]
    importacion = importar_texto(personas["sup"], movimientos)
    assert (importacion.movimientos, importacion.nuevos, importacion.aplicados, importacion.sin_pista) == (3, 3, 1, 1)
    assert importacion.saldo_final == 100000 + 100000 - 5000 + 1234
    otra = importar_pdf(personas["sup"], movimientos)
    assert (otra.nuevos, otra.duplicados) == (0, 3)
    assert MovimientoBancario.objects.count() == 3
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 1
    verificar_sumas()


def test_reimportar_no_duplica_y_otro_periodo_solo_agrega_lo_nuevo(base):
    personas, ana = base
    agosto = [spei(3, 100000, referencia=ana.matricula)]
    importar_pdf(personas["sup"], agosto)
    importar_pdf(personas["sup"], agosto)
    importar_pdf(personas["sup"], [spei(9, 2000, concepto="otro pago")], mes=9, saldo_inicial=saldo_final(agosto))
    assert MovimientoBancario.objects.count() == 2
    assert Pago.objects.filter(titular=ana, medio=Pago.BANCO).count() == 1


def test_movimientos_identicos_en_el_mismo_estado_se_conservan(base):
    personas, _ = base
    importar_texto(personas["sup"], [enlace(5, 1000, "cuota"), enlace(5, 1000, "cuota")])
    assert MovimientoBancario.objects.count() == 2


def test_estado_de_otra_cuenta_se_rechaza(base):
    personas, _ = base
    _, r = subir(personas["sup"], pdf(estado([enlace(5, 1000, "x")], clabe="002010077777777784")))
    assert r.status_code == 200 and "no es de una cuenta bancaria registrada" in r.content.decode()
    assert not MovimientoBancario.objects.exists() and not CargaTemporal.objects.exists()


def test_estado_alterado_se_rechaza_sin_escribir(base):
    personas, ana = base
    _, r = subir(personas["sup"], pdf(estado([spei(3, 100000, referencia=ana.matricula), enlace(5, 1000, "x")], alterar=0)))
    assert r.status_code == 200
    assert not MovimientoBancario.objects.exists() and not Importacion.objects.exists() and not Pago.objects.filter(medio=Pago.BANCO).exists()


def test_automatica_por_referencia_y_por_concepto_con_recibo_y_fecha_del_banco(base):
    personas, ana = base
    beto = titular_activo(personas["op"], personas["sup"], "Beto")
    importar_texto(personas["sup"], [spei(3, 30000, referencia=ana.matricula), spei(4, 20000, concepto=f"colegiatura {beto.matricula}")])
    pago_ana = Pago.objects.get(titular=ana)
    pago_beto = Pago.objects.get(titular=beto)
    assert pago_ana.medio == Pago.BANCO and pago_ana.turno_id is None and pago_ana.recibo.serie == "B"
    assert pago_ana.fecha.date() == date(2026, 8, 3) and pago_beto.importe == 20000
    assert mov(pago=pago_ana).estado == MovimientoBancario.APLICADO
    assert Evento.objects.filter(accion="importacion_bancaria").exists()
    verificar_sumas()


def test_incrustada_solo_se_sugiere(base):
    personas, ana = base
    importar_texto(personas["sup"], [spei(3, 30000, concepto=f"pago 55{ana.matricula}0018")])
    m = mov()
    assert m.estado == MovimientoBancario.POR_IDENTIFICAR and m.sugerencia == ana.matricula
    assert not Pago.objects.filter(medio=Pago.BANCO).exists()


def test_un_digito_mal_se_sugiere(base):
    personas, ana = base
    mala = ana.matricula[:3] + str((int(ana.matricula[3]) + 1) % 10) + ana.matricula[4:]
    importar_texto(personas["sup"], [spei(3, 100000, referencia=mala)])
    m = mov()
    assert m.estado == MovimientoBancario.POR_IDENTIFICAR and m.sugerencia == ana.matricula and m.coincide_importe


def test_pagador_conocido_se_sugiere_y_con_dos_parametros_se_aplica_solo(base):
    personas, ana = base
    ReglaPagador.objects.create(cuenta_pagador=PAGADOR, titular=ana, confirmaciones=2)
    importar_texto(personas["sup"], [spei(3, 40000, concepto="pago mensual", cuenta=PAGADOR)])
    assert mov().estado == MovimientoBancario.POR_IDENTIFICAR and mov().sugerencia == ana.matricula
    parametro("aplicar_solo_por_pagador", 1)
    importar_texto(personas["sup"], [spei(4, 100000, concepto="pago mensual", cuenta=PAGADOR, rastreo="X2")], mes=10)
    assert Pago.objects.filter(titular=ana, medio=Pago.BANCO, importe=100000).count() == 1
    parametro("confirmaciones_pagador_confiable", 3)
    importar_texto(personas["sup"], [spei(5, 25000, concepto="pago mensual", cuenta=PAGADOR, rastreo="X3")], mes=12)
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 1


def test_sobrante_por_banco_pasa_al_hermano(personas):
    preparar_conceptos()
    cuenta_principal()
    _, ana, beto = familia_con_dos(personas["op"], personas["sup"])
    importar_texto(personas["sup"], [spei(3, 150000, referencia=ana.matricula)])
    def debe(titular):
        return sum(c.saldo for c in libro.con_saldo(Cargo.objects.filter(titular=titular)))

    assert debe(ana) == 0 and debe(beto) == 50000
    verificar_sumas()


def test_deposito_de_caja_se_empareja_y_la_alerta_se_apaga(base):
    personas, ana = base
    op = personas["op"]
    turno = turno_de(op)
    libro.registrar_pago(ana, 100000, Pago.EFECTIVO, op, turno=turno)
    caja.cerrar_turno(turno, op, {"100000": 1})
    deposito = caja.depositar(op, 100000, cuenta_principal(), date(2026, 8, 6), "DEP-1")
    Traslado.objects.filter(pk=deposito.pk).update(creado=deposito.creado.replace(year=2025))
    assert [t.pk for t in caja.alertas()["depositos_sin_conciliar"]] == [deposito.pk]
    importar_texto(personas["sup"], [efectivo(8, 100000)])
    deposito.refresh_from_db()
    assert deposito.estado == Traslado.CONCILIADO and mov().traslado_id == deposito.pk
    assert list(caja.alertas()["depositos_sin_conciliar"]) == []
    verificar_sumas()


def test_dos_depositos_iguales_los_elige_quien_concilia(base):
    personas, ana = base
    op = personas["op"]
    turno = turno_de(op)
    libro.registrar_pago(ana, 100000, Pago.EFECTIVO, op, turno=turno)
    caja.cerrar_turno(turno, op, {"100000": 1})
    uno = caja.depositar(op, 50000, cuenta_principal(), date(2026, 8, 6), "D1")
    caja.depositar(op, 50000, cuenta_principal(), date(2026, 8, 7), "D2")
    importar_texto(personas["sup"], [efectivo(8, 50000)])
    m = mov()
    assert m.estado == MovimientoBancario.POR_IDENTIFICAR
    assert cliente(personas["op"]).post(reverse("conciliacion:emparejar", args=[m.pk]), {"traslado": uno.pk}).status_code == 403
    cliente(personas["sup"]).post(reverse("conciliacion:emparejar", args=[m.pk]), {"traslado": uno.pk})
    m.refresh_from_db()
    uno.refresh_from_db()
    assert m.estado == MovimientoBancario.CONCILIADO and uno.estado == Traslado.CONCILIADO


def test_cola_operacion_propone_y_supervision_confirma_y_aprende(base):
    personas, ana = base
    importar_texto(personas["sup"], [spei(3, 30000, concepto="pago de la nena", cuenta=PAGADOR)])
    m = mov()
    op, sup = cliente(personas["op"]), cliente(personas["sup"])
    pagina = op.get(reverse("conciliacion:movimiento", args=[m.pk])).content.decode()
    assert PAGADOR not in pagina and PAGADOR[-4:] in pagina
    assert PAGADOR in sup.get(reverse("conciliacion:movimiento", args=[m.pk])).content.decode()
    op.post(reverse("conciliacion:proponer", args=[m.pk]), {"matricula": ana.matricula})
    assert op.post(reverse("conciliacion:confirmar", args=[m.pk]), {"matricula": ana.matricula}).status_code == 403
    m.refresh_from_db()
    assert m.propuesta == ana and m.estado == MovimientoBancario.POR_IDENTIFICAR and not Pago.objects.filter(medio=Pago.BANCO).exists()
    sup.post(reverse("conciliacion:confirmar", args=[m.pk]), {"matricula": ana.matricula})
    sup.post(reverse("conciliacion:confirmar", args=[m.pk]), {"matricula": ana.matricula})
    m.refresh_from_db()
    assert m.estado == MovimientoBancario.APLICADO and Pago.objects.filter(titular=ana, medio=Pago.BANCO).count() == 1
    regla = ReglaPagador.objects.get(cuenta_pagador=PAGADOR)
    assert regla.titular == ana and regla.confirmaciones == 1
    verificar_sumas()


def test_corregir_al_pagador_reinicia_la_regla(base):
    personas, ana = base
    beto = titular_activo(personas["op"], personas["sup"], "Beto")
    ReglaPagador.objects.create(cuenta_pagador=PAGADOR, titular=ana, confirmaciones=5)
    importar_texto(personas["sup"], [spei(3, 30000, concepto="pago", cuenta=PAGADOR)])
    conciliacion.confirmar(mov(), beto, personas["sup"])
    regla = ReglaPagador.objects.get()
    assert regla.titular == beto and regla.confirmaciones == 1


def test_no_es_un_cobro_pide_motivo(base):
    personas, _ = base
    importar_texto(personas["sup"], [enlace(5, 1000, "intereses")])
    m = mov()
    c = cliente(personas["sup"])
    c.post(reverse("conciliacion:no_cobro", args=[m.pk]), {"motivo": ""})
    m.refresh_from_db()
    assert m.estado == MovimientoBancario.POR_IDENTIFICAR
    c.post(reverse("conciliacion:no_cobro", args=[m.pk]), {"motivo": "Reembolso del proveedor"})
    m.refresh_from_db()
    assert m.estado == MovimientoBancario.NO_COBRO and m.nota == "Reembolso del proveedor" and m.resuelto_por == personas["sup"]


def test_revertir_pago_bancario_devuelve_el_movimiento_a_la_cola(base):
    personas, ana = base
    importar_texto(personas["sup"], [spei(3, 30000, referencia=ana.matricula)])
    pago = Pago.objects.get(medio=Pago.BANCO)
    cliente(personas["dir"]).post(reverse("cobros:revertir", args=[pago.pk]), {"motivo": "era de otra persona"})
    pago.refresh_from_db()
    assert hasattr(pago, "reversion")
    m = mov()
    assert m.estado == MovimientoBancario.POR_IDENTIFICAR and m.pago_id is None
    conciliacion.confirmar(m, ana, personas["sup"])
    assert mov().estado == MovimientoBancario.APLICADO
    verificar_sumas()


def test_movimiento_no_se_edita_ni_se_borra(base):
    personas, _ = base
    importar_texto(personas["sup"], [enlace(5, 1000, "x")])
    m = mov()
    from django.db.models import ProtectedError

    with pytest.raises(ProtectedError):
        MovimientoBancario.objects.filter(pk=m.pk).update(importe=5)
    with pytest.raises(ProtectedError):
        m.delete()
    m.importe = 7
    with pytest.raises(ProtectedError):
        m.save()


def test_archivo_xlsx_con_columnas_en_otro_orden(base):
    from openpyxl import Workbook

    personas, ana = base
    libro_xlsx = Workbook()
    hoja = libro_xlsx.active
    hoja.append(["Reporte de movimientos"])
    hoja.append(["Saldo", "Depósitos", "Retiros", "Concepto de pago", "Fecha de operación"])
    hoja.append([1300, 300, None, f"colegiatura {ana.matricula}", "03/08/2026"])
    hoja.append([1250, None, 50, "comision", "04/08/2026"])
    memoria = __import__("io").BytesIO()
    libro_xlsx.save(memoria)
    c, r = subir(personas["sup"], memoria.getvalue(), "movimientos.xlsx", cuenta_principal())
    assert r.status_code == 302 and "columnas" in r.url
    r2 = c.post(r.url, {"fecha": "4", "concepto": "3", "abono": "1", "cargo": "2", "saldo": "0"})
    assert r2.status_code == 302, r2.content.decode()[-2000:]
    c.post(r2.url)
    assert Pago.objects.get(medio=Pago.BANCO).titular == ana
    assert MovimientoBancario.objects.filter(estado=MovimientoBancario.INFORMATIVO).count() == 1
    carga = CargaTemporal.objects.count()
    assert carga == 0
    c2, r3 = subir(personas["sup"], memoria.getvalue(), "movimientos.xlsx", cuenta_principal())
    assert c2.get(r3.url).context["formulario"]["fecha"].initial == "4"


def test_archivo_csv_con_otros_nombres_e_importe_con_signo(base):
    personas, ana = base
    texto = f"Día;Detalle;Ref;Monto\n03/08/2026;SPEI recibido;{ana.matricula};$1,000.00\n04/08/2026;Comisión;;-10.00\n".encode("latin-1")
    c, r = subir(personas["sup"], texto, "movs.csv", cuenta_principal())
    pagina = c.get(r.url)
    propuesta = pagina.context["formulario"]
    assert propuesta["fecha"].initial == "0" and propuesta["importe"].initial == "3" and propuesta["referencia"].initial == "2"
    c.post(r.url, {"fecha": "0", "descripcion": "1", "referencia": "2", "importe": "3"})
    c.post(reverse("conciliacion:previa", args=[r.url.split("/")[-3]]))
    assert Pago.objects.get(medio=Pago.BANCO).importe == 100000


def test_archivo_que_no_cuadra_se_rechaza(base):
    personas, _ = base
    texto = b"fecha,abono,cargo,saldo\n03/08/2026,100,,1100\n04/08/2026,,50,999\n"
    c, r = subir(personas["sup"], texto, "movs.csv", cuenta_principal())
    r2 = c.post(r.url, {"fecha": "0", "abono": "1", "cargo": "2", "saldo": "3"})
    assert r2.status_code == 200 and "no cuadran" in r2.content.decode()
    assert not MovimientoBancario.objects.exists()


def test_archivo_sin_cuenta_registrada_se_rechaza(base):
    personas, _ = base
    _, r = subir(personas["sup"], b"fecha,importe\n03/08/2026,100\n", "movs.csv")
    assert r.status_code == 200 and "Elige la cuenta" in r.content.decode()


def bomba_zip():
    import io
    import zipfile

    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as archivo:
        archivo.writestr("[Content_Types].xml", "<x/>")
        archivo.writestr("xl/worksheets/sheet1.xml", b"0" * (60 * 1024 * 1024))
    return memoria.getvalue()


def xlsx_con_dimension_falsa():
    import io
    import zipfile

    from openpyxl import Workbook

    libro_xlsx = Workbook()
    libro_xlsx.active.append(["fecha", "importe"])
    memoria = io.BytesIO()
    libro_xlsx.save(memoria)
    entrada = zipfile.ZipFile(io.BytesIO(memoria.getvalue()))
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as nuevo:
        for nombre in entrada.namelist():
            datos = entrada.read(nombre)
            if nombre == "xl/worksheets/sheet1.xml":
                datos = datos.replace(b'<dimension ref="A1:B1"/>', b'<dimension ref="A1:B1000000"/>')
                assert b"B1000000" in datos
            nuevo.writestr(nombre, datos)
    return salida.getvalue()


def test_archivos_hostiles_se_rechazan(base):
    personas, _ = base
    with pytest.raises(lectura.ErrorLectura, match="descomprimido"):
        lectura.filas_de_xlsx(bomba_zip())
    with pytest.raises(lectura.ErrorLectura, match="filas"):
        lectura.filas_de_xlsx(xlsx_con_dimension_falsa())
    with pytest.raises(lectura.ErrorLectura, match="cifrado"):
        lectura.lineas_de_pdf(pdf(estado([enlace(5, 1000, "x")]), cifrado=True))
    with pytest.raises(lectura.ErrorLectura, match="no es un PDF"):
        lectura.lineas_de_pdf(b"MZ\x90\x00 no soy un pdf")
    with pytest.raises(lectura.ErrorLectura):
        lectura.lineas_de_pdf(b"%PDF-1.7\n basura sin estructura")
    for contenido, nombre in ((b"MZ falso", "estado.pdf"), (pdf(estado([enlace(5, 1000, "x")]), cifrado=True), "estado.pdf"), (bomba_zip(), "m.xlsx")):
        _, r = subir(personas["sup"], contenido, nombre, cuenta_principal())
        assert r.status_code == 200 and not CargaTemporal.objects.exists()
    _, r = subir(personas["sup"], b"x" * (lectura.LIMITE_PDF + 1), "grande.pdf")
    assert r.status_code in (200, 400, 413) and not CargaTemporal.objects.exists()


def test_texto_del_banco_no_se_interpreta(base):
    personas, _ = base
    importar_texto(personas["sup"], [spei(3, 1000, concepto="<script>alert(1)</script>", nombre="<B>X</B>")])
    m = mov()
    for c in (cliente(personas["sup"]), cliente(personas["op"])):
        cola = c.get(reverse("conciliacion:cola")).content.decode()
        detalle = c.get(reverse("conciliacion:movimiento", args=[m.pk])).content.decode()
        for pagina in (cola, detalle):
            assert "<script>alert" not in pagina and "&lt;script&gt;" in pagina


def test_csv_con_formulas_no_se_evalua_y_se_neutraliza_al_exportar(base):
    from nucleo.exportar import neutralizar

    filas = lectura.filas_de_csv(b'fecha,concepto,importe\n03/08/2026,"=HYPERLINK(""http://x"")",100\n')
    assert filas[1][1].startswith("=")
    for peligroso in ("=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"):
        assert neutralizar(peligroso).startswith("'")
    assert neutralizar("Ana") == "Ana"


@pytest.mark.django_db(transaction=True)
def test_importaciones_simultaneas_y_doble_confirmacion_no_duplican(personas):
    preparar_conceptos()
    cuenta_principal()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    lineas = estado([spei(3, 30000, referencia=ana.matricula), enlace(4, 1000, "x")])
    errores = []

    def trabajo():
        try:
            importar_texto(personas["sup"], [spei(3, 30000, referencia=ana.matricula), enlace(4, 1000, "x")])
        except Exception as error:
            errores.append(error)
        finally:
            connection.close()

    hilos = [threading.Thread(target=trabajo) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert lineas and MovimientoBancario.objects.count() == 2
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 1
    m = MovimientoBancario.objects.get(estado=MovimientoBancario.POR_IDENTIFICAR)
    resultados = []

    def confirmar():
        try:
            conciliacion.confirmar(MovimientoBancario.objects.get(pk=m.pk), ana, personas["sup"])
            resultados.append("ok")
        except conciliacion.ErrorConciliacion:
            resultados.append("ya")
        finally:
            connection.close()

    hilos = [threading.Thread(target=confirmar) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(resultados) == ["ok", "ya"]
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 2


def test_doble_envio_de_la_vista_previa_no_duplica(base):
    personas, ana = base
    c, r = subir(personas["sup"], pdf(estado([spei(3, 30000, referencia=ana.matricula)])))
    c.post(r.url)
    assert c.post(r.url).status_code == 404
    assert Importacion.objects.count() == 1


def test_inicio_de_quien_concilia(base):
    personas, _ = base
    assert "Todavía no se ha importado" in cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    importar_texto(personas["sup"], [enlace(5, 1000, "x")])
    pagina = cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    assert "1 movimiento por identificar" in pagina and "Última importación" in pagina
    assert "por identificar" not in cliente(personas["op"]).get(reverse("inicio")).content.decode()


def test_carga_ajena_no_se_ve(base):
    personas, _ = base
    c, r = subir(personas["sup"], pdf(estado([enlace(5, 1000, "x")])))
    assert cliente(personas["sup2"]).get(r.url).status_code == 404
    assert cliente(personas["sup2"]).post(r.url).status_code == 404
    assert not MovimientoBancario.objects.exists()


def test_cuenta_inactiva_o_titular_rechazado(base):
    personas, ana = base
    importar_texto(personas["sup"], [enlace(5, 1000, "x")])
    Titular.objects.filter(pk=ana.pk).update(estado=Titular.RECHAZADO)
    ana.refresh_from_db()
    with pytest.raises(conciliacion.ErrorConciliacion):
        conciliacion.confirmar(mov(), ana, personas["sup"])
    assert CuentaBancaria.objects.filter(clabe=CLABE).exists() and Banco.objects.exists()
