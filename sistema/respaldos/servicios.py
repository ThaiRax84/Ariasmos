import hashlib
import io
import json
import os
import re
import secrets
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, time
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError, connection
from django.utils import timezone

from auditoria import ancla
from auditoria.servicios import registrar
from configuracion.models import Negocio, hoy_negocio, parametro
from nucleo import cadena, sobre
from proyecto import instancia

from .models import Respaldo

PREFIJO = "ariasmos-"
EXTENSION = ".respaldo"
PATRON = re.compile(r"^ariasmos-(\d{8})-(\d{6})\.respaldo$")
DIARIOS = 30
MENSUALES = 12
HORAS_ALERTA = 48
DIAS_PRUEBA = 30
BASE = "base.sqlite3"
CONFIGURACION = "configuracion.json"
ANCLA = "ancla_auditoria.json"
MANIFIESTO = "manifiesto.json"
MIEMBROS = {BASE, CONFIGURACION, ANCLA, MANIFIESTO}
TABLAS = {"titulares": "titulares_titular", "cargos": "cobros_cargo", "pagos": "cobros_pago", "eventos": "auditoria_evento"}


class ErrorRespaldo(ValueError):
    pass


def configuracion_actual():
    ruta = getattr(settings, "RUTA_INSTANCIA", "")
    if ruta and (Path(ruta) / instancia.ARCHIVO).exists():
        return json.loads((Path(ruta) / instancia.ARCHIVO).read_text(encoding="utf-8"))
    return {
        "clave_django": settings.SECRET_KEY,
        "clave_matricula": bytes(settings.CLAVE_MATRICULA).hex(),
        "clave_auditoria": bytes(settings.CLAVE_AUDITORIA).hex(),
        "clave_respaldo": bytes(settings.CLAVE_RESPALDO).hex(),
        "clave_secretos": bytes(settings.CLAVE_SECRETOS).hex(),
        "https": True,
        "hosts": list(settings.ALLOWED_HOSTS),
        "origenes_confiables": [],
        "proxies_confiables": ["127.0.0.1", "::1"],
    }


def clave_respaldo():
    return bytes.fromhex(configuracion_actual()["clave_respaldo"])


def nueva_clave_respaldo(usuario=None, request=None):
    clave = sobre.nueva_clave()
    ruta = getattr(settings, "RUTA_INSTANCIA", "")
    if ruta and (Path(ruta) / instancia.ARCHIVO).exists():
        datos = configuracion_actual()
        datos["clave_respaldo"] = clave.hex()
        destino = Path(ruta) / instancia.ARCHIVO
        temporal = destino.with_name(f".{destino.name}.{secrets.token_hex(6)}.tmp")
        descriptor = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, indent=2, ensure_ascii=False)
        os.replace(temporal, destino)
    else:
        settings.CLAVE_RESPALDO = clave
    Negocio.objects.filter(pk=1).update(clave_recuperacion_pendiente=True)
    registrar("clave_recuperacion_cambiada", usuario=usuario, datos={"nota": "los respaldos anteriores solo se abren con la clave anterior"}, request=request)
    return clave


def local(momento):
    negocio = Negocio.actual()
    try:
        return timezone.localtime(momento, ZoneInfo(negocio.zona_horaria)) if negocio else timezone.localtime(momento)
    except Exception:
        return timezone.localtime(momento)


def carpeta():
    negocio = Negocio.actual()
    return negocio.carpeta_respaldo if negocio else ""


def _regexp(patron, valor):
    return valor is not None and re.search(patron, str(valor)) is not None


def abrir_sqlite(ruta, **opciones):
    base = sqlite3.connect(ruta, **opciones)
    base.create_function("REGEXP", 2, _regexp, deterministic=True)
    return base


def _conteos_db(ruta):
    with abrir_sqlite(ruta) as base:
        return {nombre: base.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] for nombre, tabla in TABLAS.items()}


