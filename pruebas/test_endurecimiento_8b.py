import pytest
from django.core.cache import cache
from django.urls import reverse

from configuracion.models import Parametro, Vocabulario, con_vocabulario, descripcion_parametro, vocabulario
from cuentas.models import PermisoRol, Rol
from cuentas.permisos import etiqueta
from respaldos import servicios as respaldos
from titulares.models import LotePadron

from .conftest import cliente, nuevo_usuario

NOMBRES_HOSTILES = ["{titular.__class__.__mro__}", "{x}", "{0}", "{", "}", "{titular.__init__.__globals__}", "{matricula!r:>99999}", "{rol:administrar_usuarios}"]


@pytest.mark.parametrize("nombre", NOMBRES_HOSTILES, ids=range(len(NOMBRES_HOSTILES)))
def test_un_rol_con_llaves_no_rompe_ni_filtra(personas, nombre):
    cache.clear()
    Rol.objects.filter(pk=personas["sup"].rol.pk).update(nombre=nombre[:60])
    c = cliente(personas["dir"])
    for ruta in ("configuracion:parametros", "configuracion:indice", "inicio"):
        respuesta = c.get(reverse(ruta))
        assert respuesta.status_code == 200, ruta
        texto = respuesta.content.decode()
        assert "&lt;class" not in texto and "__globals__" not in texto.replace("{titular.__init__.__globals__}", "")
    for clave in ("umbral_diferencia_arqueo", "dias_retiro_sin_revisar"):
        assert "class 'str'" not in descripcion_parametro(clave)


@pytest.mark.parametrize("texto", ["{titular}", "{matricula.__class__}", "Cli{ente", "{", "{0}", "{familia!r}"])
def test_un_vocabulario_con_llaves_se_muestra_tal_cual(personas, texto):
    cache.clear()
    Vocabulario.objects.update_or_create(clave="matricula", defaults={"texto": texto})
    assert vocabulario()["matricula"] == texto
    assert con_vocabulario("Sin {matricula_min} ni {desconocida} ni {titular.__class__}") == f"Sin {texto.lower()} ni {{desconocida}} ni {{titular.__class__}}"
    assert "class" not in etiqueta("ver_titulares")
    c = cliente(personas["dir"])
    for ruta in ("configuracion:parametros", "inicio", "titulares:lista", "cortes:lista", "solicitudes:bandeja", "configuracion:indice"):
        respuesta = c.get(reverse(ruta))
        assert respuesta.status_code == 200, ruta
        assert "&lt;class" not in respuesta.content.decode()


@pytest.mark.parametrize("clave, valor, esperado", [
    ("respaldos_diarios", "0", 7), ("respaldos_diarios", "-5", 7), ("respaldos_diarios", "3", 7), ("respaldos_diarios", "45", 45), ("respaldos_diarios", "999999", 3650),
    ("respaldos_mensuales", "-1", 0), ("horas_alerta_respaldo", "1000000000", 168), ("horas_alerta_respaldo", "0", 1), ("dias_prueba_restauracion", "1000000000", 180),
])
def test_los_respaldos_tienen_piso_y_techo(personas, clave, valor, esperado):
    Parametro.objects.update_or_create(clave=clave, defaults={"valor": valor})
    funcion = {"respaldos_diarios": respaldos.diarios, "respaldos_mensuales": respaldos.mensuales, "horas_alerta_respaldo": respaldos.horas_alerta, "dias_prueba_restauracion": respaldos.dias_prueba}[clave]
    assert funcion() == esperado


def test_el_lote_de_una_hoja_solo_lo_ve_quien_lo_subio_o_quien_importa_o_aprueba(personas):
    lote = LotePadron.objects.create(nombre_archivo="hoja.csv", sha256="0" * 64, creado_por=personas["dir"])
    rol = Rol.objects.create(nombre="Solo sube hojas", nivel=1)
    PermisoRol.objects.create(rol=rol, permiso="solicitar_importacion_padron")
    ajena = nuevo_usuario("sube_hojas", rol)
    propio = LotePadron.objects.create(nombre_archivo="mia.csv", sha256="1" * 64, creado_por=ajena)
    c = cliente(ajena)
    rutas = [("configuracion:padron_lote", [lote.pk]), ("configuracion:padron_matriculas", [lote.pk, "csv"]), ("configuracion:padron_matriculas", [lote.pk, "xlsx"]), ("configuracion:padron_fichas", [lote.pk])]
    for nombre, argumentos in rutas:
        assert c.get(reverse(nombre, args=argumentos)).status_code == 404, nombre
    assert c.get(reverse("configuracion:padron_lote", args=[propio.pk])).status_code == 200
    for clave in ("dir", "sup"):
        assert cliente(personas[clave]).get(reverse("configuracion:padron_lote", args=[lote.pk])).status_code == 200, clave


def test_del_logo_el_color_mas_oscuro_es_el_principal():
    from io import BytesIO

    from PIL import Image, ImageDraw

    from configuracion import colores_logo, marca

    lienzo = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(lienzo)
    dibujo.rectangle((0, 0, 299, 199), fill=(245, 134, 52, 255))
    dibujo.rectangle((0, 200, 299, 299), fill=(31, 26, 78, 255))
    salida = BytesIO()
    lienzo.save(salida, format="PNG")
    propuesta = colores_logo.proponer(salida.getvalue())
    assert propuesta["origen"] == "logo"
    assert marca.luminancia(propuesta["principal"]) < marca.luminancia(propuesta["acento"])
    rojo, verde, azul = marca.componentes(propuesta["principal"])
    assert azul > rojo and azul > verde
    assert colores_logo.proponer(salida.getvalue()) == propuesta
