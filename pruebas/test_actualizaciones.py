import io
import json
import os
import socket
import ssl
import sys
import urllib.request
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from actualizaciones import aviso, canales, llaves, servicios
from actualizaciones.canales import github
from actualizaciones.models import Configuracion, Descarga, LlaveDeUso, VersionPublicada
from auditoria.models import Evento
from configuracion import trabajador
from nucleo import sobre

from .actualizaciones_ayudas import INSTALADA, INSTALADOR, CanalFalso, cambio, escribir_llaves, firmado, objeto_version, par, publicar
from .conftest import cliente, equipo_aprobado

CLAVE = "github" + "_pat_" + "prueba" * 6
RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    def prohibido(*args, **kwargs):
        raise AssertionError("las pruebas no salen a la red")

    monkeypatch.setattr(socket.socket, "connect", prohibido)
    monkeypatch.setattr(socket, "create_connection", prohibido)
    monkeypatch.setattr(github, "abrir", prohibido)
    monkeypatch.setattr(urllib.request, "urlopen", prohibido)


@pytest.fixture
def efimeras(monkeypatch, tmp_path):
    uso_privada, uso = par()
    recuperacion_privada, recuperacion = par()
    monkeypatch.setattr(llaves, "RUTA", escribir_llaves(tmp_path / "llaves.json", uso, recuperacion))
    return SimpleNamespace(uso=uso_privada, uso_publica=uso, recuperacion=recuperacion_privada, recuperacion_publica=recuperacion)


@pytest.fixture
def entorno(personas, efimeras, monkeypatch, settings, tmp_path):
    settings.RUTA_ACTUALIZACIONES = str(tmp_path / "datos" / "actualizaciones")
    monkeypatch.setattr(servicios, "version_instalada", lambda: INSTALADA)
    monkeypatch.setattr(servicios, "_buscado_al_arrancar", False)
    canal = CanalFalso()
    monkeypatch.setattr(canales, "obtener", lambda *argumentos: canal)
    servicios.guardar_configuracion(True, "propietario/canal-versiones", CLAVE, usuario=personas["dir"])
    return SimpleNamespace(personas=personas, llaves=efimeras, canal=canal, carpeta=Path(settings.RUTA_ACTUALIZACIONES))


def eventos(accion):
    return Evento.objects.filter(accion=accion)


def test_llaves_del_repositorio_vacias_y_sin_ellas_no_se_activa(personas):
    contenido = json.loads((RAIZ / "sistema" / "actualizaciones" / "llaves.json").read_text(encoding="utf-8"))
    assert contenido == {"uso": "", "recuperacion": ""}
    assert llaves.del_programa() is None and not llaves.disponibles() and llaves.de_uso() is None
    with pytest.raises(servicios.ErrorActualizacion):
        servicios.guardar_configuracion(True, "propietario/canal", CLAVE, usuario=personas["dir"])
    assert not servicios.configuracion().activa
    c = cliente(personas["dir"])
    pagina = c.get(reverse("actualizaciones:configurar")).content.decode()
    assert "no trae llaves de actualización" in pagina and "disabled" in pagina
    c.post(reverse("actualizaciones:configurar"), {"activa": "on", "repositorio": "propietario/canal", "clave": CLAVE})
    assert not servicios.configuracion().activa
    assert servicios.ciclo() == "actualizaciones apagadas"


def test_archivo_de_llaves_estricto(tmp_path):
    _, uso = par()
    _, recuperacion = par()
    assert llaves.del_programa(escribir_llaves(tmp_path / "a.json", uso, recuperacion)) == {"uso": uso, "recuperacion": recuperacion}
    assert llaves.del_programa(escribir_llaves(tmp_path / "b.json", uso, uso)) is None
    assert llaves.del_programa(escribir_llaves(tmp_path / "c.json", uso, "corta")) is None
    (tmp_path / "d.json").write_text(json.dumps({"uso": uso, "recuperacion": recuperacion, "extra": 1}))
    assert llaves.del_programa(tmp_path / "d.json") is None
    (tmp_path / "e.json").write_bytes(b"\xff\xfe")
    assert llaves.del_programa(tmp_path / "e.json") is None


