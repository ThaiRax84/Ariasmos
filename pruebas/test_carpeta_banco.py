import os
from pathlib import Path

import pytest
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse

from auditoria.models import Evento
from banco import carpeta, conciliacion
from banco.models import ArchivoVigilado, Importacion, MovimientoBancario
from cobros.models import Pago
from configuracion.models import Negocio
from configuracion.trabajador import ejecutar_ciclo
from proyecto import instancia

from .banco_ayudas import cuenta_principal, enlace, estado, pdf, saldo_final, spei
from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo


@pytest.fixture
def base(personas, tmp_path):
    cache.clear()
    preparar_conceptos()
    cuenta_principal()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    vigilada = tmp_path / "banco"
    Negocio.objects.filter(pk=1).update(carpeta_banco=carpeta.validar_carpeta(str(vigilada)))
    return personas, ana, vigilada


def dejar(vigilada, nombre, contenido):
    ruta = vigilada / nombre
    ruta.write_bytes(contenido)
    return ruta


def dos_revisiones():
    carpeta.revisar()
    return carpeta.revisar()


def motivo_de(vigilada, parte):
    archivos = [p for p in (vigilada / "rechazados").iterdir() if p.name.endswith(".motivo.txt") and parte in p.name]
    assert len(archivos) == 1, list((vigilada / "rechazados").iterdir())
    return archivos[0].read_text(encoding="utf-8")


def test_la_carpeta_no_puede_estar_dentro_del_programa_ni_de_los_datos(personas, tmp_path):
    for prohibida in (Path(settings.RAIZ) / "sistema", Path(settings.RAIZ), instancia.carpeta() / "banco", "relativa/banco", ""):
        with pytest.raises(carpeta.ErrorCarpeta):
            carpeta.validar_carpeta(str(prohibida))
    Negocio.objects.filter(pk=1).update(carpeta_respaldo=str((tmp_path / "respaldo").resolve()))
    with pytest.raises(carpeta.ErrorCarpeta):
        carpeta.validar_carpeta(str(tmp_path / "respaldo"))
    c = cliente(personas["dir"])
    assert c.post(reverse("configuracion:carpeta_banco"), {"carpeta_banco": str(Path(settings.RAIZ) / "docs")}).status_code == 200
    assert c.post(reverse("configuracion:carpeta_banco"), {"carpeta_banco": str(tmp_path / "vigilada")}).url == reverse("configuracion:indice")
    assert Negocio.objects.get().carpeta_banco == str((tmp_path / "vigilada").resolve()) and (tmp_path / "vigilada" / "rechazados").is_dir()
    assert Evento.objects.filter(accion="carpeta_banco_cambiada").exists()


