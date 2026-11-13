import hashlib
import os
import re
import secrets
import warnings
from io import BytesIO
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageOps
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject

from .models import ComprobanteRetiro

LIMITE = 5 * 1024 * 1024
MAXIMO_PIXELES = 40_000_000
MAXIMO_PAGINAS = 50
MAXIMO_OBJETOS = 200000
EXTENSIONES = {ComprobanteRetiro.JPEG: "jpg", ComprobanteRetiro.PNG: "png", ComprobanteRetiro.PDF: "pdf"}
TIPOS_MIME = {ComprobanteRetiro.JPEG: "image/jpeg", ComprobanteRetiro.PNG: "image/png", ComprobanteRetiro.PDF: "application/pdf"}
NOMBRE = re.compile(r"^[0-9a-f]{32}\.(jpg|png|pdf)$")
CLAVES_ACTIVAS = {"/JS", "/JavaScript", "/Launch", "/EmbeddedFile", "/EmbeddedFiles", "/AA", "/RichMedia", "/XFA", "/AcroForm", "/OpenAction"}
ACCIONES_ACTIVAS = {"/JavaScript", "/Launch", "/SubmitForm", "/ImportData", "/GoToE", "/GoToR", "/Rendition", "/Sound", "/Movie", "/ResetForm", "/Hide", "/SetOCGState", "/Trans", "/GoTo3DView", "/RichMediaExecute"}
CRUDO_ACTIVO = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFiles?|RichMedia|XFA|AcroForm|OpenAction|AA)(?![A-Za-z0-9])")
ESCAPE_NOMBRE = re.compile(rb"#([0-9A-Fa-f]{2})")


class ComprobanteInvalido(ValueError):
    pass


def carpeta():
    configurada = getattr(settings, "RUTA_COMPROBANTES", "")
    if not configurada:
        raise ComprobanteInvalido("No hay carpeta para guardar comprobantes en esta instalación.")
    ruta = Path(configurada)
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_de(nombre):
    if not NOMBRE.match(nombre or ""):
        raise ComprobanteInvalido("Nombre de comprobante no válido.")
    return carpeta() / nombre


def tipo_de(contenido):
    if contenido.startswith(b"\xff\xd8\xff"):
        return ComprobanteRetiro.JPEG
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return ComprobanteRetiro.PNG
    if contenido.startswith(b"%PDF-"):
        return ComprobanteRetiro.PDF
    raise ComprobanteInvalido("Solo se aceptan fotos JPEG o PNG y archivos PDF.")


def _imagen(contenido, tipo):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(contenido)) as previa:
                formato = previa.format
                ancho, alto = previa.size
                if ancho * alto > MAXIMO_PIXELES:
                    raise ComprobanteInvalido("La imagen es demasiado grande.")
                previa.verify()
            if formato != {"jpeg": "JPEG", "png": "PNG"}[tipo]:
                raise ComprobanteInvalido("El contenido de la imagen no corresponde a su tipo.")
            with Image.open(BytesIO(contenido)) as imagen:
                imagen.load()
                girada = ImageOps.exif_transpose(imagen)
                salida = BytesIO()
                if tipo == ComprobanteRetiro.JPEG:
                    _solo_pixeles(girada, "RGB").save(salida, format="JPEG", quality=85)
                else:
                    modo = "RGBA" if girada.mode in ("RGBA", "LA", "P") else "RGB"
                    _solo_pixeles(girada, modo).save(salida, format="PNG")
    except ComprobanteInvalido:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ComprobanteInvalido("La imagen es demasiado grande.")
    except Exception:
        raise ComprobanteInvalido("La imagen está dañada o no se puede leer.")
    return salida.getvalue()


def _solo_pixeles(imagen, modo):
    convertida = imagen.convert(modo)
    return Image.frombytes(modo, convertida.size, convertida.tobytes())


