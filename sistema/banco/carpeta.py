import os
import secrets
import stat
from pathlib import Path

from django.utils import timezone

from auditoria.servicios import registrar
from configuracion.models import Negocio

from . import conciliacion, lectura
from .models import ArchivoVigilado, Importacion, MapeoColumnas

PROCESADOS = "procesados"
RECHAZADOS = "rechazados"
LIMITES = {".pdf": lectura.LIMITE_PDF, ".xlsx": lectura.LIMITE_HOJA, ".csv": lectura.LIMITE_HOJA}
PUNTO_DE_REANALISIS = 0x400


class ErrorCarpeta(ValueError):
    pass


def validar_carpeta(texto):
    from cortes.entrega import ErrorEntrega, validar_ruta

    try:
        ruta = validar_ruta(texto)
    except ErrorEntrega as error:
        raise ErrorCarpeta(str(error))
    from cortes.entrega import _dentro
    from cortes.models import Destino

    negocio = Negocio.actual()
    otras = [negocio.carpeta_respaldo if negocio else ""] + list(Destino.objects.values_list("ruta", flat=True))
    propia = Path(ruta)
    for otra in otras:
        if not otra:
            continue
        ajena = Path(otra).resolve()
        if ajena == propia or _dentro(ajena, propia) or _dentro(propia, ajena):
            raise ErrorCarpeta("La carpeta vigilada no puede ser la de respaldo ni una carpeta de entrega de cortes, ni estar dentro de ellas o contenerlas.")
    for sub in (PROCESADOS, RECHAZADOS):
        _subcarpeta(propia, sub)
    return ruta


def _subcarpeta(base, nombre):
    ruta = Path(base) / nombre
    try:
        info = os.lstat(ruta)
    except FileNotFoundError:
        os.mkdir(ruta)
        info = os.lstat(ruta)
    if not stat.S_ISDIR(info.st_mode) or (getattr(info, "st_file_attributes", 0) & PUNTO_DE_REANALISIS):
        raise ErrorCarpeta(f"«{nombre}» dentro de la carpeta vigilada no es una carpeta normal (es un enlace u otro tipo de entrada). Quítala para que el sistema la vuelva a crear.")
    return ruta


def carpeta():
    negocio = Negocio.actual()
    return negocio.carpeta_banco if negocio else ""


def _es_regular(info):
    if not stat.S_ISREG(info.st_mode):
        return False
    return not (getattr(info, "st_file_attributes", 0) & PUNTO_DE_REANALISIS)


def _destino(base, subcarpeta, nombre):
    limpio = lectura.nombre_saneado(nombre)
    marca = f"{timezone.localtime():%Y%m%d-%H%M%S}"
    destino = Path(base) / subcarpeta / f"{marca}-{limpio}"
    if destino.exists() or os.path.lexists(destino):
        destino = Path(base) / subcarpeta / f"{marca}-{secrets.token_hex(3)}-{limpio}"
    return destino