def test_aviso_valido_y_firma_sobre_los_bytes_exactos():
    privada, publica = par()
    datos, firma = firmado(privada, objeto_version())
    leido = aviso.leer_version(datos, firma, publica)
    assert leido["version"] == "0.9.0" and leido["instalador"]["tamano"] == len(INSTALADOR)
    alterado = datos.replace(b"0.9.0", b"0.9.1", 1)
    with pytest.raises(aviso.AvisoInvalido) as error:
        aviso.leer_version(alterado, firma, publica)
    assert error.value.motivo == "firma"
    with pytest.raises(aviso.AvisoInvalido) as error:
        aviso.leer_version(datos + b" ", firma, publica)
    assert error.value.motivo == "firma"
    otra, otra_publica = par()
    with pytest.raises(aviso.AvisoInvalido) as error:
        aviso.leer_version(datos, firma, otra_publica)
    assert error.value.motivo == "firma"
    with pytest.raises(aviso.AvisoInvalido) as error:
        aviso.leer_version(datos, firma[:63], publica)
    assert error.value.motivo == "firma"


def test_la_firma_se_comprueba_antes_de_interpretar():
    privada, publica = par()
    basura = b"{no es json"
    otra, _ = par()
    with pytest.raises(aviso.AvisoInvalido) as error:
        aviso.leer_version(basura, otra.sign(basura), publica)
    assert error.value.motivo == "firma"
    with pytest.raises(aviso.AvisoInvalido) as error:
        aviso.leer_version(basura, privada.sign(basura), publica)
    assert error.value.motivo == "formato"
    grande = b"[" + b" " * aviso.LIMITE_AVISO + b"]"
    with pytest.raises(aviso.AvisoInvalido) as error:
        aviso.leer_version(grande, privada.sign(grande), publica)
    assert error.value.motivo == "tamano_aviso"


def _modificado(**cambios):
    objeto = objeto_version()
    for clave, valor in cambios.items():
        if valor is KeyError:
            objeto.pop(clave)
        else:
            objeto[clave] = valor
    return objeto


@pytest.mark.parametrize(
    "objeto,motivo",
    [
        (_modificado(extra="x"), "formato"),
        (_modificado(cambios=KeyError), "formato"),
        (_modificado(producto="otro"), "producto"),
        (_modificado(contador=True), "formato"),
        (_modificado(contador=0), "formato"),
        (_modificado(version="1.02.0"), "formato"),
        (_modificado(version="1.2"), "formato"),
        (_modificado(minimo="1.0.0"), "formato"),
        (_modificado(fecha="2026-02-30"), "formato"),
        (_modificado(cambios=["x"] * 21), "formato"),
        (_modificado(cambios=["a" * 201]), "formato"),
        (_modificado(cambios=["línea\ncon salto"]), "formato"),
        (_modificado(cambios=["oculto‮"]), "formato"),
        (_modificado(instalador={"nombre": "../x.exe", "tamano": 10, "sha256": "0" * 64}), "formato"),
        (_modificado(instalador={"nombre": "a.exe", "tamano": 10, "sha256": "0" * 64, "url": "https://x"}), "formato"),
        (_modificado(instalador={"nombre": "a.exe", "tamano": 600 * 1024 * 1024, "sha256": "0" * 64}), "formato"),
        (_modificado(instalador={"nombre": "a.exe", "tamano": 10, "sha256": "A" * 64}), "formato"),
    ],
)
def test_formato_exacto(objeto, motivo):
    privada, publica = par()
    datos, firma = firmado(privada, objeto)
    with pytest.raises(aviso.AvisoInvalido) as error:
        aviso.leer_version(datos, firma, publica)
    assert error.value.motivo == motivo


def test_campos_repetidos_y_numeros_no_enteros_se_rechazan():
    privada, publica = par()
    texto = aviso.serializar(objeto_version()).decode()
    for crudo in (texto.replace('"producto": "ariasmos",', '"producto": "ariasmos", "producto": "ariasmos",'), texto.replace('"contador": 1,', '"contador": 1.0,'), "﻿" + texto):
        datos = crudo.encode("utf-8")
        with pytest.raises(aviso.AvisoInvalido) as error:
            aviso.leer_version(datos, privada.sign(datos), publica)
        assert error.value.motivo == "formato"


def test_busqueda_acepta_version_nueva_y_avisa_a_todos(entorno):
    publicar(entorno.canal, entorno.llaves.uso)
    assert "versión nueva: 0.9.0" in servicios.ciclo()
    version = VersionPublicada.objects.get()
    assert version.contador == 1 and servicios.configuracion().contador_version == 1
    assert eventos("actualizacion_aceptada").count() == 1
    for clave in ("op", "sup", "dir"):
        pagina = cliente(entorno.personas[clave]).get(reverse("inicio")).content.decode()
        assert "Hay una versión nueva: 0.9.0" in pagina and "Topes del banco por día" in pagina and "Descargar" in pagina
    entorno.canal.archivos.pop("version.json")
    entorno.canal.archivos["version.json"], entorno.canal.archivos["version.json.firma"] = firmado(entorno.llaves.uso, objeto_version(cambios=["<script>alerta()</script>"], contador=2))
    servicios.buscar()
    pagina = cliente(entorno.personas["op"]).get(reverse("inicio")).content.decode()
    assert "<script>alerta()" not in pagina and "&lt;script&gt;alerta()" in pagina


