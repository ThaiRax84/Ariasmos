import io
import json
import re
from datetime import timedelta
from html.parser import HTMLParser

import pytest
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from pypdf import PdfReader

from caja import servicios as caja
from cobros import libro
from caja.models import Caja
from cobros.models import Beca, ConceptoCobro, Pago
from configuracion.models import VOCABULARIO_BASE, Vocabulario, hoy_negocio, minuscula, plural, vocabulario
from cortes import servicios as cortes
from cortes.models import Corte
from cuentas.models import Rol
from titulares.models import RelacionContacto

from .conftest import cliente, nuevo_usuario
from .test_permisos import MATRIZ, SOLO_SESION, escenario

INVENTADO = {
    "titular": "Zarpo",
    "titulares": "Zarpos",
    "matricula": "Clave Vex",
    "agrupacion": "Corro",
    "agrupaciones": "Corros",
    "familia": "Clan",
    "familias": "Clanes",
    "padron": "Censo",
    "descuento": "Rebaja",
    "publico": "Mostrador",
}
ROLES_INVENTADOS = {"Operación": "Mesa", "Supervisión": "Vigía", "Dirección": "Mando"}
FABRICA = re.compile(
    r"\b(titular(?:es)?|matr[ií]culas?|agrupaci(?:ó|o)n(?:es)?|familias?|padr(?:ó|o)n(?:es)?|becas?|becad[oa]s?|alumn[oa]s?|descuentos?|p[úu]blico en general)\b",
    re.I,
)
ROLES_FABRICA = re.compile(r"\b(Operación|Supervisión|Dirección)\b")
ATRIBUTOS = ("placeholder", "title", "aria-label", "alt", "data-confirmar")