def _mover(base, origen, subcarpeta, motivo=""):
    _subcarpeta(base, subcarpeta)
    destino = _destino(base, subcarpeta, origen.name)
    os.replace(origen, destino)
    if motivo:
        aviso = destino.with_name(destino.name + ".motivo.txt")
        descriptor = os.open(aviso, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as salida:
            salida.write(motivo.strip() + "\n")
    return destino


def _leer(ruta, info, limite):
    banderas = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(ruta, banderas)
    with os.fdopen(descriptor, "rb") as archivo:
        abierto = os.fstat(archivo.fileno())
        if not stat.S_ISREG(abierto.st_mode) or (info.st_ino and abierto.st_ino != info.st_ino) or abierto.st_size != info.st_size:
            raise ErrorCarpeta("El archivo cambió mientras se leía.")
        contenido = archivo.read(limite + 1)
    if len(contenido) > limite or len(contenido) != info.st_size:
        raise ErrorCarpeta("El archivo cambió mientras se leía.")
    return contenido


def _cuenta_de_hoja(filas):
    try:
        encabezado = lectura.detectar_encabezado(filas, conciliacion.SINONIMOS)
    except Exception:
        raise conciliacion.ErrorConciliacion("No se reconocen los encabezados del archivo.")
    titulos = [lectura.normal(c) for c in filas[encabezado]]
    candidatos = [m for m in MapeoColumnas.objects.select_related("cuenta").filter(cuenta__activa=True) if m.mapeo.get("titulos") == titulos]
    if len(candidatos) != 1:
        raise conciliacion.ErrorConciliacion("No se reconoce de qué cuenta es el archivo: impórtalo una vez a mano para que el sistema aprenda sus columnas.")
    return candidatos[0].cuenta, encabezado, dict(candidatos[0].mapeo.get("columnas", {}))


def importar_contenido(nombre, contenido, sha256):
    if contenido.startswith(b"%PDF"):
        if not nombre.lower().endswith(".pdf"):
            raise conciliacion.ErrorConciliacion("El contenido es un PDF pero la extensión no lo es.")
        cuenta, movimientos, resumen = conciliacion.movimientos_de_pdf(lectura.lineas_de_pdf(contenido))
        return conciliacion.importar(cuenta, movimientos, Importacion.ESTADO_PDF, nombre, sha256, None, resumen, origen=Importacion.CARPETA)
    if nombre.lower().endswith(".pdf"):
        raise conciliacion.ErrorConciliacion("El archivo dice ser PDF y no lo es.")
    filas = lectura.filas_de_hoja(nombre, contenido)
    cuenta, encabezado, columnas = _cuenta_de_hoja(filas)
    movimientos = conciliacion.movimientos_de_filas(filas, encabezado, columnas, cuenta)
    return conciliacion.importar(cuenta, movimientos, Importacion.ARCHIVO, nombre, sha256, None, None, origen=Importacion.CARPETA)


def _rechazar(base, ruta, motivo, sha256=""):
    destino = _mover(base, ruta, RECHAZADOS, motivo)
    registrar("carpeta_banco_rechazo", datos={"archivo": lectura.nombre_saneado(ruta.name), "motivo": motivo[:300], "sha256": sha256, "movido_a": destino.name})
    return destino


def _revisar_entrada(base, entrada, presentes, informe):
    nombre = entrada.name
    if nombre.startswith(".") or nombre in (PROCESADOS, RECHAZADOS):
        return
    ruta_archivo = base / nombre
    try:
        info = os.lstat(ruta_archivo)
    except FileNotFoundError:
        return
    if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        return
    presentes.add(nombre)
    if not _es_regular(info):
        _rechazar(base, ruta_archivo, "No es un archivo normal (es un enlace u otro tipo de entrada); no se sigue.")
        informe["rechazados"] += 1
        return
    extension = Path(nombre).suffix.lower()
    limite = LIMITES.get(extension)
    if limite is None:
        _rechazar(base, ruta_archivo, f"Extensión no admitida ({extension or 'sin extensión'}). Se aceptan: {', '.join(sorted(LIMITES))}.")
        informe["rechazados"] += 1
        return
    if info.st_size > limite:
        _rechazar(base, ruta_archivo, f"El archivo pasa del tamaño máximo de importación ({limite // (1024 * 1024)} MB).")
        informe["rechazados"] += 1
        return
    anterior = ArchivoVigilado.objects.filter(nombre=nombre[:255]).first()
    if anterior is None or anterior.tamano != info.st_size or anterior.modificado != info.st_mtime_ns:
        ArchivoVigilado.objects.update_or_create(nombre=nombre[:255], defaults={"tamano": info.st_size, "modificado": info.st_mtime_ns})
        informe["esperando"] += 1
        return
    try:
        contenido = _leer(ruta_archivo, info, limite)
    except (OSError, ErrorCarpeta):
        ArchivoVigilado.objects.filter(nombre=nombre[:255]).delete()
        informe["esperando"] += 1
        return
    huella = lectura.huella_archivo(contenido)
    if Importacion.objects.filter(sha256=huella).exists():
        _rechazar(base, ruta_archivo, "Este archivo ya se importó antes (mismo SHA-256).", huella)
        ArchivoVigilado.objects.filter(nombre=nombre[:255]).delete()
        informe["rechazados"] += 1
        return
    try:
        importacion = importar_contenido(nombre, contenido, huella)
    except (lectura.ErrorLectura, conciliacion.ErrorConciliacion) as error:
        _rechazar(base, ruta_archivo, str(error), huella)
        ArchivoVigilado.objects.filter(nombre=nombre[:255]).delete()
        informe["rechazados"] += 1
        return
    destino = _mover(base, ruta_archivo, PROCESADOS)
    ArchivoVigilado.objects.filter(nombre=nombre[:255]).delete()
    registrar("carpeta_banco_importado", objeto=importacion, datos={"archivo": importacion.nombre_archivo, "sha256": huella, "movido_a": destino.name, "retenida": importacion.retenida})
    informe["importados"] += 1


def _avisar_bloqueo(motivo):
    from datetime import timedelta

    from auditoria.models import Evento

    if Evento.objects.filter(accion="carpeta_banco_bloqueada", momento__gte=timezone.now() - timedelta(hours=6)).exists():
        return
    registrar("carpeta_banco_bloqueada", datos={"motivo": motivo[:300]})


def revisar():
    ruta = carpeta()
    if not ruta:
        return {"sin_carpeta": True}
    try:
        base = Path(validar_carpeta(ruta))
    except ErrorCarpeta as error:
        _avisar_bloqueo(str(error))
        return {"importados": 0, "rechazados": 0, "esperando": 0, "bloqueada": str(error)}
    informe = {"importados": 0, "rechazados": 0, "esperando": 0}
    presentes = set()
    with os.scandir(base) as entradas:
        lista = sorted(entradas, key=lambda e: e.name)
    for entrada in lista:
        try:
            _revisar_entrada(base, entrada, presentes, informe)
        except (OSError, ErrorCarpeta) as error:
            _avisar_bloqueo(str(error))
            informe["bloqueada"] = str(error)
            break
    ArchivoVigilado.objects.exclude(nombre__in=presentes).delete()
    return informe