def test_sin_cambios_no_deja_eventos_y_busca_una_vez_al_dia(entorno):
    publicar(entorno.canal, entorno.llaves.uso)
    servicios.ciclo()
    config = servicios.configuracion()
    assert config.proxima_busqueda > timezone.now() and config.ultima_busqueda is not None
    assert not servicios.toca_buscar(config)
    pedidos = len(entorno.canal.pedidos)
    servicios.ciclo()
    assert len(entorno.canal.pedidos) == pedidos
    assert servicios.toca_buscar(config, config.proxima_busqueda + timedelta(seconds=1))
    assert "Sin cambios" in servicios.buscar()
    assert eventos("actualizacion_rechazada").count() == 0


def test_antirretroceso_por_contador_y_por_version(entorno):
    publicar(entorno.canal, entorno.llaves.uso, objeto_version(contador=5))
    servicios.buscar()
    publicar(entorno.canal, entorno.llaves.uso, objeto_version(version="0.9.5", contador=4))
    assert "rechazó" in servicios.buscar()
    assert eventos("actualizacion_rechazada").get().datos["motivo"] == "contador"
    publicar(entorno.canal, entorno.llaves.uso, objeto_version(version="0.9.5", contador=5))
    servicios.buscar()
    assert VersionPublicada.objects.count() == 1
    publicar(entorno.canal, entorno.llaves.uso, objeto_version(version="0.7.9", contador=9))
    servicios.buscar()
    assert eventos("actualizacion_rechazada").filter(datos__motivo="version_anterior").exists()
    publicar(entorno.canal, entorno.llaves.uso, objeto_version(version="0.8.0", contador=10))
    assert "Al día" in servicios.buscar()
    assert servicios.vigente().version == "0.9.0"


def test_rechazos_como_maximo_uno_cada_seis_horas_por_motivo(entorno):
    otra, _ = par()
    publicar(entorno.canal, otra)
    servicios.buscar()
    servicios.buscar()
    assert eventos("actualizacion_rechazada").count() == 1
    assert not VersionPublicada.objects.exists()
    assert servicios.rechazar("firma", ahora=timezone.now() + timedelta(hours=7))
    assert eventos("actualizacion_rechazada").count() == 2
    assert servicios.rechazar("otro_motivo")


def test_cambio_de_llave_con_la_de_recuperacion(entorno):
    nueva, nueva_publica = par()
    entorno.canal.archivos["cambio-de-llave.json"], entorno.canal.archivos["cambio-de-llave.json.firma"] = cambio(entorno.llaves.recuperacion, nueva_publica, contador=1)
    publicar(entorno.canal, nueva)
    servicios.buscar()
    assert llaves.de_uso() == nueva_publica and LlaveDeUso.objects.count() == 1
    assert VersionPublicada.objects.get().llave == nueva_publica
    assert eventos("llave_de_uso_cambiada").count() == 1
    pagina = cliente(entorno.personas["dir"]).get(reverse("inicio")).content.decode()
    assert "Se cambió la llave de uso" in pagina
    assert "Se cambió la llave de uso" not in cliente(entorno.personas["op"]).get(reverse("inicio")).content.decode()
    publicar(entorno.canal, entorno.llaves.uso, objeto_version(version="0.9.1", contador=2))
    servicios.buscar()
    assert eventos("actualizacion_rechazada").filter(datos__motivo="firma").exists()
    assert VersionPublicada.objects.count() == 1


def test_cambio_de_llave_firmado_con_la_de_uso_o_con_contador_viejo_se_rechaza(entorno):
    nueva, nueva_publica = par()
    entorno.canal.archivos["cambio-de-llave.json"], entorno.canal.archivos["cambio-de-llave.json.firma"] = cambio(entorno.llaves.uso, nueva_publica)
    publicar(entorno.canal, entorno.llaves.uso)
    servicios.buscar()
    assert llaves.de_uso() == entorno.llaves.uso_publica and not LlaveDeUso.objects.exists()
    assert eventos("actualizacion_rechazada").filter(datos__motivo="cambio_de_llave_firma").exists()
    assert VersionPublicada.objects.count() == 1
    entorno.canal.archivos["cambio-de-llave.json"], entorno.canal.archivos["cambio-de-llave.json.firma"] = cambio(entorno.llaves.recuperacion, nueva_publica, contador=3)
    servicios.buscar()
    otra, otra_publica = par()
    entorno.canal.archivos["cambio-de-llave.json"], entorno.canal.archivos["cambio-de-llave.json.firma"] = cambio(entorno.llaves.recuperacion, otra_publica, contador=2)
    servicios.buscar()
    assert llaves.de_uso() == nueva_publica
    assert eventos("actualizacion_rechazada").filter(datos__motivo="cambio_de_llave_contador").exists()
    entorno.canal.archivos["cambio-de-llave.json"], entorno.canal.archivos["cambio-de-llave.json.firma"] = cambio(entorno.llaves.recuperacion, entorno.llaves.recuperacion_publica, contador=9)
    servicios.buscar()
    assert llaves.de_uso() == nueva_publica


