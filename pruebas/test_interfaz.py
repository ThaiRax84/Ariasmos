import re
from io import BytesIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from auditoria.models import Evento
from caja import comprobantes
from cobros.models import ConceptoCobro
from configuracion import marca
from configuracion.contexto import MAXIMO_VISIBLES
from configuracion.models import MarcaNegocio, Parametro
from inventario import servicios as inventario
from inventario.models import Articulo, Conteo
from proyecto.seguridad import POLITICA_CONTENIDO
from proyecto.version import actual as version_actual
from solicitudes import motor

from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo
from .test_retiros import MALICIOSOS

PLANTILLAS = Path(settings.SISTEMA) / "plantillas_html"
ESTATICOS = Path(settings.SISTEMA) / "estaticos"


def png(ancho=40, alto=20, color=(200, 80, 30)):
    salida = BytesIO()
    Image.new("RGB", (ancho, alto), color).save(salida, format="PNG")
    return salida.getvalue()


def fijar(clave, valor):
    Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})


@pytest.fixture
def limpio():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.parametrize("valor", ["#1F1A4E", "#f58634", "#000000", "#FFFFFF"], ids=["mayusculas", "minusculas", "negro", "blanco"])
def test_colores_validos(valor):
    assert marca.validar_color(valor) == valor.upper()


@pytest.mark.parametrize(
    "valor",
    ["red", "#FFF", "#1234567", "1F1A4E", "#12345G", "#123456\n", " #123456", "#123456;}body{display:none", "url(x)", "", None, 123456, "#１２３４５６"],
    ids=["nombre", "corto", "largo", "sin-gato", "no-hex", "salto", "espacio", "inyeccion", "url", "vacio", "nulo", "numero", "digitos-anchos"],
)
def test_colores_invalidos_se_rechazan(valor):
    with pytest.raises(marca.MarcaInvalida):
        marca.validar_color(valor)


def test_contraste_y_mezcla():
    assert round(marca.contraste("#000000", "#FFFFFF"), 1) == 21.0
    assert round(marca.contraste("#777777", "#777777"), 1) == 1.0
    assert round(marca.contraste("#1F1A4E", "#FFFFFF"), 1) >= 7
    assert marca.contraste("#F58634", "#FFFFFF") < 4.5
    assert marca.mezclar("#000000", 0.5) == "#808080"
    assert marca.mezclar("#F58634", 0.15) == "#FEEDE1"


def test_variables_derivadas_de_un_principal_oscuro():
    valores = marca.variables("#1F1A4E", "#F58634")
    assert valores["--primario"] == valores["--tinta"] == valores["--boton-fondo"] == "#1F1A4E"
    assert valores["--franja"] == valores["--acento"] == "#F58634"
    assert valores["--tinte"] == marca.mezclar("#F58634", 0.15) and valores["--fondo"] == marca.mezclar("#F58634", 0.06)
    assert marca.contraste(valores["--suave"], valores["--fondo"]) >= 4.5


def test_principal_claro_usa_la_tinta_de_ariasmos():
    valores = marca.variables("#F5C542", "#F58634")
    assert valores["--tinta"] == marca.TINTA_ARIASMOS
    assert valores["--boton-fondo"] == marca.TINTA_ARIASMOS
    assert marca.contraste("#FFFFFF", valores["--boton-fondo"]) >= 4.5


def test_marca_solo_la_configura_quien_administra(personas, limpio):
    assert cliente(personas["sup"]).get(reverse("configuracion:marca")).status_code == 403
    assert cliente(personas["op"]).post(reverse("configuracion:marca"), {"accion": "colores", "color_principal": "#1F1A4E", "color_acento": "#F58634"}).status_code == 403
    assert not MarcaNegocio.objects.filter(color_principal="#1F1A4E").exists()
    respuesta = cliente().get(reverse("marca_css"))
    assert respuesta.status_code == 302 and reverse("entrar") in respuesta.url


