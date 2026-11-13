import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Evento
from cobros import libro
from cobros.models import Pago
from configuracion.models import Negocio
from cuentas import secretos
from cuentas.models import Usuario
from nucleo import sobre, totp
from respaldos import servicios
from respaldos.models import Respaldo
from respaldos.restauracion import restaurar

from .conftest import CONTRASENA, cliente, codigo_actual, equipo_aprobado
from .libro_ayudas import preparar_conceptos, titular_activo, turno_de


def residuos():
    return {p.name for p in Path(tempfile.gettempdir()).iterdir() if p.name.startswith("ariasmos-")}


@pytest.fixture
def con_datos(personas, tmp_path, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        preparar_conceptos()
        ana = titular_activo(personas["op"], personas["sup"], "Ana")
        beto = titular_activo(personas["op"], personas["sup"], "Beto")
        libro.registrar_pago(ana, 60000, Pago.EFECTIVO, personas["op"], turno=turno_de(personas["op"]))
    carpeta = tmp_path / "respaldos"
    Negocio.objects.filter(pk=1).update(carpeta_respaldo=str(carpeta))
    return personas, carpeta, (ana, beto)


def saldos(ruta):
    with sqlite3.connect(ruta) as base:
        cargos = base.execute("SELECT titular_id, SUM(importe_final) FROM cobros_cargo GROUP BY titular_id ORDER BY titular_id").fetchall()
        aplicado = base.execute(
            "SELECT c.titular_id, SUM(a.importe) FROM cobros_aplicacion a JOIN cobros_cargo c ON c.id = a.cargo_id GROUP BY c.titular_id ORDER BY c.titular_id"
        ).fetchall()
        pagos = base.execute("SELECT COUNT(*), SUM(importe) FROM cobros_pago").fetchone()
    return cargos, aplicado, pagos


@pytest.mark.django_db(transaction=True)
def test_respaldo_prueba_y_restauracion_en_instancia_vacia(con_datos, tmp_path, settings):
    personas, carpeta, (ana, _) = con_datos
    antes = residuos()
    registro = servicios.respaldar(personas["dir"])
    assert registro.resultado == Respaldo.CORRECTO, registro.mensaje
    archivos = list(carpeta.iterdir())
    assert [a.name for a in archivos] == [registro.archivo] and archivos[0].suffix == ".respaldo"
    crudo = archivos[0].read_bytes()
    assert b"SQLite format" not in crudo and ana.matricula.encode() not in crudo and b"clave_auditoria" not in crudo
    assert residuos() == antes
    prueba = servicios.probar(personas["dir"])
    assert prueba.resultado == Respaldo.CORRECTO, prueba.mensaje
    assert prueba.conteos == registro.conteos and registro.conteos["titulares"] == 2 and registro.conteos["pagos"] == 1
    assert residuos() == antes
    texto = sobre.clave_a_texto(bytes(settings.CLAVE_RESPALDO))
    nueva = tmp_path / "equipo-nuevo" / "instancia"
    resultado = restaurar(archivos[0], texto.lower(), destino=nueva)
    configuracion = json.loads((nueva / "configuracion.json").read_text())
    assert configuracion["clave_respaldo"] == bytes(settings.CLAVE_RESPALDO).hex() and configuracion["base_datos"] == str(nueva / "cobro.sqlite3")
    assert oct(os.stat(nueva / "configuracion.json").st_mode)[-3:] == "600"
    origen = Path(settings.DATABASES["default"]["NAME"]) if Path(settings.DATABASES["default"]["NAME"]).exists() else Path(settings.DATABASES["default"]["TEST"]["NAME"])
    assert saldos(nueva / "cobro.sqlite3") == saldos(origen)
    valida, eventos = servicios._cadena_valida(str(nueva / "cobro.sqlite3"), bytes(settings.CLAVE_AUDITORIA))
    assert valida and eventos == resultado["eventos"] == registro.conteos["eventos"]
    assert residuos() == antes
    for evento in Evento.objects.all():
        contenido = json.dumps(evento.datos)
        assert texto not in contenido and bytes(settings.CLAVE_RESPALDO).hex() not in contenido
    with sqlite3.connect(origen) as base:
        volcado = "\n".join(base.iterdump())
    assert texto not in volcado and bytes(settings.CLAVE_RESPALDO).hex() not in volcado


@pytest.mark.django_db(transaction=True)
def test_restaurar_rechaza_clave_equivocada_y_archivos_alterados_sin_tocar_nada(con_datos, tmp_path, settings):
    personas, carpeta, _ = con_datos
    archivo = carpeta / servicios.respaldar(personas["dir"]).archivo
    texto = sobre.clave_a_texto(bytes(settings.CLAVE_RESPALDO))
    destino = tmp_path / "instancia"
    destino.mkdir()
    (destino / "configuracion.json").write_text('{"intacta": true}')
    otra = sobre.clave_a_texto(sobre.nueva_clave())
    crudo = archivo.read_bytes()
    alterado = tmp_path / "alterado.respaldo"
    alterado.write_bytes(crudo[:200] + bytes([crudo[200] ^ 1]) + crudo[201:])
    truncado = tmp_path / "truncado.respaldo"
    truncado.write_bytes(crudo[: len(crudo) // 2])
    falso = tmp_path / "falso.respaldo"
    falso.write_bytes(b"no soy un respaldo")
    casos = [(archivo, otra), (alterado, texto), (truncado, texto), (falso, texto), (archivo, texto[:-1] + ("A" if texto[-1] != "A" else "B"))]
    for ruta, clave in casos:
        with pytest.raises((sobre.ErrorSobre, servicios.ErrorRespaldo)):
            restaurar(ruta, clave, reemplazar=True, destino=destino)
        assert (destino / "configuracion.json").read_text() == '{"intacta": true}' and sorted(p.name for p in destino.iterdir()) == ["configuracion.json"]
    assert not list(tmp_path.glob("instancia-anterior-*"))
    with pytest.raises(servicios.ErrorRespaldo, match="Ya hay una instalación"):
        restaurar(archivo, texto, destino=destino)
    resultado = restaurar(archivo, texto, reemplazar=True, destino=destino)
    assert Path(resultado["copia_anterior"]).is_dir() and (Path(resultado["copia_anterior"]) / "configuracion.json").read_text() == '{"intacta": true}'
    assert json.loads((destino / "configuracion.json").read_text())["clave_respaldo"] == bytes(settings.CLAVE_RESPALDO).hex()


@pytest.mark.django_db(transaction=True)
def test_comandos_respaldar_probar_y_restaurar(con_datos, tmp_path, settings, monkeypatch):
    personas, carpeta, _ = con_datos
    call_command("respaldar")
    call_command("probar_respaldo")
    archivo = next(carpeta.iterdir())
    vacia = tmp_path / "otra-instancia"
    monkeypatch.setenv("COBRO_INSTANCIA", str(vacia))
    with pytest.raises(CommandError):
        call_command("restaurar", "--archivo", str(archivo), "--clave", "AAAA-BBBB")
    assert not vacia.exists()
    call_command("restaurar", "--archivo", str(archivo), "--clave", sobre.clave_a_texto(bytes(settings.CLAVE_RESPALDO)))
    assert (vacia / "cobro.sqlite3").exists() and (vacia / "configuracion.json").exists()
    with pytest.raises(CommandError, match="Ya hay"):
        call_command("restaurar", "--archivo", str(archivo), "--clave", sobre.clave_a_texto(bytes(settings.CLAVE_RESPALDO)))


@pytest.mark.django_db(transaction=True)
def test_respaldo_sin_carpeta_falla_con_alerta_y_trabajador(personas, settings):
    registro = servicios.respaldar()
    assert registro.resultado == Respaldo.FALLO and "carpeta" in registro.mensaje
    assert any("carpeta" in a for a in servicios.alertas())
    inicio = cliente(personas["dir"]).get(reverse("inicio")).content.decode()
    assert "No hay carpeta de respaldo configurada" in inicio
    assert "No hay carpeta de respaldo" not in cliente(personas["sup"]).get(reverse("inicio")).content.decode()


@pytest.mark.django_db(transaction=True)
def test_alerta_si_el_ultimo_respaldo_tiene_mas_de_48_horas(con_datos):
    personas, carpeta, _ = con_datos
    registro = servicios.respaldar()
    assert servicios.alertas() == []
    Respaldo.objects.filter(pk=registro.pk).update(creado=timezone.now() - timedelta(hours=49))
    assert any("48 horas" in a for a in servicios.alertas())


def test_retencion_30_diarios_y_12_mensuales(tmp_path):
    inicio = datetime(2026, 11, 12, 2, 0)
    nombres = []
    for dias in range(0, 500, 1):
        momento = inicio - timedelta(days=dias)
        nombre = servicios.nombre_archivo(momento)
        (tmp_path / nombre).write_bytes(b"x")
        nombres.append((momento, nombre))
    (tmp_path / "otro-archivo.txt").write_text("no se toca")
    servicios.retener(tmp_path)
    quedan = sorted(p.name for p in tmp_path.iterdir() if p.name.endswith(".respaldo"))
    diarios = {servicios.nombre_archivo(inicio - timedelta(days=d)) for d in range(30)}
    assert diarios <= set(quedan)
    meses = {(m.year, m.month) for m, _ in nombres}
    ultimos_meses = sorted(meses, reverse=True)[:12]
    for mes in ultimos_meses:
        assert any(servicios._fecha_de(n).year == mes[0] and servicios._fecha_de(n).month == mes[1] for n in quedan)
    assert len(quedan) <= 30 + 12 and (tmp_path / "otro-archivo.txt").exists()


def test_clave_de_recuperacion_se_ve_una_vez(personas, settings):
    c = cliente(personas["dir"])
    texto = sobre.clave_a_texto(bytes(settings.CLAVE_RESPALDO))
    assert "Guarda la clave de recuperación" in c.get(reverse("inicio")).content.decode()
    pagina = c.get(reverse("respaldos:clave"))
    assert texto in pagina.content.decode() and pagina["Cache-Control"] == "no-store"
    assert c.post(reverse("respaldos:clave"), {}).status_code == 200
    assert c.post(reverse("respaldos:clave"), {"guardada": "on"}).status_code == 302
    for url in (reverse("respaldos:clave"), reverse("respaldos:panel"), reverse("inicio")):
        assert texto not in c.get(url).content.decode()
    assert cliente(personas["sup"]).get(reverse("respaldos:clave")).status_code == 403
    anterior = bytes(settings.CLAVE_RESPALDO)
    c.post(reverse("respaldos:clave_nueva"))
    assert bytes(settings.CLAVE_RESPALDO) != anterior and Negocio.objects.get().clave_recuperacion_pendiente
    assert sobre.clave_a_texto(bytes(settings.CLAVE_RESPALDO)) in c.get(reverse("respaldos:clave")).content.decode()
    assert Evento.objects.filter(accion="clave_recuperacion_cambiada").exists()
    assert not any(texto in json.dumps(e.datos) for e in Evento.objects.all())


def test_carpeta_de_respaldo_validada(personas, tmp_path, settings):
    c = cliente(personas["dir"])
    for ruta in ("respaldos", str(Path(settings.RAIZ) / "respaldos")):
        assert c.post(reverse("respaldos:carpeta"), {"carpeta_respaldo": ruta}).status_code == 200
    assert c.post(reverse("respaldos:carpeta"), {"carpeta_respaldo": str(tmp_path / "r")}).status_code == 302
    assert Negocio.objects.get().carpeta_respaldo == str((tmp_path / "r").resolve())


def test_secretos_del_autenticador_cifrados_y_el_inicio_de_sesion_funciona(personas):
    direccion = personas["dir"]
    direccion.refresh_from_db()
    assert sobre.esta_cifrado(direccion.totp_cifrado) and secretos.en_claro() == 0
    secreto = secretos.leer(direccion)
    assert secreto not in direccion.totp_cifrado
    Usuario.objects.filter(pk=direccion.pk).update(totp_cifrado=secreto)
    assert secretos.en_claro() == 1
    call_command("cifrar_secretos")
    assert secretos.en_claro() == 0
    direccion.refresh_from_db()
    assert secretos.leer(direccion) == secreto
    c = cliente(credencial=equipo_aprobado(), usuario=None)
    c.post(reverse("entrar"), {"usuario": direccion.usuario, "contrasena": CONTRASENA})
    respuesta = c.post(reverse("entrar_codigo"), {"codigo": totp.codigo(secreto, totp.paso_actual())})
    assert respuesta.status_code == 302 and respuesta.url == reverse("inicio")
    otro = personas["sup"]
    otro.refresh_from_db()
    Usuario.objects.filter(pk=otro.pk).update(totp_cifrado=direccion.totp_cifrado)
    otro.refresh_from_db()
    with pytest.raises(sobre.ErrorSobre):
        secretos.leer(otro)
    assert codigo_actual(direccion)


@pytest.mark.django_db(transaction=True)
def test_la_prueba_detecta_una_bitacora_alterada_en_la_copia(con_datos, tmp_path, settings):
    personas, carpeta, _ = con_datos
    registro = servicios.respaldar()
    extraidos = servicios.abrir(carpeta / registro.archivo, bytes(settings.CLAVE_RESPALDO), str(tmp_path))
    assert servicios.verificar_paquete(extraidos)["eventos"] == registro.conteos["eventos"]
    with servicios.abrir_sqlite(extraidos[servicios.BASE]) as base:
        base.execute("UPDATE auditoria_evento SET accion = 'otra' WHERE numero = 2")
    with pytest.raises(servicios.ErrorRespaldo, match="bitácora"):
        servicios.verificar_paquete(extraidos)