def test_llave_cambiada_deja_de_valer_si_el_programa_trae_otra_recuperacion(entorno, monkeypatch, tmp_path):
    nueva, nueva_publica = par()
    entorno.canal.archivos["cambio-de-llave.json"], entorno.canal.archivos["cambio-de-llave.json.firma"] = cambio(entorno.llaves.recuperacion, nueva_publica)
    publicar(entorno.canal, nueva)
    servicios.buscar()
    _, uso = par()
    _, recuperacion = par()
    monkeypatch.setattr(llaves, "RUTA", escribir_llaves(tmp_path / "otras.json", uso, recuperacion))
    assert llaves.de_uso() == uso


def test_minimo_mayor_que_la_instalada_no_ofrece_descarga(entorno):
    publicar(entorno.canal, entorno.llaves.uso, objeto_version(minimo="0.8.5"))
    servicios.buscar()
    pagina = cliente(entorno.personas["op"]).get(reverse("inicio")).content.decode()
    assert "hay que instalar antes la versión 0.8.5" in pagina and 'action="/actualizaciones/descargar/"' not in pagina
    with pytest.raises(servicios.ErrorActualizacion):
        servicios.pedir_descarga(entorno.personas["op"])


def test_descarga_por_post_con_csrf_una_a_la_vez_y_tres_por_hora(entorno):
    publicar(entorno.canal, entorno.llaves.uso)
    servicios.buscar()
    url = reverse("actualizaciones:descargar")
    estricto = Client(enforce_csrf_checks=True)
    estricto.cookies["dispositivo"] = equipo_aprobado()
    estricto.force_login(entorno.personas["op"], backend="django.contrib.auth.backends.ModelBackend")
    assert estricto.post(url).status_code == 403
    assert cliente().post(url).status_code == 302 and not Descarga.objects.exists()
    c = cliente(entorno.personas["op"])
    assert c.get(url).status_code == 302 and not Descarga.objects.exists()
    assert c.post(url).status_code == 302
    descarga = Descarga.objects.get()
    assert descarga.pedida_por == entorno.personas["op"] and descarga.estado == Descarga.PENDIENTE
    with pytest.raises(servicios.ErrorActualizacion, match="en curso"):
        servicios.pedir_descarga(entorno.personas["sup"])
    pagina = c.get(reverse("inicio")).content.decode()
    assert "Descargando" in pagina and 'action="/actualizaciones/descargar/"' not in pagina
    for _ in range(2):
        Descarga.objects.filter(en_proceso=True).update(estado=Descarga.FALLIDA, en_proceso=None)
        servicios.pedir_descarga(entorno.personas["sup"])
    Descarga.objects.filter(en_proceso=True).update(estado=Descarga.FALLIDA, en_proceso=None)
    with pytest.raises(servicios.ErrorActualizacion, match="tres veces"):
        servicios.pedir_descarga(entorno.personas["dir"])
    assert "tres veces en la última hora" in c.get(reverse("inicio")).content.decode()


def test_el_trabajador_descarga_con_nombre_fijo_y_huella(entorno):
    objeto = objeto_version(nombre="Instalador-Del-Canal.exe")
    publicar(entorno.canal, entorno.llaves.uso, objeto)
    servicios.buscar()
    servicios.pedir_descarga(entorno.personas["op"])
    assert "lista para instalar" in servicios.ciclo()
    final = entorno.carpeta / "Ariasmos-0.9.0-instalador.exe"
    assert final.read_bytes() == INSTALADOR
    assert sorted(p.name for p in entorno.carpeta.iterdir()) == ["Ariasmos-0.9.0-instalador.exe"]
    if os.name == "posix":
        assert final.stat().st_mode & 0o077 == 0 and entorno.carpeta.stat().st_mode & 0o077 == 0
    descarga = Descarga.objects.get()
    assert descarga.estado == Descarga.LISTA and descarga.en_proceso is None and descarga.sha256 == objeto["instalador"]["sha256"]
    evento = eventos("actualizacion_descargada").get()
    assert evento.datos["pedida_por"] == "operacion"
    pagina = cliente(entorno.personas["op"]).get(reverse("inicio")).content.decode()
    assert "Lista para instalar: versión 0.9.0" in pagina and "Instalar actualización" in pagina
    assert "Se descargó la versión 0.9.0, pedida por operacion" in cliente(entorno.personas["dir"]).get(reverse("inicio")).content.decode()
    with pytest.raises(servicios.ErrorActualizacion, match="ya está descargada"):
        servicios.pedir_descarga(entorno.personas["sup"])
    assert "/static/" not in str(final) and not str(final).startswith(str(RAIZ / "sistema"))