def test_colores_con_bitacora_y_hoja_sin_inyeccion(personas, limpio):
    c = cliente(personas["dir"])
    respuesta = c.post(reverse("configuracion:marca"), {"accion": "colores", "color_principal": "#1f1a4e", "color_acento": "#F58634"})
    assert respuesta.status_code == 302
    actual = MarcaNegocio.objects.get()
    assert (actual.color_principal, actual.color_acento) == ("#1F1A4E", "#F58634")
    evento = Evento.objects.filter(accion="marca_cambiada").latest("numero")
    assert evento.datos["despues"]["color_principal"] == "#1F1A4E"
    hoja = c.get(reverse("marca_css") + f"?v={actual.version}")
    assert hoja["Content-Type"].startswith("text/css") and hoja["X-Content-Type-Options"] == "nosniff"
    assert "max-age" in hoja["Cache-Control"]
    texto = hoja.content.decode()
    assert "--primario: #1F1A4E;" in texto and "--franja: #F58634;" in texto
    for renglon in texto.strip().splitlines()[1:-1]:
        assert re.fullmatch(r"  --[a-z-]+: #[0-9A-F]{6};", renglon), renglon
    pagina = c.get(reverse("inicio")).content.decode()
    assert f'href="{reverse("marca_css")}?v={actual.version}"' in pagina
    for malo in ("#123456;}body{display:none}", "red", "#12345", "url(javascript:1)"):
        antes = MarcaNegocio.objects.get().version
        respuesta = c.post(reverse("configuracion:marca"), {"accion": "colores", "color_principal": malo, "color_acento": "#F58634"})
        assert respuesta.status_code == 200
        assert MarcaNegocio.objects.get().version == antes
    assert "display:none" not in c.get(reverse("marca_css")).content.decode()


def test_la_cache_de_la_hoja_se_invalida_al_cambiar(personas, limpio):
    marca.guardar_colores("#1F1A4E", "#F58634", personas["dir"])
    primera = marca.hoja(marca.actual())
    assert "#1F1A4E" in primera
    marca.guardar_colores("#2B4A1F", "#C4662E", personas["dir"])
    actual = marca.actual()
    segunda = cliente(personas["op"]).get(reverse("marca_css") + f"?v={actual.version}").content.decode()
    assert "#2B4A1F" in segunda and "#1F1A4E" not in segunda
    vieja = cliente(personas["op"]).get(reverse("marca_css") + f"?v={actual.version - 1}")
    assert vieja["Cache-Control"] == "no-store" and "#2B4A1F" in vieja.content.decode()
    marca.guardar_colores("", "", personas["dir"])
    assert marca.hoja(marca.actual()).strip() == ":root {}"
    assert "marca.css" not in cliente(personas["op"]).get(reverse("inicio")).content.decode()


def test_los_colores_van_juntos(personas, limpio):
    with pytest.raises(marca.MarcaInvalida):
        marca.guardar_colores("#1F1A4E", "", personas["dir"])
    respuesta = cliente(personas["dir"]).post(reverse("configuracion:marca"), {"accion": "colores", "color_principal": "#1F1A4E", "color_acento": ""})
    assert respuesta.status_code == 200 and "los dos colores" in respuesta.content.decode()