def _copiar_base(destino):
    origen = abrir_sqlite(connection.settings_dict["NAME"], timeout=60)
    copia = abrir_sqlite(destino)
    try:
        origen.backup(copia)
    finally:
        copia.close()
        origen.close()


def _agregar(tar, nombre, contenido):
    info = tarfile.TarInfo(nombre)
    info.size = len(contenido)
    info.mtime = int(timezone.now().timestamp())
    info.mode = 0o600
    tar.addfile(info, io.BytesIO(contenido))


def nombre_archivo(momento):
    return f"{PREFIJO}{momento:%Y%m%d-%H%M%S}{EXTENSION}"


def respaldar(usuario=None, automatico=False, dia=None):
    from cortes.entrega import validar_ruta

    destino = carpeta()
    try:
        registro = Respaldo.objects.create(tipo=Respaldo.RESPALDO, automatico=automatico, dia=dia if automatico else None)
    except IntegrityError:
        return None
    temporal = tempfile.mkdtemp(prefix="ariasmos-respaldo-")
    salida_temporal = None
    try:
        if not destino:
            raise ErrorRespaldo("No hay carpeta de respaldo configurada.")
        destino = validar_ruta(destino)
        base = os.path.join(temporal, BASE)
        _copiar_base(base)
        conteos = _conteos_db(base)
        momento = local(timezone.now())
        registro_ancla = ancla.leer() or {}
        manifiesto = {"version": 1, "creado": momento.isoformat(), "conteos": conteos, "ancla": {"numero": registro_ancla.get("numero"), "sello": registro_ancla.get("sello")}}
        paquete = os.path.join(temporal, "paquete.tar")
        with tarfile.open(paquete, "w") as tar:
            tar.add(base, arcname=BASE)
            _agregar(tar, CONFIGURACION, json.dumps(configuracion_actual(), indent=2).encode("utf-8"))
            if registro_ancla:
                _agregar(tar, ANCLA, json.dumps(registro_ancla).encode("utf-8"))
            _agregar(tar, MANIFIESTO, json.dumps(manifiesto, indent=1).encode("utf-8"))
        nombre = nombre_archivo(momento)
        final = Path(destino) / nombre
        salida_temporal = Path(destino) / f".{nombre}.{secrets.token_hex(6)}.tmp"
        with open(paquete, "rb") as origen, open(salida_temporal, "wb") as cifrado:
            sobre.cifrar(origen, cifrado, clave_respaldo())
            cifrado.flush()
            os.fsync(cifrado.fileno())
        os.chmod(salida_temporal, 0o600)
        os.replace(salida_temporal, final)
        salida_temporal = None
        contenido = final.read_bytes()
        Respaldo.objects.filter(pk=registro.pk).update(
            resultado=Respaldo.CORRECTO, archivo=nombre, tamano=len(contenido), sha256=hashlib.sha256(contenido).hexdigest(), conteos=conteos, terminado=timezone.now()
        )
        registrar("respaldo_creado", usuario=usuario, datos={"archivo": nombre, "tamano": len(contenido), "conteos": conteos})
        retener(destino)
    except Exception as error:
        mensaje = f"{type(error).__name__}: {error}"[:300]
        Respaldo.objects.filter(pk=registro.pk).update(resultado=Respaldo.FALLO, mensaje=mensaje, terminado=timezone.now())
        registrar("respaldo_fallido", usuario=usuario, datos={"error": mensaje})
    finally:
        shutil.rmtree(temporal, ignore_errors=True)
        if salida_temporal is not None and Path(salida_temporal).exists():
            Path(salida_temporal).unlink()
    registro.refresh_from_db()
    return registro


def _fecha_de(nombre):
    encontrado = PATRON.match(nombre)
    if not encontrado:
        return None
    return datetime.strptime(encontrado.group(1) + encontrado.group(2), "%Y%m%d%H%M%S")