def test_aviso_de_turnos_abiertos_al_estar_lista(entorno):
    from .libro_ayudas import turno_de

    publicar(entorno.canal, entorno.llaves.uso)
    servicios.buscar()
    servicios.pedir_descarga(entorno.personas["op"])
    servicios.ciclo()
    turno_de(entorno.personas["op"])
    pagina = cliente(entorno.personas["op"]).get(reverse("inicio")).content.decode()
    assert "Hay 1 turno de caja abierto" in pagina and "haz un respaldo" in pagina


@pytest.mark.parametrize("entregado,motivo", [(INSTALADOR[:-1] + b"X", "huella"), (INSTALADOR + b"X", "tamano"), (INSTALADOR[:-1], "tamano")])
def test_huella_o_tamano_distintos_se_borran_y_avisan(entorno, entregado, motivo):
    publicar(entorno.canal, entorno.llaves.uso)
    servicios.buscar()
    entorno.canal.entregar["Ariasmos-0.9.0-instalador.exe"] = entregado
    servicios.pedir_descarga(entorno.personas["op"])
    assert "rechazada" in servicios.ciclo()
    assert list(entorno.carpeta.iterdir()) == []
    descarga = Descarga.objects.get()
    assert descarga.estado == Descarga.FALLIDA and descarga.en_proceso is None
    assert eventos("actualizacion_rechazada").get().datos["motivo"] == motivo
    assert "no se completó" in cliente(entorno.personas["dir"]).get(reverse("inicio")).content.decode()
    assert not eventos("actualizacion_descargada").exists()


def test_sin_internet_no_pasa_nada(entorno):
    entorno.canal.sin_conexion = True
    assert servicios.ciclo() == servicios.TEXTOS["sin_conexion"]
    assert servicios.configuracion().ultimo_resultado == servicios.TEXTOS["sin_conexion"]
    assert not eventos("actualizacion_rechazada").exists() and not eventos("tarea_fallida").exists()
    pagina = cliente(entorno.personas["op"]).get(reverse("inicio")).content.decode()
    assert "conexión" not in pagina
    entorno.canal.sin_conexion = False
    publicar(entorno.canal, entorno.llaves.uso)
    servicios.buscar()
    servicios.pedir_descarga(entorno.personas["op"])
    entorno.canal.sin_conexion = True
    assert "fallida" in servicios.ciclo()
    assert Descarga.objects.get().estado == Descarga.FALLIDA and list(entorno.carpeta.iterdir()) == []


def test_descarga_interrumpida_se_libera(entorno):
    publicar(entorno.canal, entorno.llaves.uso)
    servicios.buscar()
    descarga = servicios.pedir_descarga(entorno.personas["op"])
    Descarga.objects.filter(pk=descarga.pk).update(estado=Descarga.EN_CURSO, iniciada_en=timezone.now() - timedelta(hours=2))
    servicios.ciclo()
    assert Descarga.objects.get().estado == Descarga.FALLIDA
    servicios.pedir_descarga(entorno.personas["op"])


def test_clave_cifrada_nunca_se_muestra_ni_va_a_la_bitacora(entorno):
    config = Configuracion.objects.get()
    assert CLAVE not in config.clave_cifrada and sobre.esta_cifrado(config.clave_cifrada)
    assert servicios.leer_clave(config) == CLAVE
    c = cliente(entorno.personas["dir"])
    pagina = c.get(reverse("actualizaciones:configurar")).content.decode()
    assert CLAVE not in pagina and config.clave_cifrada not in pagina and "Clave guardada: sí" in pagina
    otra = "github" + "_pat_" + "segunda" * 6
    c.post(reverse("actualizaciones:configurar"), {"activa": "on", "repositorio": "propietario/canal-versiones", "clave": otra})
    publicar(entorno.canal, entorno.llaves.uso)
    servicios.ciclo()
    for evento in Evento.objects.all():
        texto = json.dumps(evento.datos, ensure_ascii=False)
        assert CLAVE not in texto and otra not in texto and "prueba" * 6 not in texto
    configurado = eventos("actualizaciones_configuradas").latest("numero")
    assert configurado.datos["clave_cambiada"] is True and configurado.usuario == entorno.personas["dir"]
    assert servicios.leer_clave(Configuracion.objects.get()) == otra
    copia = Configuracion.objects.get().clave_cifrada
    with pytest.raises(sobre.ErrorSobre):
        sobre.descifrar_texto(sobre.derivar(bytes(range(32)), "actualizaciones"), copia, servicios.CONTEXTO_CLAVE)