def test_logo_se_reconstruye_y_se_entrega_con_nosniff(personas, limpio):
    c = cliente(personas["dir"])
    original = png() + b"<script>alert(1)</script>"
    respuesta = c.post(reverse("configuracion:marca"), {"accion": "logo", "archivo": SimpleUploadedFile("logo.png", original, content_type="image/png")})
    assert respuesta.status_code == 302
    actual = MarcaNegocio.objects.get()
    assert actual.logo.endswith(".png") and actual.logo_tipo == "png"
    assert Path(settings.RUTA_COMPROBANTES, actual.logo).exists()
    assert not str(Path(settings.RUTA_COMPROBANTES)).startswith(str(ESTATICOS))
    entregado = cliente(personas["op"]).get(reverse("marca_logo") + f"?v={actual.version}")
    assert entregado.status_code == 200 and entregado["Content-Type"] == "image/png"
    assert entregado["X-Content-Type-Options"] == "nosniff" and "sandbox" in entregado["Content-Security-Policy"]
    assert b"<script>" not in entregado.content and entregado.content != original
    assert Image.open(BytesIO(entregado.content)).size == (40, 20)
    assert Evento.objects.filter(accion="marca_cambiada", datos__cambio="logo").exists()
    pagina = cliente(personas["op"]).get(reverse("inicio")).content.decode()
    assert f'{reverse("marca_logo")}?v={actual.version}' in pagina
    assert (actual.logo, actual.logo_sha256) in comprobantes.todos()
    c.post(reverse("configuracion:marca"), {"accion": "quitar_logo"})
    assert MarcaNegocio.objects.get().logo == ""
    assert cliente(personas["op"]).get(reverse("marca_logo")).status_code == 404


@pytest.mark.parametrize("nombre", sorted(MALICIOSOS) + ["pdf_valido", "gif"], ids=lambda n: n[:20])
def test_logo_malicioso_se_rechaza(personas, limpio, nombre):
    if nombre == "pdf_valido":
        contenido = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF"
    elif nombre == "gif":
        salida = BytesIO()
        Image.new("RGB", (4, 4)).save(salida, format="GIF")
        contenido = salida.getvalue()
    else:
        contenido = MALICIOSOS[nombre]
    respuesta = cliente(personas["dir"]).post(reverse("configuracion:marca"), {"accion": "logo", "archivo": SimpleUploadedFile("logo.png", contenido, content_type="image/png")})
    assert respuesta.status_code == 200
    assert not MarcaNegocio.objects.exclude(logo="").exists()


def test_logo_de_mas_de_un_mega_se_rechaza(personas, limpio):
    grande = png() + b"\x00" * (1024 * 1024)
    with pytest.raises(marca.MarcaInvalida):
        marca.guardar_logo(grande, personas["dir"])
    respuesta = cliente(personas["dir"]).post(reverse("configuracion:marca"), {"accion": "logo", "archivo": SimpleUploadedFile("logo.png", grande, content_type="image/png")})
    assert "1 MB" in respuesta.content.decode()
    assert not MarcaNegocio.objects.exclude(logo="").exists()


def test_logo_alterado_no_se_entrega(personas, limpio):
    actual = marca.guardar_logo(png(), personas["dir"])
    Path(settings.RUTA_COMPROBANTES, actual.logo).write_bytes(png(color=(0, 0, 0)))
    assert cliente(personas["op"]).get(reverse("marca_logo")).status_code == 404
    assert Evento.objects.filter(accion="logo_alterado").exists()


def test_recibo_lleva_la_marca_del_negocio_y_ariasmos_al_pie(personas, limpio):
    from cobros.models import Pago, Recibo
    from cobros import libro

    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    marca.guardar_logo(png(), personas["dir"])
    libro.registrar_pago(ana, 10000, Pago.BANCO, personas["dir"])
    recibo = Recibo.objects.get()
    pagina = cliente(personas["op"]).get(reverse("cobros:recibo", args=[recibo.pk])).content.decode()
    assert reverse("marca_logo") in pagina and "Hecho con <b>ARIASMOS</b>" in pagina and recibo.codigo in pagina
    pdf = cliente(personas["op"]).get(reverse("cobros:recibo_pdf", args=[recibo.pk]))
    assert pdf.content.startswith(b"%PDF") and b"/Image" in pdf.content