def retener(destino):
    archivos = sorted(((f, _fecha_de(f.name)) for f in Path(destino).iterdir() if f.is_file() and _fecha_de(f.name)), key=lambda par: par[1], reverse=True)
    conservar = set()
    dias = []
    for archivo, momento in archivos:
        if momento.date() not in dias:
            dias.append(momento.date())
            if len(dias) <= DIARIOS:
                conservar.add(archivo)
    meses = []
    for archivo, momento in archivos:
        mes = (momento.year, momento.month)
        if mes not in meses:
            meses.append(mes)
            if len(meses) <= MENSUALES:
                conservar.add(archivo)
    borrados = 0
    for archivo, _ in archivos:
        if archivo not in conservar:
            archivo.unlink()
            borrados += 1
    return borrados


def ultimo_archivo(destino=None):
    destino = destino or carpeta()
    if not destino or not Path(destino).is_dir():
        return None
    candidatos = sorted((f for f in Path(destino).iterdir() if f.is_file() and _fecha_de(f.name)), key=lambda f: _fecha_de(f.name))
    return candidatos[-1] if candidatos else None


def abrir(archivo, clave, destino):
    paquete = os.path.join(destino, "paquete.tar")
    with open(archivo, "rb") as origen, open(paquete, "wb") as claro:
        sobre.descifrar(origen, claro, clave)
    extraidos = {}
    with tarfile.open(paquete, "r") as tar:
        for miembro in tar.getmembers():
            if miembro.name not in MIEMBROS or not miembro.isfile():
                raise ErrorRespaldo(f"El paquete contiene algo inesperado: {miembro.name!r}")
            ruta = os.path.join(destino, miembro.name)
            with tar.extractfile(miembro) as entrada, open(ruta, "wb") as salida:
                shutil.copyfileobj(entrada, salida)
            extraidos[miembro.name] = ruta
    os.unlink(paquete)
    for necesario in (BASE, CONFIGURACION, MANIFIESTO):
        if necesario not in extraidos:
            raise ErrorRespaldo(f"Al paquete le falta {necesario}.")
    return extraidos


def _contenido(fila):
    numero, momento, usuario, usuario_texto, equipo, accion, objeto_tipo, objeto_id, titular, datos, ip = fila
    instante = datetime.fromisoformat(str(momento).replace(" ", "T"))
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=dt_timezone.utc)
    return {
        "numero": numero,
        "momento": instante.astimezone(dt_timezone.utc).isoformat(),
        "usuario": usuario,
        "usuario_texto": usuario_texto,
        "equipo": equipo,
        "accion": accion,
        "objeto_tipo": objeto_tipo,
        "objeto_id": objeto_id,
        "titular": titular,
        "datos": json.loads(datos) if isinstance(datos, str) else datos,
        "ip": ip,
    }


def _cadena_valida(ruta_base, clave_auditoria):
    consulta = "SELECT numero, momento, usuario_id, usuario_texto, equipo, accion, objeto_tipo, objeto_id, titular, datos, ip, sello_anterior, sello FROM auditoria_evento ORDER BY numero"
    anterior = cadena.GENESIS
    esperado = 1
    with abrir_sqlite(ruta_base) as base:
        for fila in base.execute(consulta):
            numero, sello_anterior, sello = fila[0], fila[11], fila[12]
            if numero != esperado or sello_anterior != anterior or cadena.sellar(clave_auditoria, anterior, _contenido(fila[:11])) != sello:
                return False, numero
            anterior = sello
            esperado += 1
    return True, esperado - 1