def test_configurar_exige_clave_al_cambiar_de_repositorio_y_valida(entorno):
    c = cliente(entorno.personas["dir"])
    url = reverse("actualizaciones:configurar")
    respuesta = c.post(url, {"activa": "on", "repositorio": "otro/canal"})
    assert respuesta.status_code == 200 and "clave de solo lectura" in respuesta.content.decode()
    assert c.post(url, {"activa": "on", "repositorio": "no valido"}).status_code == 200
    assert c.post(url, {"activa": "on", "repositorio": "propietario/canal-versiones", "clave": "ghp_x\r\nHost: otro"}).status_code == 200
    assert servicios.configuracion().repositorio == "propietario/canal-versiones"
    assert c.post(url, {"repositorio": "propietario/canal-versiones"}).status_code == 302
    assert not servicios.configuracion().activa
    assert cliente(entorno.personas["sup"]).get(url).status_code == 403
    assert cliente(entorno.personas["op"]).get(url).status_code == 403
    sin_reingreso = cliente(entorno.personas["dir"], reingreso=False).get(url)
    assert sin_reingreso.status_code == 302 and reverse("confirmar") in sin_reingreso.url


def test_buscar_ahora_solo_direccion_y_con_limite(entorno):
    url = reverse("actualizaciones:buscar")
    assert cliente(entorno.personas["sup"]).post(url).status_code == 403
    c = cliente(entorno.personas["dir"])
    assert c.post(url).status_code == 302
    assert servicios.configuracion().busqueda_pedida
    with pytest.raises(servicios.ErrorActualizacion, match="minutos"):
        servicios.pedir_busqueda(entorno.personas["dir"])
    servicios.buscar()
    assert not servicios.configuracion().busqueda_pedida


def test_tarea_del_trabajador(entorno):
    assert "actualizaciones" in [nombre for nombre, _, _ in trabajador.TAREAS]
    publicar(entorno.canal, entorno.llaves.uso)
    informe = dict((nombre, (exito, texto)) for nombre, exito, texto in trabajador.ejecutar_ciclo())
    assert informe["actualizaciones"][0] and "0.9.0" in informe["actualizaciones"][1]


def _lista(entorno):
    publicar(entorno.canal, entorno.llaves.uso)
    servicios.buscar()
    servicios.pedir_descarga(entorno.personas["op"])
    servicios.ciclo()
    return entorno.carpeta / "Ariasmos-0.9.0-instalador.exe"


def test_instalar_vuelve_a_comprobar_firma_y_huella(entorno, monkeypatch):
    _lista(entorno)
    ejecutados = []
    monkeypatch.setattr(servicios, "lanzar_instalador", ejecutados.append)
    call_command("instalar_actualizacion", "--si", stdout=io.StringIO())
    assert len(ejecutados) == 1
    copia = Path(ejecutados[0])
    assert copia.parent.name.startswith("verificado-") and copia.parent.parent == entorno.carpeta and copia.read_bytes() == INSTALADOR
    assert eventos("actualizacion_instalacion_iniciada").count() == 1


def test_instalar_se_niega_si_el_archivo_cambio(entorno, monkeypatch):
    final = _lista(entorno)
    final.write_bytes(INSTALADOR[:-1] + b"Z")
    ejecutados = []
    monkeypatch.setattr(servicios, "lanzar_instalador", ejecutados.append)
    with pytest.raises(CommandError, match="huella"):
        call_command("instalar_actualizacion", "--si", stdout=io.StringIO())
    assert ejecutados == [] and not any(p.name.startswith("verificado-") for p in entorno.carpeta.iterdir())


def test_instalar_se_niega_si_el_aviso_guardado_cambio(entorno, monkeypatch):
    _lista(entorno)
    version = VersionPublicada.objects.get()
    VersionPublicada.objects.filter(pk=version.pk).update(aviso=bytes(version.aviso).replace(b"0.9.0", b"0.9.9"))
    ejecutados = []
    monkeypatch.setattr(servicios, "lanzar_instalador", ejecutados.append)
    with pytest.raises(CommandError, match="firma"):
        call_command("instalar_actualizacion", "--si", stdout=io.StringIO())
    assert ejecutados == []