def _ofensas(texto):
    sin_svg = re.sub(r"(?s)<svg.*?</svg>", "", texto)
    ofensas = []
    if re.search(r"<style[\s>]", sin_svg, re.I):
        ofensas.append("etiqueta style")
    if re.search(r"\sstyle\s*=", sin_svg, re.I):
        ofensas.append("atributo style")
    if re.search(r"<script(?![^>]*\ssrc=)[^>]*>", sin_svg, re.I):
        ofensas.append("script en línea")
    if re.search(r"\son[a-z]+\s*=", sin_svg, re.I):
        ofensas.append("manejador on")
    if re.search(r"""(?:src|href|action)\s*=\s*["']?(?:https?:)?//""", texto, re.I):
        ofensas.append("recurso externo")
    if re.search(r"javascript:", texto, re.I):
        ofensas.append("javascript:")
    return ofensas


def test_ninguna_plantilla_lleva_estilos_ni_scripts_en_linea():
    revisadas = 0
    for archivo in PLANTILLAS.rglob("*.html"):
        assert _ofensas(archivo.read_text(encoding="utf-8")) == [], archivo.name
        revisadas += 1
    assert revisadas > 90


def test_estaticos_propios_sin_recursos_de_internet_ni_comentarios():
    for archivo in list(ESTATICOS.rglob("*.css")) + list(ESTATICOS.rglob("*.js")):
        texto = archivo.read_text(encoding="utf-8")
        assert not re.search(r"https?://", texto) and "@import" not in texto, archivo.name
        assert "/*" not in texto and not re.search(r"^\s*//", texto, re.M), archivo.name
    hoja = (ESTATICOS / "css" / "sistema.css").read_text(encoding="utf-8")
    for fuente in ("nunito-latin-400-normal.woff2", "nunito-latin-800-normal.woff2", "cinzel-latin-700-normal.woff2", "metamorphous-latin-400-normal.woff2"):
        assert fuente in hoja and (ESTATICOS / "fuentes" / fuente).exists()
    assert "font-display: swap" in hoja and "prefers-reduced-motion: reduce" in hoja
    transiciones = (ESTATICOS / "css" / "transiciones.css").read_text(encoding="utf-8")
    assert "@view-transition" in transiciones and "prefers-reduced-motion: no-preference" in transiciones


def test_respuestas_sin_estilos_en_linea_y_con_la_politica_intacta(personas, limpio):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    marca.guardar_colores("#1F1A4E", "#F58634", personas["dir"])
    rutas = [reverse("inicio"), reverse("titulares:lista"), reverse("titulares:detalle", args=[ana.pk]), reverse("cobros:buscar"), reverse("cobros:cobrar", args=[ana.pk]), reverse("caja:inicio"), reverse("solicitudes:bandeja"), reverse("cortes:lista")]
    for clave in ("op", "sup", "dir"):
        c = cliente(personas[clave])
        for ruta in rutas + ([reverse("configuracion:indice"), reverse("configuracion:marca"), reverse("usuarios")] if clave == "dir" else []):
            respuesta = c.get(ruta)
            if respuesta.status_code != 200:
                continue
            assert respuesta["Content-Security-Policy"] == POLITICA_CONTENIDO
            assert _ofensas(respuesta.content.decode()) == [], (clave, ruta)
    entrada = cliente().get(reverse("entrar"))
    assert entrada["Content-Security-Policy"] == POLITICA_CONTENIDO and _ofensas(entrada.content.decode()) == []


def _menu(c):
    pagina = c.get(reverse("inicio")).content.decode()
    nav = re.search(r'(?s)<nav class="menu"[^>]*>(.*?)</nav>', pagina).group(1)
    mas = re.search(r'(?s)<div class="menu-mas-panel">(.*?)</div>', nav)
    visibles = re.findall(r">([^<]+)</a>", nav[: mas.start()] if mas else nav)
    ocultas = re.findall(r">([^<]+)</a>", mas.group(1)) if mas else []
    return visibles, ocultas