def _nombres_crudos(contenido):
    return ESCAPE_NOMBRE.sub(lambda m: bytes([int(m.group(1), 16)]), contenido)


def _revisar_objeto(raiz):
    pendientes = [raiz]
    vistos = set()
    revisados = 0
    while pendientes:
        objeto = pendientes.pop()
        if isinstance(objeto, IndirectObject):
            clave = (objeto.idnum, objeto.generation)
            if clave in vistos:
                continue
            vistos.add(clave)
            objeto = objeto.get_object()
        revisados += 1
        if revisados > MAXIMO_OBJETOS:
            raise ComprobanteInvalido("El PDF es demasiado complejo.")
        if isinstance(objeto, DictionaryObject):
            for llave, valor in objeto.items():
                if str(llave) in CLAVES_ACTIVAS:
                    raise ComprobanteInvalido("El PDF tiene contenido activo (acciones, formularios, JavaScript o archivos incrustados).")
                if str(llave) == "/S" and isinstance(valor, NameObject) and str(valor) in ACCIONES_ACTIVAS:
                    raise ComprobanteInvalido("El PDF tiene contenido activo (acciones, formularios, JavaScript o archivos incrustados).")
                pendientes.append(valor)
        elif isinstance(objeto, ArrayObject):
            pendientes.extend(objeto)


def _pdf(contenido):
    if CRUDO_ACTIVO.search(_nombres_crudos(contenido)):
        raise ComprobanteInvalido("El PDF tiene contenido activo (acciones, formularios, JavaScript o archivos incrustados).")
    try:
        lector = PdfReader(BytesIO(contenido), strict=False)
        if lector.is_encrypted:
            raise ComprobanteInvalido("El PDF está cifrado o protegido con contraseña.")
        if len(lector.pages) > MAXIMO_PAGINAS:
            raise ComprobanteInvalido(f"El PDF tiene más de {MAXIMO_PAGINAS} páginas.")
        _revisar_objeto(lector.trailer)
    except ComprobanteInvalido:
        raise
    except Exception:
        raise ComprobanteInvalido("El PDF está dañado o no se puede leer.")
    return contenido


def preparar(contenido):
    if not contenido:
        raise ComprobanteInvalido("El archivo está vacío.")
    if len(contenido) > LIMITE:
        raise ComprobanteInvalido("El comprobante pasa de 5 MB.")
    tipo = tipo_de(contenido)
    limpio = _pdf(contenido) if tipo == ComprobanteRetiro.PDF else _imagen(contenido, tipo)
    if len(limpio) > LIMITE:
        raise ComprobanteInvalido("El comprobante pasa de 5 MB.")
    return tipo, limpio


def leer_subida(archivo):
    if archivo is None:
        raise ComprobanteInvalido("Elige el archivo del comprobante.")
    if archivo.size > LIMITE:
        raise ComprobanteInvalido("El comprobante pasa de 5 MB.")
    contenido = archivo.read(LIMITE + 1)
    if len(contenido) > LIMITE:
        raise ComprobanteInvalido("El comprobante pasa de 5 MB.")
    return contenido


def guardar(tipo, contenido):
    nombre = f"{secrets.token_hex(16)}.{EXTENSIONES[tipo]}"
    ruta = ruta_de(nombre)
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(descriptor, "wb") as salida:
        salida.write(contenido)
        salida.flush()
        os.fsync(salida.fileno())
    return nombre, hashlib.sha256(contenido).hexdigest()


def descartar(nombre):
    try:
        os.unlink(ruta_de(nombre))
    except OSError:
        pass


def leer(comprobante):
    contenido = ruta_de(comprobante.archivo).read_bytes()
    if hashlib.sha256(contenido).hexdigest() != comprobante.sha256:
        raise ComprobanteInvalido("El archivo del comprobante no coincide con su huella.")
    return contenido


def todos():
    return [(c.archivo, c.sha256) for c in ComprobanteRetiro.objects.order_by("id")]
