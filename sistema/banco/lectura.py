import csv
import hashlib
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime

from openpyxl import load_workbook
from pypdf import PdfReader

from nucleo.dinero import ErrorImporte, a_centavos
from nucleo.lectores import santander_pyme

LIMITE_PDF = 10 * 1024 * 1024
MAXIMO_PAGINAS = 300
LIMITE_HOJA = 5 * 1024 * 1024
LIMITE_DESCOMPRIMIDO = 50 * 1024 * 1024
MAXIMO_ENTRADAS_ZIP = 2000
MAXIMO_FILAS = 20000
MAXIMO_COLUMNAS = 60
MAXIMO_CELDA = 300
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}


class ErrorLectura(ValueError):
    pass


def huella_archivo(contenido):
    return hashlib.sha256(contenido).hexdigest()


def nombre_saneado(nombre):
    base = re.split(r"[\\/]", str(nombre or ""))[-1]
    limpio = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")
    return (limpio or "archivo")[:120]


def leer_subida(archivo, limite):
    if archivo is None:
        raise ErrorLectura("Elige un archivo.")
    if archivo.size > limite:
        raise ErrorLectura(f"El archivo pasa de {limite // (1024 * 1024)} MB.")
    contenido = archivo.read(limite + 1)
    if len(contenido) > limite:
        raise ErrorLectura(f"El archivo pasa de {limite // (1024 * 1024)} MB.")
    return contenido


def lineas_de_pdf(contenido):
    if len(contenido) > LIMITE_PDF:
        raise ErrorLectura("El PDF pasa de 10 MB.")
    if not contenido.startswith(b"%PDF"):
        raise ErrorLectura("El archivo no es un PDF.")
    try:
        lector = PdfReader(io.BytesIO(contenido), strict=False)
        if lector.is_encrypted:
            raise ErrorLectura("El PDF está cifrado o protegido con contraseña; descárgalo sin contraseña.")
        if len(lector.pages) > MAXIMO_PAGINAS:
            raise ErrorLectura("El PDF tiene demasiadas páginas.")
        lineas = []
        for pagina in lector.pages:
            lineas.extend((pagina.extract_text(extraction_mode="layout") or "").splitlines())
            if len(lineas) > santander_pyme.MAXIMO_LINEAS:
                raise ErrorLectura("El PDF tiene demasiado texto.")
    except ErrorLectura:
        raise
    except Exception:
        raise ErrorLectura("No se pudo leer el PDF.")
    return lineas


def _celda(valor):
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, float):
        return repr(round(valor, 2))
    return str(valor).replace("\x00", "").strip()[:MAXIMO_CELDA]


