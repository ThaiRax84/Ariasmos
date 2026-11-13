import threading

import pytest

from actualizaciones import aviso, llaves, servicios
from actualizaciones.models import Configuracion, Descarga, LlaveDeUso, VersionPublicada
from auditoria.models import Evento

from .actualizaciones_ayudas import cambio, escribir_llaves, objeto_version, par, publicar
from .test_actualizaciones import efimeras, entorno, sin_red  # noqa: F401


def poner_cambio(canal, datos, firma):
    canal.archivos["cambio-de-llave.json"] = datos
    canal.archivos["cambio-de-llave.json.firma"] = firma


def archivos(entorno):
    return sorted(ruta.name for ruta in entorno.carpeta.iterdir()) if entorno.carpeta.exists() else []


def test_llave_de_uso_robada_no_deja_sin_actualizaciones_tras_cambiarla(entorno):
    e = entorno
    falsa = objeto_version(version="9999.0.0", contador=aviso.MAXIMO_CONTADOR, nombre="Ariasmos-9999.0.0-instalador.exe")
    publicar(e.canal, e.llaves.uso, falsa)
    servicios.buscar()
    servicios.pedir_descarga(e.personas["op"])
    servicios.descargar_pendiente()
    assert servicios.vigente().version == "9999.0.0" and archivos(e) == ["Ariasmos-9999.0.0-instalador.exe"]
    nueva, nueva_publica = par()
    poner_cambio(e.canal, *cambio(e.llaves.recuperacion, nueva_publica, 1))
    publicar(e.canal, nueva, objeto_version(version="0.9.0", contador=1))
    assert servicios.buscar() == "Hay una versión nueva: 0.9.0."
    assert servicios.vigente().version == "0.9.0"
    assert archivos(e) == []
    assert not Descarga.objects.filter(estado=Descarga.LISTA).exists()
    assert Evento.objects.filter(accion="actualizacion_rechazada", datos__motivo="llave_de_uso_distinta").exists()
    with pytest.raises(servicios.ErrorActualizacion):
        servicios.preparar_instalacion()
    config = Configuracion.objects.get()
    assert (config.contador_version, config.contador_llave) == (1, 1)
    servicios.pedir_descarga(e.personas["op"])
    servicios.descargar_pendiente()
    assert servicios.preparar_instalacion()["version"] == "0.9.0"


def test_la_version_firmada_con_la_llave_retirada_deja_de_ofrecerse(entorno):
    e = entorno
    publicar(e.canal, e.llaves.uso, objeto_version(version="0.9.0", contador=4))
    servicios.buscar()
    assert servicios.aviso_para(e.personas["op"])["version"].version == "0.9.0"
    _, nueva_publica = par()
    e.canal.archivos.clear()
    poner_cambio(e.canal, *cambio(e.llaves.recuperacion, nueva_publica, 1))
    servicios.buscar()
    assert servicios.vigente() is None
    assert servicios.aviso_para(e.personas["op"]) is None
    with pytest.raises(servicios.ErrorActualizacion):
        servicios.pedir_descarga(e.personas["op"])


def test_un_programa_con_llaves_nuevas_vuelve_a_actualizarse(entorno, monkeypatch, tmp_path):
    e = entorno
    intermedia, intermedia_publica = par()
    poner_cambio(e.canal, *cambio(e.llaves.recuperacion, intermedia_publica, 3))
    publicar(e.canal, intermedia, objeto_version(version="0.9.0", contador=7))
    servicios.buscar()
    assert servicios.vigente().version == "0.9.0"
    uso, uso_publica = par()
    recuperacion, recuperacion_publica = par()
    monkeypatch.setattr(llaves, "RUTA", escribir_llaves(tmp_path / "nuevas.json", uso_publica, recuperacion_publica))
    assert servicios.vigente() is None
    e.canal.archivos.clear()
    publicar(e.canal, uso, objeto_version(version="0.9.5", contador=1, nombre="Ariasmos-0.9.5-instalador.exe"))
    assert servicios.buscar() == "Hay una versión nueva: 0.9.5."
    otra, otra_publica = par()
    poner_cambio(e.canal, *cambio(recuperacion, otra_publica, 1))
    publicar(e.canal, otra, objeto_version(version="0.9.6", contador=1, nombre="Ariasmos-0.9.6-instalador.exe"))
    assert servicios.buscar() == "Hay una versión nueva: 0.9.6."
    assert llaves.de_uso() == otra_publica
    assert LlaveDeUso.objects.count() == 2 and VersionPublicada.objects.count() == 3


def test_el_contador_sigue_protegiendo_dentro_de_la_misma_llave(entorno):
    e = entorno
    publicar(e.canal, e.llaves.uso, objeto_version(version="0.9.5", contador=5, nombre="Ariasmos-0.9.5-instalador.exe"))
    servicios.buscar()
    publicar(e.canal, e.llaves.uso, objeto_version(version="0.9.1", contador=4, nombre="Ariasmos-0.9.1-instalador.exe"))
    assert servicios.buscar() == "Se rechazó el aviso de versión."
    assert servicios.vigente().version == "0.9.5"
    viejo = cambio(e.llaves.recuperacion, par()[1], 2)
    poner_cambio(e.canal, *viejo)
    servicios.buscar()
    actual = llaves.de_uso()
    poner_cambio(e.canal, *cambio(e.llaves.recuperacion, par()[1], 1))
    servicios.buscar()
    assert llaves.de_uso() == actual


def test_la_descarga_del_servicio_no_detiene_las_demas_tareas(entorno, monkeypatch):
    e = entorno
    publicar(e.canal, e.llaves.uso)
    servicios.buscar()
    servicios.pedir_descarga(e.personas["op"])
    lanzados = []

    class HiloFalso:
        def __init__(self, target, name, daemon):
            self.target, self.vivo = target, False
            assert daemon

        def start(self):
            self.vivo = True
            lanzados.append(self)

        def is_alive(self):
            return self.vivo

    monkeypatch.setattr(threading, "Thread", HiloFalso)
    monkeypatch.setattr(servicios, "_hilo_descarga", None)
    assert "Descarga iniciada." in servicios.ciclo(en_hilo=True)
    assert Descarga.objects.filter(estado=Descarga.PENDIENTE).count() == 1
    assert "Descarga en curso." in servicios.ciclo(en_hilo=True)
    assert len(lanzados) == 1
    monkeypatch.setattr(servicios.connections, "close_all", lambda: None)
    lanzados[0].target()
    lanzados[0].vivo = False
    assert Descarga.objects.filter(estado=Descarga.LISTA).count() == 1
    assert "Descarga" not in servicios.ciclo(en_hilo=True)


def test_las_llaves_no_se_generan_dentro_del_repositorio(tmp_path):
    from .test_herramientas_firma import RAIZ, contestar, herramienta

    modulo = herramienta("generar-llaves")
    destino = RAIZ / "herramientas" / "firma"
    with pytest.raises(Exception, match="fuera del repositorio"):
        modulo.generar([str(destino)], pedir=contestar("x" * 20, "x" * 20, "y" * 20, "y" * 20))
    assert not list(destino.glob("*.llave-privada")) and not (destino / "llaves.json").exists()