def test_menu_por_rol(personas):
    voc_titulares = "Alumnos"
    operacion, mas_operacion = _menu(cliente(personas["op"]))
    assert operacion[0] == "Inicio" and "Cobrar" in operacion and voc_titulares in operacion and "Mi caja" in operacion
    assert "Usuarios" not in operacion + mas_operacion and "Configuración" not in operacion + mas_operacion
    direccion, mas_direccion = _menu(cliente(personas["dir"]))
    assert len(direccion) <= MAXIMO_VISIBLES
    for entrada in ("Usuarios", "Roles", "Configuración", "Auditoría", "Respaldos", "Políticas"):
        assert entrada in mas_direccion
    prioridad = ["Inicio", "Cobrar", voc_titulares, "Inventario", "Mi caja", "Banco", "Efectivo", "Solicitudes", "Cortes"]
    posiciones = [prioridad.index(e) for e in direccion]
    assert posiciones == sorted(posiciones)
    supervision, mas_supervision = _menu(cliente(personas["sup"]))
    assert "Más" not in supervision


def test_menu_marca_la_entrada_activa_y_el_mas(personas):
    c = cliente(personas["dir"])
    pagina = c.get(reverse("titulares:lista")).content.decode()
    assert re.search(r'<a href="%s" aria-current="page">' % reverse("titulares:lista"), pagina)
    pagina = c.get(reverse("configuracion:indice")).content.decode()
    assert 'class="menu-mas activo"' in pagina and re.search(r'<a href="%s" aria-current="page">Configuración</a>' % reverse("configuracion:indice"), pagina)


def test_menu_no_pierde_entradas(personas):
    antiguas = {
        "op": {"Inicio", "Alumnos", "Familias", "Cobrar", "Mi caja", "Solicitudes", "Cortes"},
        "dir": {"Inicio", "Alumnos", "Familias", "Usuarios", "Roles", "Configuración", "Respaldos", "Auditoría", "Equipos", "Delegaciones", "Políticas", "Conceptos"},
    }
    for clave, esperadas in antiguas.items():
        visibles, ocultas = _menu(cliente(personas[clave]))
        assert esperadas <= set(visibles) | set(ocultas), clave


def test_splash_una_vez_por_sesion_del_navegador_y_con_la_version(roles, credencial):
    c = cliente(credencial=credencial)
    primera = c.get(reverse("entrar"))
    texto = primera.content.decode()
    assert "data-splash" in texto and "Iniciando el sistema" in texto
    assert f"ver. {version_actual()}" in texto and re.search(r"ver\. \d+\.\d+\.\d+", texto)
    galleta = primera.cookies["splash_visto"]
    assert galleta.value == "1" and not galleta["max-age"] and not galleta["expires"]
    assert galleta["httponly"] and galleta["samesite"] == "Strict"
    assert "data-splash" not in c.get(reverse("entrar")).content.decode()
    nuevo = cliente(credencial=credencial)
    assert "data-splash" in nuevo.get(reverse("entrar")).content.decode()


def test_splash_sigue_la_version_vigente(roles, credencial, settings, tmp_path):
    (tmp_path / "VERSION").write_text("9.8.7\n", encoding="utf-8")
    settings.RAIZ = tmp_path
    texto = cliente(credencial=credencial).get(reverse("entrar")).content.decode()
    assert "ver. 9.8.7" in texto
    plantilla = (PLANTILLAS / "comun" / "_splash.html").read_text(encoding="utf-8")
    assert "ver. {{ version }}" in plantilla and not re.search(r"ver\. \d", plantilla)


def test_splash_se_puede_saltar_y_respeta_reducir_movimiento():
    hoja = (ESTATICOS / "css" / "sistema.css").read_text(encoding="utf-8")
    assert re.search(r"prefers-reduced-motion: reduce\)[^@]*\.splash \{ display: none; \}", hoja)
    codigo = (ESTATICOS / "js" / "sistema.js").read_text(encoding="utf-8")
    assert "prepararSplash" in codigo and '"keydown"' in codigo and '"click"' in codigo