def verificar_paquete(extraidos):
    with abrir_sqlite(extraidos[BASE]) as base:
        resultado = base.execute("PRAGMA integrity_check").fetchone()[0]
    if resultado != "ok":
        raise ErrorRespaldo(f"La base del respaldo no está íntegra: {resultado}")
    manifiesto = json.loads(Path(extraidos[MANIFIESTO]).read_text(encoding="utf-8"))
    conteos = _conteos_db(extraidos[BASE])
    if conteos != manifiesto.get("conteos"):
        raise ErrorRespaldo("Los conteos de la base no coinciden con los del momento del respaldo.")
    configuracion = json.loads(Path(extraidos[CONFIGURACION]).read_text(encoding="utf-8"))
    valida, numero = _cadena_valida(extraidos[BASE], bytes.fromhex(configuracion["clave_auditoria"]))
    if not valida:
        raise ErrorRespaldo(f"La bitácora de la copia no está íntegra (evento {numero}).")
    ancla_paquete = manifiesto.get("ancla") or {}
    if ancla_paquete.get("numero") and ancla_paquete["numero"] > numero:
        raise ErrorRespaldo("La copia está por detrás del ancla de la bitácora.")
    return {"conteos": conteos, "eventos": numero, "configuracion": configuracion, "manifiesto": manifiesto}


def probar(usuario=None, automatico=False, dia=None, archivo=None):
    try:
        registro = Respaldo.objects.create(tipo=Respaldo.PRUEBA, automatico=automatico, dia=dia if automatico else None)
    except IntegrityError:
        return None
    temporal = tempfile.mkdtemp(prefix="ariasmos-prueba-")
    try:
        archivo = archivo or ultimo_archivo()
        if archivo is None:
            raise ErrorRespaldo("No hay respaldos que probar.")
        revision = verificar_paquete(abrir(archivo, clave_respaldo(), temporal))
        Respaldo.objects.filter(pk=registro.pk).update(resultado=Respaldo.CORRECTO, archivo=Path(archivo).name, conteos=revision["conteos"], terminado=timezone.now())
        registrar("respaldo_probado", usuario=usuario, datos={"archivo": Path(archivo).name, "conteos": revision["conteos"], "eventos": revision["eventos"]})
    except Exception as error:
        mensaje = f"{type(error).__name__}: {error}"[:300]
        Respaldo.objects.filter(pk=registro.pk).update(resultado=Respaldo.FALLO, mensaje=mensaje, terminado=timezone.now(), archivo=Path(archivo).name if archivo else "")
        registrar("prueba_respaldo_fallida", usuario=usuario, datos={"error": mensaje})
    finally:
        shutil.rmtree(temporal, ignore_errors=True)
    registro.refresh_from_db()
    return registro


def toca_respaldo(ahora=None):
    ahora = local(ahora or timezone.now())
    try:
        hora = time.fromisoformat(str(parametro("hora_respaldo")))
    except ValueError:
        hora = time(2, 0)
    return ahora.time() >= hora and not Respaldo.objects.filter(tipo=Respaldo.RESPALDO, automatico=True, dia=hoy_negocio()).exists()


def toca_prueba():
    ultima = Respaldo.objects.filter(tipo=Respaldo.PRUEBA).exclude(resultado=Respaldo.EN_CURSO).first()
    if ultima is None:
        return Respaldo.objects.filter(tipo=Respaldo.RESPALDO, resultado=Respaldo.CORRECTO).exists()
    return (timezone.now() - ultima.creado).days >= DIAS_PRUEBA


def alertas():
    avisos = []
    if not carpeta():
        avisos.append("No hay carpeta de respaldo configurada: no se están haciendo respaldos.")
    ultimo = Respaldo.objects.filter(tipo=Respaldo.RESPALDO, resultado=Respaldo.CORRECTO).first()
    if ultimo is None or (timezone.now() - ultimo.creado).total_seconds() > HORAS_ALERTA * 3600:
        avisos.append(f"El último respaldo correcto tiene más de {HORAS_ALERTA} horas." if ultimo else "Todavía no hay ningún respaldo correcto.")
    prueba = Respaldo.objects.filter(tipo=Respaldo.PRUEBA).exclude(resultado=Respaldo.EN_CURSO).first()
    if prueba is not None and prueba.resultado == Respaldo.FALLO:
        avisos.append(f"La última prueba de restauración falló: {prueba.mensaje}")
    return avisos
