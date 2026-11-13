import csv
import hashlib
import json
import re
import unicodedata
from io import BytesIO, StringIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.flowables import Preformatted

from configuracion.moneda import catalogo
from nucleo import dinero
from nucleo.cadena import canonico
from nucleo.exportar import neutralizar

from .models import COMPLETO, SOLO_NOMBRES

TEXTO_LIBRE = {"motivo", "nota", "referencia", "concepto_banco", "descripcion", "importacion", "archivo"}
DINERO = {
    "importe", "importe_pendiente", "ingresos", "esperado", "cobrado_de_lo_esperado", "total_cobrado", "total_devuelto", "fondo_inicial", "contado",
    "diferencia", "efectivo_cobrado_neto", "efectivo_en_custodia", "efectivo_depositado", "efectivo_del_mes", "aplicado_por_banco", "abonos_del_estado_oficial",
    "aplicado_confirmado_por_estado_oficial", "aplicado_sin_confirmar", "importe_por_identificar", "1_30", "31_60", "61_90", "mas_90",
    "total_retirado", "total_regresado", "primer_contado", "efectivo_retirado_neto", "retiros_del_mes",
}
ETIQUETAS = {
    "titular.nombre": "Titular",
    "titular.matricula": "Matrícula",
    "titular.familia": "Familia",
    "contacto.nombre": "Contacto",
    "contacto.relacion": "Relación",
    "contacto.telefono": "Teléfono",
    "contacto.correo": "Correo",
    "pagador.nombre": "Pagador",
}


def filtrar(dato, nivel):
    if isinstance(dato, list):
        return [filtrar(x, nivel) for x in dato]
    if not isinstance(dato, dict):
        return dato
    salida = {}
    for clave, valor in dato.items():
        if clave == "titular" and isinstance(valor, dict):
            if nivel == COMPLETO:
                salida[clave] = dict(valor)
            elif nivel == SOLO_NOMBRES:
                salida[clave] = {"nombre": valor.get("nombre", ""), "familia": valor.get("familia", "")}
            else:
                salida[clave] = {"matricula": valor.get("matricula", "")}
        elif clave == "contacto" and isinstance(valor, dict):
            if nivel == COMPLETO:
                salida[clave] = dict(valor)
        elif clave == "pagador" and isinstance(valor, dict):
            if nivel == COMPLETO:
                salida[clave] = dict(valor)
            elif nivel == SOLO_NOMBRES:
                salida[clave] = {"nombre": valor.get("nombre", "")}
        elif clave in TEXTO_LIBRE:
            if nivel == COMPLETO:
                salida[clave] = valor
        else:
            salida[clave] = filtrar(valor, nivel)
    return salida


def vista(cifras, nivel):
    datos = filtrar(cifras, nivel)
    datos["nivel"] = nivel
    return datos


def _aplanar(fila, prefijo=""):
    plano = {}
    for clave, valor in fila.items():
        nombre = f"{prefijo}{clave}"
        if isinstance(valor, dict):
            plano.update(_aplanar(valor, nombre + "."))
        elif isinstance(valor, list):
            plano[nombre] = "; ".join(str(v) for v in valor)
        else:
            plano[nombre] = valor
    return plano


def etiqueta(clave):
    if clave in ETIQUETAS:
        return ETIQUETAS[clave]
    texto = clave.split(".")[-1].replace("_", " ")
    return texto[:1].upper() + texto[1:]


def _es_dinero(clave, valor):
    return isinstance(valor, int) and not isinstance(valor, bool) and clave.split(".")[-1] in DINERO


def texto_celda(clave, valor, codigo, pdf=False):
    if _es_dinero(clave, valor):
        if pdf:
            moneda = catalogo().get(codigo, {})
            simbolo = moneda.get("simbolo", "")
            try:
                simbolo.encode("cp1252")
            except UnicodeEncodeError:
                simbolo = ""
            return dinero.formatear(valor, simbolo, codigo)
        return dinero.a_texto(valor)
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if valor is None:
        return ""
    return " ".join(str(valor).split())


def tablas(datos):
    resultado = []
    for seccion in datos.get("secciones", []):
        filas = [_aplanar(f) for f in seccion.get("filas", [])]
        columnas = []
        for fila in filas:
            for clave in fila:
                if clave not in columnas:
                    columnas.append(clave)
        resultado.append({"titulo": seccion.get("titulo", ""), "columnas": columnas, "filas": filas})
    return resultado