def test_espera_a_que_el_tamano_no_cambie_y_luego_importa(base):
    personas, ana, vigilada = base
    contenido = pdf(estado([enlace(5, 1000, "intereses")]))
    ruta = dejar(vigilada, "agosto.pdf", contenido[: len(contenido) // 2])
    assert carpeta.revisar()["esperando"] == 1 and ruta.exists()
    ruta.write_bytes(contenido)
    assert carpeta.revisar()["esperando"] == 1 and ruta.exists() and not Importacion.objects.exists()
    assert carpeta.revisar()["importados"] == 1 and not ruta.exists()
    importacion = Importacion.objects.get()
    assert importacion.origen == Importacion.CARPETA and importacion.creada_por is None and importacion.importo == "Carpeta vigilada"
    assert [p.name.endswith("-agosto.pdf") for p in (vigilada / "procesados").iterdir()] == [True]
    assert Evento.objects.filter(accion="carpeta_banco_importado").exists() and Evento.objects.filter(accion="importacion_bancaria", usuario__isnull=True).exists()
    assert not ArchivoVigilado.objects.exists()


def test_extension_tamano_y_repetidos_se_rechazan_con_motivo(base):
    personas, ana, vigilada = base
    dejar(vigilada, "programa.exe", b"MZ")
    dejar(vigilada, "sin_extension", b"x")
    dejar(vigilada, "enorme.csv", b"a" * (5 * 1024 * 1024 + 1))
    contenido = pdf(estado([enlace(5, 1000, "intereses")]))
    dejar(vigilada, "agosto.pdf", contenido)
    informe = dos_revisiones()
    assert informe["importados"] == 1
    assert "Extensión no admitida" in motivo_de(vigilada, "programa.exe")
    assert "Extensión no admitida" in motivo_de(vigilada, "sin_extension")
    assert "tamaño máximo" in motivo_de(vigilada, "enorme.csv")
    dejar(vigilada, "otra-vez.pdf", contenido)
    dos_revisiones()
    assert "ya se importó" in motivo_de(vigilada, "otra-vez.pdf")
    assert Importacion.objects.count() == 1 and not list(vigilada.glob("*.pdf"))


def test_archivo_que_no_es_lo_que_dice_se_rechaza(base):
    personas, ana, vigilada = base
    dejar(vigilada, "falso.pdf", b"PK\x03\x04 no es pdf")
    dejar(vigilada, "disfrazado.csv", pdf(estado([enlace(5, 1000, "x")])))
    dos_revisiones()
    assert "no lo es" in motivo_de(vigilada, "falso.pdf")
    assert motivo_de(vigilada, "disfrazado.csv")
    assert not Importacion.objects.exists()


def test_archivo_de_otra_cuenta_o_sin_columnas_aprendidas_se_rechaza(base):
    personas, ana, vigilada = base
    dejar(vigilada, "otra.pdf", pdf(estado([enlace(5, 1000, "x")], clabe="012180001234567897")))
    dejar(vigilada, "movs.csv", b"fecha,referencia,importe\n2026-08-05,1,100.00\n")
    dos_revisiones()
    assert "CLABE" in motivo_de(vigilada, "otra.pdf")
    assert "a mano" in motivo_de(vigilada, "movs.csv")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="sin enlaces")
def test_enlaces_no_se_siguen(base, tmp_path):
    personas, ana, vigilada = base
    secreto = tmp_path / "fuera.pdf"
    secreto.write_bytes(pdf(estado([enlace(5, 1000, "x")])))
    try:
        os.symlink(secreto, vigilada / "enlace.pdf")
        os.symlink(tmp_path, vigilada / "carpeta-enlazada")
    except OSError:
        pytest.skip("el sistema no permite crear enlaces")
    dos_revisiones()
    assert not Importacion.objects.exists() and secreto.exists()
    assert "enlace" in motivo_de(vigilada, "enlace.pdf")
    assert "enlace" in motivo_de(vigilada, "carpeta-enlazada")


def test_sin_continuidad_no_aplica_pagos_hasta_que_una_persona_la_libere(base):
    personas, ana, vigilada = base
    movimientos = [spei(10, 50000, referencia=ana.matricula)]
    dejar(vigilada, "agosto.pdf", pdf(estado(movimientos)))
    dos_revisiones()
    importacion = Importacion.objects.get()
    assert importacion.continuidad == Importacion.PRIMERA and importacion.retenida and not Pago.objects.filter(medio=Pago.BANCO).exists()
    movimiento = MovimientoBancario.objects.get(importacion=importacion)
    assert movimiento.estado == MovimientoBancario.POR_IDENTIFICAR and movimiento.sugerencia == ana.matricula
    inicio = cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    assert "retenidas" in inicio and "agosto.pdf" in inicio
    assert cliente(personas["op"]).post(reverse("conciliacion:liberar", args=[importacion.pk])).status_code == 403
    respuesta = cliente(personas["sup"]).post(reverse("conciliacion:liberar", args=[importacion.pk]))
    assert respuesta.url == reverse("conciliacion:importacion", args=[importacion.pk])
    pago = Pago.objects.get(medio=Pago.BANCO)
    assert pago.titular == ana and pago.registrado_por == personas["sup"]
    importacion.refresh_from_db()
    assert importacion.liberada_por == personas["sup"] and importacion.aplicados == 1
    with pytest.raises(conciliacion.ErrorConciliacion):
        conciliacion.liberar(importacion, personas["sup2"])
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 1


def test_continuidad_verificada_aplica_sola(base):
    personas, ana, vigilada = base
    agosto = [enlace(5, 1000, "intereses")]
    dejar(vigilada, "agosto.pdf", pdf(estado(agosto)))
    dos_revisiones()
    Importacion.objects.filter(retenida=True).update(liberada_por=personas["sup"])
    septiembre = [spei(3, 40000, referencia=ana.matricula)]
    dejar(vigilada, "septiembre.pdf", pdf(estado(septiembre, mes=9, saldo_inicial=saldo_final(agosto))))
    dos_revisiones()
    importacion = Importacion.objects.get(periodo_inicio__month=9)
    assert importacion.continuidad == Importacion.VERIFICADA and not importacion.retenida
    pago = Pago.objects.get(medio=Pago.BANCO)
    assert pago.registrado_por is None and pago.movimiento.importacion == importacion
    assert "importación automática" in cliente(personas["op"]).get(reverse("cobros:recibo", args=[pago.recibo.pk])).content.decode()


def test_estado_que_no_continua_se_rechaza(base):
    personas, ana, vigilada = base
    agosto = [enlace(5, 1000, "intereses")]
    dejar(vigilada, "agosto.pdf", pdf(estado(agosto)))
    dos_revisiones()
    dejar(vigilada, "septiembre.pdf", pdf(estado([spei(3, 40000, referencia=ana.matricula)], mes=9, saldo_inicial=saldo_final(agosto) + 1)))
    dos_revisiones()
    assert "No continúa" in motivo_de(vigilada, "septiembre.pdf")
    assert Importacion.objects.count() == 1


def test_quien_libera_no_marca_revisada_la_importacion(base):
    personas, ana, vigilada = base
    archivo = b"fecha,referencia,importe\n" + f"2026-08-05,{ana.matricula},500.00\n".encode()
    c = cliente(personas["sup"])
    from django.core.files.uploadedfile import SimpleUploadedFile

    r = c.post(reverse("conciliacion:importar"), {"archivo": SimpleUploadedFile("base.csv", b"fecha,referencia,importe\n2026-07-01,x,1.00\n"), "cuenta": cuenta_principal().pk})
    c.post(r.url, {"fecha": "0", "referencia": "1", "importe": "2"})
    c.post(reverse("conciliacion:previa", args=[r.url.split("/")[-3]]))
    dejar(vigilada, "movs.csv", archivo)
    dos_revisiones()
    importacion = Importacion.objects.get(origen=Importacion.CARPETA)
    assert importacion.continuidad == Importacion.NO_VERIFICABLE and importacion.retenida and not Pago.objects.filter(medio=Pago.BANCO).exists()
    conciliacion.liberar(importacion, personas["sup"])
    importacion.refresh_from_db()
    assert Pago.objects.filter(medio=Pago.BANCO).count() == 1
    with pytest.raises(conciliacion.RevisionPropia):
        conciliacion.marcar_revisada(importacion, personas["sup"])
    conciliacion.marcar_revisada(importacion, personas["dir"])


def test_el_trabajador_revisa_la_carpeta(base):
    personas, ana, vigilada = base
    dejar(vigilada, "agosto.pdf", pdf(estado([enlace(5, 1000, "x")])))
    ejecutar_ciclo()
    informe = dict((n, t) for n, _, t in ejecutar_ciclo())
    assert "1 importados" in informe["carpeta_banco"]
    Negocio.objects.filter(pk=1).update(carpeta_banco="")
    assert dict((n, t) for n, _, t in ejecutar_ciclo())["carpeta_banco"] == "sin carpeta vigilada del banco"