def filas_de_xlsx(contenido):
    if len(contenido) > LIMITE_HOJA:
        raise ErrorLectura("El archivo pasa de 5 MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as comprimido:
            entradas = comprimido.infolist()
            if len(entradas) > MAXIMO_ENTRADAS_ZIP or sum(e.file_size for e in entradas) > LIMITE_DESCOMPRIMIDO:
                raise ErrorLectura("El archivo descomprimido es demasiado grande.")
    except zipfile.BadZipFile:
        raise ErrorLectura("El archivo no es un Excel (.xlsx) válido.")
    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception:
        raise ErrorLectura("No se pudo abrir el Excel.")
    try:
        hoja = libro.worksheets[0]
        if (hoja.max_row or 0) > MAXIMO_FILAS + 1:
            raise ErrorLectura(f"El archivo tiene más de {MAXIMO_FILAS} filas.")
        if (hoja.max_column or 0) > MAXIMO_COLUMNAS:
            raise ErrorLectura(f"El archivo tiene más de {MAXIMO_COLUMNAS} columnas.")
        filas = []
        for fila in hoja.iter_rows(values_only=True, max_row=MAXIMO_FILAS + 2, max_col=MAXIMO_COLUMNAS + 1):
            if len(fila) > MAXIMO_COLUMNAS and any(v not in (None, "") for v in fila[MAXIMO_COLUMNAS:]):
                raise ErrorLectura(f"El archivo tiene más de {MAXIMO_COLUMNAS} columnas.")
            filas.append([_celda(v) for v in fila[:MAXIMO_COLUMNAS]])
            if len(filas) > MAXIMO_FILAS + 1:
                raise ErrorLectura(f"El archivo tiene más de {MAXIMO_FILAS} filas.")
    except ErrorLectura:
        raise
    except Exception:
        raise ErrorLectura("No se pudo leer el Excel.")
    finally:
        libro.close()
    return _recortar(filas)


def filas_de_csv(contenido):
    if len(contenido) > LIMITE_HOJA:
        raise ErrorLectura("El archivo pasa de 5 MB.")
    if b"\x00" in contenido:
        raise ErrorLectura("El archivo no es un texto CSV.")
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = contenido.decode("latin-1")
    muestra = texto[:8192]
    try:
        separador = csv.Sniffer().sniff(muestra, delimiters=",;\t|").delimiter
    except csv.Error:
        separador = ","
    filas = []
    try:
        for fila in csv.reader(io.StringIO(texto), delimiter=separador):
            if len(fila) > MAXIMO_COLUMNAS:
                raise ErrorLectura(f"El archivo tiene más de {MAXIMO_COLUMNAS} columnas.")
            filas.append([c.strip()[:MAXIMO_CELDA] for c in fila])
            if len(filas) > MAXIMO_FILAS + 1:
                raise ErrorLectura(f"El archivo tiene más de {MAXIMO_FILAS} filas.")
    except csv.Error:
        raise ErrorLectura("El CSV no se pudo leer.")
    return _recortar(filas)


def _recortar(filas):
    filas = [f for f in filas if any(c.strip() for c in f)]
    if not filas:
        raise ErrorLectura("El archivo no tiene datos.")
    ancho = max(len(f) for f in filas)
    return [f + [""] * (ancho - len(f)) for f in filas]


def filas_de_hoja(nombre, contenido):
    if contenido.startswith(b"PK\x03\x04"):
        return filas_de_xlsx(contenido)
    if nombre.lower().endswith((".xlsx", ".xlsm")):
        raise ErrorLectura("El archivo no es un Excel (.xlsx) válido.")
    if contenido.startswith(b"%PDF") or contenido[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise ErrorLectura("Sube un Excel (.xlsx) o un CSV.")
    return filas_de_csv(contenido)


def normal(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", texto.lower()).split())


def fecha(texto):
    valor = str(texto or "").strip()
    if not valor:
        return None
    for patron in (r"^(\d{4})-(\d{1,2})-(\d{1,2})", r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2})$"):
        encontrado = re.match(patron, valor)
        if encontrado:
            a, b, c = (int(x) for x in encontrado.groups())
            anio, mes, dia = (a, b, c) if patron.startswith(r"^(\d{4})") else (c if c > 99 else 2000 + c, b, a)
            try:
                return date(anio, mes, dia)
            except ValueError:
                return None
    encontrado = re.match(r"^(\d{1,2})[/ -]([A-Za-z]{3})[a-z]*\.?[/ -](\d{4})$", valor)
    if encontrado and encontrado.group(2).lower() in MESES:
        try:
            return date(int(encontrado.group(3)), MESES[encontrado.group(2).lower()], int(encontrado.group(1)))
        except ValueError:
            return None
    return None


def importe(texto):
    valor = str(texto or "").strip().replace("$", "").replace(" ", "")
    if not valor:
        return None
    negativo = valor.startswith("(") and valor.endswith(")")
    valor = valor.strip("()")
    if re.fullmatch(r"-?\d+(\.\d+)?", valor) and "." in valor and len(valor.split(".")[1]) > 2:
        valor = f"{float(valor):.2f}"
    try:
        centavos = a_centavos(valor)
    except ErrorImporte:
        return None
    return -centavos if negativo else centavos


def es_fecha(texto):
    return fecha(texto) is not None


def es_importe(texto):
    return importe(texto) is not None and bool(re.search(r"\d", str(texto)))


def detectar_encabezado(filas, sinonimos):
    mejor, puntos_mejor = 0, -1
    for indice, fila in enumerate(filas[:30]):
        puntos = sum(1 for celda in fila if any(normal(celda) == s or normal(celda).startswith(s + " ") for lista in sinonimos.values() for s in lista))
        if puntos > puntos_mejor:
            mejor, puntos_mejor = indice, puntos
    return mejor


def proponer(filas, encabezado, sinonimos, por_contenido=()):
    titulos = [normal(c) for c in filas[encabezado]]
    datos = filas[encabezado + 1: encabezado + 51]
    propuesta = {}
    usadas = set()
    for papel, lista in sinonimos.items():
        for indice, titulo in enumerate(titulos):
            if indice in usadas:
                continue
            if any(titulo == s or titulo.startswith(s + " ") or titulo.endswith(" " + s) for s in lista):
                propuesta[papel] = indice
                usadas.add(indice)
                break
    for papel, prueba in por_contenido:
        if papel in propuesta:
            continue
        for indice in range(len(titulos)):
            if indice in usadas:
                continue
            valores = [f[indice] for f in datos if indice < len(f) and f[indice].strip()]
            if valores and sum(1 for v in valores if prueba(v)) >= max(1, len(valores) * 0.8):
                propuesta[papel] = indice
                usadas.add(indice)
                break
    return propuesta