def test_instalar_se_niega_con_un_enlace_y_sin_confirmacion(entorno, monkeypatch, tmp_path):
    final = _lista(entorno)
    ejecutados = []
    monkeypatch.setattr(servicios, "lanzar_instalador", ejecutados.append)
    monkeypatch.setattr("builtins.input", lambda texto: "no")
    with pytest.raises(CommandError, match="No se instaló"):
        call_command("instalar_actualizacion", stdout=io.StringIO())
    if hasattr(os, "symlink") and os.name == "posix":
        otro = tmp_path / "otro.exe"
        otro.write_bytes(INSTALADOR)
        final.unlink()
        os.symlink(otro, final)
        with pytest.raises(CommandError, match="archivo normal"):
            call_command("instalar_actualizacion", "--si", stdout=io.StringIO())
    assert ejecutados == []


def test_instalar_avisa_de_turnos_abiertos(entorno, monkeypatch):
    from .libro_ayudas import turno_de

    _lista(entorno)
    turno_de(entorno.personas["op"])
    monkeypatch.setattr(servicios, "lanzar_instalador", lambda ruta: None)
    salida = io.StringIO()
    call_command("instalar_actualizacion", "--si", stdout=salida)
    assert "1 turno(s) de caja abierto(s)" in salida.getvalue() and "respaldo" in salida.getvalue()


def test_lanzar_instalador_solo_en_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(servicios.ErrorActualizacion):
        servicios.lanzar_instalador("/tmp/x.exe")


class Respuesta:
    def __init__(self, estado, cuerpo=b"", cabeceras=None):
        self.status = estado
        self.headers = cabeceras or {}
        self._cuerpo = io.BytesIO(cuerpo)
        self.cerrada = False

    def read(self, cantidad=-1):
        return self._cuerpo.read(cantidad)

    def close(self):
        self.cerrada = True


class Red:
    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.peticiones = []

    def __call__(self, peticion, tiempo):
        self.peticiones.append(peticion)
        assert tiempo == github.TIEMPO_CONEXION
        return self.respuestas.pop(0)


def listado(*recursos):
    return json.dumps({"assets": [{"id": numero + 1, "name": nombre, "size": tamano} for numero, (nombre, tamano) in enumerate(recursos)]}).encode()


def test_github_lista_con_la_clave_solo_hacia_la_api():
    red = Red(Respuesta(200, listado(("version.json", 10), ("version.json.firma", 64))))
    canal = github.CanalGithub("propietario/canal-versiones", CLAVE, abrir_url=red)
    recursos = canal.publicacion()
    assert set(recursos) == {"version.json", "version.json.firma"} and recursos["version.json"].ident == "1"
    peticion = red.peticiones[0]
    assert peticion.full_url == "https://api.github.com/repos/propietario/canal-versiones/releases/latest"
    assert peticion.get_header("Authorization") == "Bearer " + CLAVE
    assert CLAVE not in repr(canal)


def test_github_una_sola_redireccion_sin_reenviar_la_clave():
    destino = "https://objects.githubusercontent.com/descarga?firma=abc"
    red = Red(Respuesta(302, cabeceras={"Location": destino}), Respuesta(200, b"contenido"))
    canal = github.CanalGithub("propietario/canal-versiones", CLAVE, abrir_url=red)
    assert canal.leer(canales.Recurso("version.json", 9, "7"), 100) == b"contenido"
    primera, segunda = red.peticiones
    assert primera.full_url.endswith("/releases/assets/7") and primera.get_header("Authorization")
    assert segunda.full_url == destino and segunda.get_header("Authorization") is None
    assert all(CLAVE not in valor for _, valor in segunda.header_items())


@pytest.mark.parametrize(
    "destino",
    [
        "https://malicioso.example.com/x",
        "http://objects.githubusercontent.com/x",
        "https://usuario:clave@objects.githubusercontent.com/x",
        "https://objects.githubusercontent.com:8443/x",
        "https://githubusercontent.com.malicioso.example/x",
        "https://.githubusercontent.com/x",
        "/relativa",
        None,
    ],
)
def test_github_redireccion_a_servidor_no_permitido(destino):
    red = Red(Respuesta(302, cabeceras={"Location": destino} if destino else {}))
    canal = github.CanalGithub("propietario/canal-versiones", CLAVE, abrir_url=red)
    with pytest.raises(canales.RespuestaInvalida):
        canal.leer(canales.Recurso("version.json", 9, "7"), 100)
    assert len(red.peticiones) == 1


def test_github_dos_redirecciones_se_rechazan():
    red = Red(Respuesta(302, cabeceras={"Location": "https://objects.githubusercontent.com/a"}), Respuesta(302, cabeceras={"Location": "https://objects.githubusercontent.com/b"}))
    canal = github.CanalGithub("propietario/canal-versiones", CLAVE, abrir_url=red)
    with pytest.raises(canales.RespuestaInvalida, match="más de una"):
        canal.leer(canales.Recurso("version.json", 9, "7"), 100)