def resumen(datos):
    plano = {}
    plano.update(_aplanar(datos.get("encabezado", {})))
    plano.update(_aplanar(datos.get("totales", {})))
    return plano


def a_json(datos):
    return (json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=False) + "\n").encode("utf-8")


def a_csv(datos):
    codigo = datos.get("moneda", "")
    salida = StringIO()
    escritor = csv.writer(salida)
    escritor.writerow([neutralizar(datos.get("titulo", "")), neutralizar(f"Moneda: {codigo}"), neutralizar(f"Nivel: {datos.get('nivel', '')}")])
    for clave, valor in resumen(datos).items():
        escritor.writerow([neutralizar(etiqueta(clave)), neutralizar(texto_celda(clave, valor, codigo))])
    for tabla in tablas(datos):
        escritor.writerow([])
        escritor.writerow([neutralizar(tabla["titulo"])])
        escritor.writerow([neutralizar(etiqueta(c)) for c in tabla["columnas"]])
        for fila in tabla["filas"]:
            escritor.writerow([neutralizar(texto_celda(c, fila.get(c), codigo)) for c in tabla["columnas"]])
    return salida.getvalue().encode("utf-8-sig")


def _corto(texto, largo):
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= largo else texto[: largo - 1] + "…"


def a_pdf(datos, negocio=""):
    codigo = datos.get("moneda", "")
    memoria = BytesIO()
    documento = SimpleDocTemplate(memoria, pagesize=landscape(letter), leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm, bottomMargin=10 * mm, title="Corte")
    estilos = getSampleStyleSheet()
    estilo_titulo = estilos["Heading2"]
    estilo_texto = estilos["Code"]
    estilo_texto.fontName = "Helvetica"
    estilo_texto.fontSize = 8
    elementos = [Preformatted(_corto(negocio, 120), estilos["Heading1"]), Preformatted(_corto(f"{datos.get('titulo', '')} · nivel {datos.get('nivel', '')}", 140), estilo_titulo)]
    filas_resumen = [[_corto(etiqueta(k), 60), _corto(texto_celda(k, v, codigo, pdf=True), 90)] for k, v in resumen(datos).items()]
    if filas_resumen:
        tabla = Table(filas_resumen, hAlign="LEFT")
        tabla.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey)]))
        elementos += [tabla, Spacer(1, 4 * mm)]
    for seccion in tablas(datos):
        elementos.append(Preformatted(_corto(seccion["titulo"], 140), estilo_titulo))
        if not seccion["filas"]:
            elementos += [Preformatted("Sin renglones.", estilo_texto), Spacer(1, 3 * mm)]
            continue
        columnas = seccion["columnas"]
        largo = max(8, 200 // max(len(columnas), 1))
        cuerpo = [[_corto(etiqueta(c), largo) for c in columnas]] + [[_corto(texto_celda(c, f.get(c), codigo, pdf=True), largo) for c in columnas] for f in seccion["filas"]]
        tabla = Table(cuerpo, repeatRows=1, hAlign="LEFT")
        tabla.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 6.5),
                    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 6.5),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ]
            )
        )
        elementos += [tabla, Spacer(1, 3 * mm)]
    documento.build(elementos)
    return memoria.getvalue()


def huella(cifras):
    return hashlib.sha256(canonico(cifras).encode("utf-8")).hexdigest()


def saneado(texto, largo=30):
    plano = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii").lower()
    plano = re.sub(r"[^a-z0-9]+", "-", plano).strip("-")
    return plano[:largo].strip("-")


def nombre_base(corte):
    if corte.tipo == "diario":
        caja = saneado(corte.caja.nombre) if corte.caja_id else ""
        return f"corte-diario-{corte.fecha:%Y-%m-%d}-{caja or 'caja'}-{corte.numero}"
    if corte.tipo == "mayor":
        return f"corte-mensual-{corte.fecha:%Y-%m}"
    sufijo = f"-{corte.numero}" if corte.numero > 1 else ""
    return f"cobranza-{corte.fecha:%Y-%m-%d}{sufijo}"
