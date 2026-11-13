import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from actualizaciones import aviso, llaves

RAIZ = Path(__file__).resolve().parents[1]
FIRMA = RAIZ / "herramientas" / "firma"
CONTRASENA_USO = "contrasena-de-uso-larga-1"
CONTRASENA_RECUPERACION = "contrasena-de-recuperacion-2"


def herramienta(nombre):
    especificacion = importlib.util.spec_from_file_location(f"herramienta_{nombre.replace('-', '_')}", FIRMA / f"{nombre}.py")
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def error_firma():
    herramienta("generar-llaves")
    return sys.modules["comun"].ErrorFirma


def contestar(*respuestas):
    pendientes = list(respuestas)
    return lambda pregunta: pendientes.pop(0)


@pytest.fixture
def llaves_generadas(tmp_path):
    carpeta = tmp_path / "llaves"
    carpeta.mkdir()
    publicas = herramienta("generar-llaves").generar([str(carpeta)], pedir=contestar(CONTRASENA_USO, CONTRASENA_USO, CONTRASENA_RECUPERACION, CONTRASENA_RECUPERACION))
    return carpeta, publicas


def test_generar_llaves_cifradas_y_publicas_para_el_programa(llaves_generadas):
    carpeta, publicas = llaves_generadas
    for nombre in ("uso", "recuperacion"):
        contenido = (carpeta / f"{nombre}.llave-privada").read_bytes()
        assert b"ENCRYPTED PRIVATE KEY" in contenido
        if os.name == "posix":
            assert (carpeta / f"{nombre}.llave-privada").stat().st_mode & 0o077 == 0
    assert llaves.del_programa(carpeta / "llaves.json") == publicas
    with pytest.raises(error_firma()):
        herramienta("generar-llaves").generar([str(carpeta)], pedir=contestar(CONTRASENA_USO, CONTRASENA_USO, CONTRASENA_RECUPERACION, CONTRASENA_RECUPERACION))


def test_generar_llaves_exige_contrasenas_largas_y_distintas(tmp_path):
    generar = herramienta("generar-llaves")
    with pytest.raises(error_firma()):
        generar.generar([str(tmp_path)], pedir=contestar("corta", "corta"))
    with pytest.raises(error_firma()):
        generar.generar([str(tmp_path)], pedir=contestar(CONTRASENA_USO, CONTRASENA_USO, CONTRASENA_USO, CONTRASENA_USO))
    assert not list(tmp_path.iterdir())


def test_firmar_version_produce_un_aviso_que_el_programa_acepta(llaves_generadas, tmp_path):
    carpeta, publicas = llaves_generadas
    instalador = tmp_path / "Ariasmos-0.9.0-instalador.exe"
    instalador.write_bytes(b"MZ" + b"\x00" * 5000)
    cambios = tmp_path / "cambios.txt"
    cambios.write_text("Topes del banco por día\n\nAviso de versiones nuevas\n", encoding="utf-8")
    salida = tmp_path / "salida"
    salida.mkdir()
    argumentos = ["--instalador", str(instalador), "--version", "0.9.0", "--contador", "3", "--cambios", str(cambios), "--minimo", "0.8.0", "--llave", str(carpeta / "uso.llave-privada"), "--salida", str(salida), "--fecha", "2026-11-20"]
    herramienta("firmar-version").firmar(argumentos, pedir=contestar(CONTRASENA_USO))
    datos, firma = (salida / "version.json").read_bytes(), (salida / "version.json.firma").read_bytes()
    leido = aviso.leer_version(datos, firma, publicas["uso"])
    assert leido["contador"] == 3 and leido["cambios"] == ["Topes del banco por día", "Aviso de versiones nuevas"] and leido["instalador"]["tamano"] == 5002
    with pytest.raises(aviso.AvisoInvalido):
        aviso.leer_version(datos, firma, publicas["recuperacion"])
    with pytest.raises(error_firma()):
        herramienta("firmar-version").firmar(argumentos, pedir=contestar(CONTRASENA_USO))
    otra = tmp_path / "otra"
    otra.mkdir()
    with pytest.raises(error_firma()):
        herramienta("firmar-version").firmar(argumentos[:-4] + ["--salida", str(otra)], pedir=contestar("contrasena-equivocada-123"))
    with pytest.raises(error_firma()):
        herramienta("firmar-version").firmar([*argumentos[:3], "1.02.0", *argumentos[4:-4], "--salida", str(otra)], pedir=contestar(CONTRASENA_USO))


def test_cambiar_llave_con_la_de_recuperacion(llaves_generadas, tmp_path):
    carpeta, publicas = llaves_generadas
    salida = tmp_path / "cambio"
    salida.mkdir()
    nueva = herramienta("cambiar-llave").cambiar(
        ["--recuperacion", str(carpeta / "recuperacion.llave-privada"), "--contador", "1", "--carpeta-llave", str(carpeta), "--salida", str(salida)],
        pedir=contestar(CONTRASENA_RECUPERACION, "contrasena-nueva-de-uso", "contrasena-nueva-de-uso"),
    )
    leido = aviso.leer_cambio_de_llave((salida / "cambio-de-llave.json").read_bytes(), (salida / "cambio-de-llave.json.firma").read_bytes(), publicas["recuperacion"])
    assert leido["llave_uso"] == nueva and nueva not in publicas.values()
    assert b"ENCRYPTED PRIVATE KEY" in (carpeta / "uso-1.llave-privada").read_bytes()


def test_las_herramientas_del_dueno_no_van_en_el_paquete():
    construir = (RAIZ / "instalacion" / "construir.ps1").read_text(encoding="utf-8-sig")
    assert "Join-Path $Raiz 'herramientas'" not in construir and "'herramientas', " not in construir
    assert json.loads((RAIZ / "sistema" / "actualizaciones" / "llaves.json").read_text(encoding="utf-8")) == {"uso": "", "recuperacion": ""}