@pytest.fixture
def articulos(personas):
    cache.clear()
    preparar_conceptos()
    fijar("modulo_inventario", 1)
    libros = ConceptoCobro.objects.get(nombre="Libros")
    libro = Articulo.objects.create(clave="LIB-A", nombre="Libro A", precio=35000, concepto=libros)
    cuaderno = Articulo.objects.create(clave="CUA-1", nombre="Cuaderno", precio=5000, concepto=libros)
    lapiz = Articulo.objects.create(clave="LAP-1", nombre="Lapiz", precio=1000, concepto=libros)
    conteo = inventario.subir_conteo({libro.pk: 10, cuaderno.pk: 20, lapiz.pk: 0}, personas["op"], Conteo.PANTALLA)
    motor.aprobar(conteo.solicitud, personas["sup"])
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    return personas, ana, libro, cuaderno, lapiz


def test_quien_vende_ve_existencias_y_nada_en_cero(articulos):
    personas, ana, libro, cuaderno, lapiz = articulos
    pagina = cliente(personas["op"]).get(reverse("inventario:vender_titular", args=[ana.pk])).content.decode()
    assert "Quedan 10" in pagina and "Quedan 20" in pagina
    fila_lapiz = re.search(r"(?s)Lapiz<span.*?</tr>", pagina).group(0)
    assert "Quedan" not in fila_lapiz
    assert "pocas" not in pagina


def test_existencia_baja_al_veinte_por_ciento(articulos):
    personas, ana, libro, cuaderno, lapiz = articulos
    inventario.vender(ana, [(libro.pk, 7)], "adeudo", personas["op"])
    catalogo = {f["articulo"].pk: f for f in inventario.para_vender()}
    assert catalogo[libro.pk]["existencia"] == 3 and not catalogo[libro.pk]["pocas"]
    inventario.vender(ana, [(libro.pk, 1)], "adeudo", personas["op"])
    catalogo = {f["articulo"].pk: f for f in inventario.para_vender()}
    assert catalogo[libro.pk]["existencia"] == 2 and catalogo[libro.pk]["pocas"]
    pagina = cliente(personas["op"]).get(reverse("inventario:vender_titular", args=[ana.pk])).content.decode()
    assert "Quedan 2 · pocas" in pagina
    inicio = cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    assert "existencia baja, quedan 2 de 10" in inicio
    assert "existencia baja" not in cliente(personas["op"]).get(reverse("inicio")).content.decode()
    fijar("porcentaje_existencia_baja", 10)
    catalogo = {f["articulo"].pk: f for f in inventario.para_vender()}
    assert not catalogo[libro.pk]["pocas"]


def test_la_referencia_es_la_ultima_entrada_o_conteo(articulos):
    personas, ana, libro, cuaderno, lapiz = articulos
    inventario.vender(ana, [(cuaderno.pk, 18)], "adeudo", personas["op"])
    assert inventario.niveles_referencia([cuaderno])[cuaderno.pk] == 20
    inventario.registrar_movimiento("entrada", cuaderno, 8, "Compra", "", personas["op"])
    assert inventario.niveles_referencia([cuaderno])[cuaderno.pk] == 10
    assert not {f["articulo"].pk: f for f in inventario.para_vender()}[cuaderno.pk]["pocas"]
    inventario.vender(ana, [(cuaderno.pk, 8)], "adeudo", personas["op"])
    assert {f["articulo"].pk: f for f in inventario.para_vender()}[cuaderno.pk]["pocas"]
    assert inventario.es_baja(5, 0, 5, 20) and not inventario.es_baja(5, 0, 0, 20) and inventario.es_baja(2, 10, 0, 20)


def test_la_lista_para_contar_sigue_sin_existencias(articulos):
    texto = inventario.lista_para_contar()
    texto = texto if isinstance(texto, str) else texto.decode("utf-8-sig")
    assert "10" not in texto and "20" not in texto