class Texto(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []
        self.omitir = 0

    def handle_starttag(self, etiqueta, atributos):
        if etiqueta in ("script", "style"):
            self.omitir += 1
        valores = dict(atributos)
        for nombre in ATRIBUTOS:
            if valores.get(nombre):
                self.partes.append(valores[nombre])
        if etiqueta == "input" and valores.get("type") in ("submit", "button") and valores.get("value"):
            self.partes.append(valores["value"])

    def handle_endtag(self, etiqueta):
        if etiqueta in ("script", "style") and self.omitir:
            self.omitir -= 1

    def handle_data(self, datos):
        if not self.omitir:
            self.partes.append(datos)


def visible(respuesta):
    tipo = respuesta.get("Content-Type", "")
    contenido = b"".join(respuesta.streaming_content) if respuesta.streaming else respuesta.content
    if tipo.startswith("application/pdf"):
        lector = PdfReader(io.BytesIO(contenido))
        return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
    if "spreadsheetml" in tipo:
        libro_xlsx = load_workbook(io.BytesIO(contenido), read_only=True)
        return "\n".join(str(celda) for hoja in libro_xlsx.worksheets for fila in hoja.iter_rows(values_only=True) for celda in fila if celda is not None) + "\n" + " ".join(libro_xlsx.sheetnames)
    if tipo.startswith("text/html"):
        lector = Texto()
        lector.feed(contenido.decode("utf-8"))
        return "\n".join(lector.partes)
    texto = contenido.decode("utf-8-sig", errors="replace")
    if tipo.startswith("application/json"):
        return "\n".join(valores_json(json.loads(texto)))
    return texto


def valores_json(dato):
    if isinstance(dato, dict):
        for clave, valor in dato.items():
            if clave not in ("clave", "tipo", "accion", "permisos", "permiso_directo", "permiso_solicitar", "permiso_aprobar"):
                yield from valores_json(valor)
    elif isinstance(dato, list):
        for valor in dato:
            yield from valores_json(valor)
    elif isinstance(dato, str):
        yield dato


IDENTIFICADORES = re.compile(r"\b\w+_\w+\b|\b\w+\.\w+\b|'\w+':")


def encontradas(texto):
    texto = IDENTIFICADORES.sub(" ", texto)
    return sorted({m.group(0) for m in FABRICA.finditer(texto)} | {m.group(0) for m in ROLES_FABRICA.finditer(texto)})


def inventar():
    for clave, texto in INVENTADO.items():
        Vocabulario.objects.update_or_create(clave=clave, defaults={"texto": texto})
    for viejo, nuevo in ROLES_INVENTADOS.items():
        Rol.objects.filter(nombre=viejo).update(nombre=nuevo)
    RelacionContacto.objects.filter(nombre__icontains="alumno").update(nombre="El mismo")


@pytest.fixture
def recorrido(escenario, tmp_path):
    usuarios, argumentos = escenario
    titular = argumentos_titular(argumentos)
    colegiatura = ConceptoCobro.objects.get(nombre="Colegiatura")
    colegiatura.importe_centavos = 250000
    colegiatura.dia_vencimiento = 10
    colegiatura.save()
    Beca.objects.create(titular=titular, concepto=colegiatura, puntos_base=5000, vigente_desde=hoy_negocio(), motivo="prueba", creada_por=usuarios["Supervisión"])
    cajera = nuevo_usuario("cajera", usuarios["Operación"].rol)
    turno = caja.abrir_turno(cajera, Caja.objects.create(nombre="Caja 2"), 0)
    libro.registrar_pago(titular, 20000, Pago.EFECTIVO, cajera, turno=turno)
    caja.cerrar_turno(turno, cajera, {"100000": 1}, nota="conteo de prueba")
    diario = Corte.objects.filter(tipo="diario").first()
    cobranza = cortes.generar_cobranza(usuario=usuarios["Supervisión"])
    inicio = hoy_negocio().replace(day=1) - timedelta(days=1)
    mayores = cortes.generar_mayores(hoy_negocio())
    inventar()
    extras = []
    for corte in [c for c in (diario, cobranza, *mayores) if c is not None]:
        for formato in ("pdf", "csv", "json"):
            extras.append(reverse("cortes:descargar", kwargs={"pk": corte.pk, "formato": formato}))
        extras.append(reverse("cortes:detalle", kwargs={"pk": corte.pk}))
    extras.append(reverse("configuracion:padron_matriculas", kwargs={"pk": argumentos["configuracion:padron_lote"]["pk"], "formato": "xlsx"}))
    return usuarios, argumentos, extras


def argumentos_titular(argumentos):
    from titulares.models import Titular

    return Titular.objects.get(pk=argumentos["titulares:detalle"]["pk"])


def test_formas_derivadas_en_un_solo_lugar(db):
    voc = vocabulario()
    assert voc["matriculas"] == "Matrículas" and voc["matricula_min"] == "matrícula" and voc["titulares_min"] == "titulares"
    assert voc["descuentos"] == "Descuentos" and voc["publico_min"] == "público en general"
    assert plural("Número de cliente") == "Números de cliente" and plural("Padrón") == "Padrones" and plural("RFC") == "RFC"
    assert minuscula("CURP") == "CURP" and minuscula("Folio") == "folio"
    assert set(dict(voc)) == set(VOCABULARIO_BASE)


def test_ninguna_pantalla_pdf_ni_exportacion_usa_el_vocabulario_de_fabrica(recorrido):
    usuarios, argumentos, extras = recorrido
    hallazgos = {}
    rutas = [(nombre, reverse(nombre, kwargs=argumentos.get(nombre))) for nombre in sorted(MATRIZ)]
    rutas += [(nombre, reverse(nombre)) for nombre in sorted(SOLO_SESION - {"salir", "revisar_autorizacion", "aviso_enterado", "marca_logo", "marca_css", "actualizaciones:descargar"})]
    rutas += [(ruta, ruta) for ruta in extras]
    for nombre, url in rutas:
        for rol in ("Operación", "Supervisión", "Dirección"):
            usuarios[rol].refresh_from_db()
            respuesta = cliente(usuarios[rol]).get(url)
            if respuesta.status_code != 200:
                continue
            palabras = encontradas(visible(respuesta))
            if palabras:
                hallazgos.setdefault(nombre, set()).update(palabras)
    assert hallazgos == {}, "\n".join(f"{k}: {sorted(v)}" for k, v in sorted(hallazgos.items()))


def _texto_de_plantilla(contenido):
    sin_etiquetas = re.sub(r"(?s)\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\}", " ", contenido)
    lector = Texto()
    lector.feed(sin_etiquetas)
    return "\n".join(lector.partes)


def test_ninguna_plantilla_de_pantalla_trae_vocabulario_ni_roles_escritos_a_mano():
    from django.conf import settings
    from pathlib import Path

    hallazgos = {}
    for archivo in sorted((Path(settings.SISTEMA) / "plantillas_html").rglob("*.html")):
        palabras = encontradas(_texto_de_plantilla(archivo.read_text(encoding="utf-8")))
        if palabras:
            hallazgos[archivo.name] = palabras
    assert hallazgos == {}


PERMITIDOS_EN_CODIGO = {
    ("configuracion/models.py", "Público en general"),
    ("titulares/padron.py", "nombre del alumno"),
}
ARCHIVOS_DE_DATOS = ("urls.py", "/migrations/", "/management/commands/demostracion.py")


def test_ningun_texto_del_codigo_escribe_a_mano_el_vocabulario_o_un_rol():
    import ast
    from pathlib import Path

    from django.conf import settings

    raiz = Path(settings.SISTEMA)
    hallazgos = []
    for archivo in sorted(raiz.rglob("*.py")):
        relativo = archivo.relative_to(raiz).as_posix()
        if any(parte in "/" + relativo for parte in ARCHIVOS_DE_DATOS):
            continue
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            if not (isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)):
                continue
            texto = nodo.value
            if re.fullmatch(r"[\w:./%<>?()|\\^$-]*", texto) or texto.startswith("SELECT ") or (relativo, texto) in PERMITIDOS_EN_CODIGO:
                continue
            if encontradas(re.sub(r"\{[a-z_]+\}", " ", texto)):
                hallazgos.append(f"{relativo}:{nodo.lineno}: {texto[:80]}")
    assert hallazgos == []