def test_github_limites_de_tamano():
    canal = github.CanalGithub("propietario/canal-versiones", CLAVE, abrir_url=Red(Respuesta(200, b"x" * 101)))
    with pytest.raises(canales.Excedido):
        canal.leer(canales.Recurso("version.json", 50, "7"), 100)
    canal = github.CanalGithub("propietario/canal-versiones", CLAVE, abrir_url=Red(Respuesta(200, b"x", {"Content-Length": "5000"})))
    with pytest.raises(canales.Excedido):
        canal.leer(canales.Recurso("version.json", 50, "7"), 100)
    with pytest.raises(canales.Excedido):
        canal.leer(canales.Recurso("version.json", 101, "7"), 100)
    canal = github.CanalGithub("propietario/canal-versiones", CLAVE, abrir_url=Red(Respuesta(200, b"x" * (github.LIMITE_LISTADO + 1))))
    with pytest.raises(canales.Excedido):
        canal.publicacion()


def test_github_errores_de_red_y_de_clave():
    def caida(peticion, tiempo):
        raise OSError("sin red")

    with pytest.raises(canales.SinConexion):
        github.CanalGithub("propietario/canal-versiones", CLAVE, abrir_url=caida).publicacion()
    with pytest.raises(canales.ClaveRechazada):
        github.CanalGithub("propietario/canal-versiones", CLAVE, abrir_url=Red(Respuesta(401))).publicacion()
    with pytest.raises(canales.SinPublicacion):
        github.CanalGithub("propietario/canal-versiones", CLAVE, abrir_url=Red(Respuesta(404))).publicacion()
    with pytest.raises(canales.RespuestaInvalida):
        github.CanalGithub("propietario/canal-versiones", CLAVE, abrir_url=Red(Respuesta(200, b"[]"))).publicacion()


@pytest.mark.parametrize("repositorio", ["sin-barra", "a/b/c", "propietario/..", "-x/y", "propietario/nombre.git", "pro pietario/x"])
def test_github_repositorio_por_patron(repositorio):
    assert not github.repositorio_valido(repositorio)
    with pytest.raises(canales.ErrorCanal):
        github.CanalGithub(repositorio, CLAVE)


def test_github_clave_por_patron():
    for clave in ("", "ghp_corta", CLAVE + "\n", CLAVE + " x", "Bearer " + CLAVE):
        assert not github.clave_valida(clave)
    assert github.clave_valida(CLAVE) and github.clave_valida("ghp_" + "a1" * 18)


def test_github_sin_proxies_y_con_tls_por_omision(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    monkeypatch.setenv("https_proxy", "http://proxy.example:3128")
    abridor = github._abridor()
    assert not any(isinstance(manejador, urllib.request.ProxyHandler) for manejador in abridor.handlers)
    seguro = [m for m in abridor.handlers if isinstance(m, urllib.request.HTTPSHandler)]
    assert len(seguro) == 1 and seguro[0]._context.verify_mode == ssl.CERT_REQUIRED and seguro[0]._context.check_hostname
    assert not any(isinstance(manejador, urllib.request.HTTPHandler) for manejador in abridor.handlers)
    assert not any(isinstance(manejador, urllib.request.HTTPRedirectHandler) for manejador in abridor.handlers)


def test_la_integracion_continua_no_firma_ni_publica():
    for flujo in (RAIZ / ".github" / "workflows").glob("*.yml"):
        texto = flujo.read_text(encoding="utf-8").lower()
        for prohibido in ("gh release", "releases", "action-gh-release", "contents: write", "firmar-version", "llave-privada", "cambiar-llave"):
            assert prohibido not in texto, (flujo.name, prohibido)


def test_gitignore_excluye_llaves_privadas():
    reglas = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    for regla in ("*.llave-privada", "*.pem", "*.key"):
        assert regla in reglas
    assert not list(RAIZ.rglob("*.llave-privada"))


def test_acceso_directo_para_instalar_la_actualizacion():
    iss = (RAIZ / "instalacion" / "ariasmos.iss").read_text(encoding="utf-8-sig")
    assert "Instalar actualización" in iss and "instalar-actualizacion.cmd" in iss
    ps1 = (RAIZ / "instalacion" / "herramientas" / "instalar-actualizacion.ps1").read_text(encoding="utf-8-sig")
    assert "instalar_actualizacion" in ps1
    assert (RAIZ / "instalacion" / "herramientas" / "instalar-actualizacion.cmd").exists()
