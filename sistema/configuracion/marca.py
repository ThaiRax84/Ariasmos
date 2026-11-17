import hashlib
import re
from datetime import timedelta
from io import BytesIO

from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from auditoria.servicios import registrar

from .models import MarcaNegocio

COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
LIMITE_LOGO = 1024 * 1024
LADO_MAXIMO_LOGO = 512
HORAS_ENTRE_AVISOS = 6
BLANCO = "#FFFFFF"
TINTA_ARIASMOS = "#1F1813"
SUAVE_ARIASMOS = "#5C5047"
CONTRASTE_TINTA = 7.0
CONTRASTE_TEXTO = 4.5
PROPORCION_TINTE = 0.15
PROPORCION_FONDO = 0.06
PROPORCION_BORDE = 0.25
PROPORCION_SUAVE = 0.78
CLAVE_CACHE = "marca_css"


class MarcaInvalida(ValueError):
    pass


def validar_color(valor):
    if not isinstance(valor, str) or not COLOR.fullmatch(valor):
        raise MarcaInvalida("Escribe el color como # seguido de seis dígitos hexadecimales, por ejemplo #1F1A4E.")
    return valor.upper()


def componentes(color):
    color = validar_color(color)
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def hexadecimal(rojo, verde, azul):
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in (rojo, verde, azul))


def luminancia(color):
    def canal(valor):
        valor = valor / 255
        return valor / 12.92 if valor <= 0.04045 else ((valor + 0.055) / 1.055) ** 2.4

    rojo, verde, azul = (canal(c) for c in componentes(color))
    return 0.2126 * rojo + 0.7152 * verde + 0.0722 * azul


def contraste(uno, otro):
    claro, oscuro = sorted((luminancia(uno), luminancia(otro)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


def mezclar(color, proporcion, fondo=BLANCO):
    if not 0 <= proporcion <= 1:
        raise MarcaInvalida("Proporción fuera de rango.")
    arriba, abajo = componentes(color), componentes(fondo)
    return hexadecimal(*(a * proporcion + b * (1 - proporcion) for a, b in zip(arriba, abajo)))


def variables(principal, acento):
    principal, acento = validar_color(principal), validar_color(acento)
    fondo = mezclar(acento, PROPORCION_FONDO)
    tinta = principal if contraste(principal, BLANCO) >= CONTRASTE_TINTA else TINTA_ARIASMOS
    suave = SUAVE_ARIASMOS
    if tinta == principal:
        candidato = mezclar(principal, PROPORCION_SUAVE)
        if contraste(candidato, fondo) >= CONTRASTE_TEXTO and contraste(candidato, BLANCO) >= CONTRASTE_TEXTO:
            suave = candidato
    boton = principal if contraste(BLANCO, principal) >= CONTRASTE_TEXTO else tinta
    return {
        "--fondo": fondo,
        "--tinta": tinta,
        "--suave": suave,
        "--primario": principal,
        "--acento": acento,
        "--franja": acento,
        "--borde": mezclar(acento, PROPORCION_BORDE),
        "--tinte": mezclar(acento, PROPORCION_TINTE),
        "--boton-fondo": boton,
        "--boton-texto": BLANCO,
    }


def actual():
    return MarcaNegocio.objects.filter(pk=1).first()


def hoja(marca):
    if marca is None or not marca.con_colores:
        return ":root {}\n"
    clave = f"{CLAVE_CACHE}:{marca.version}"
    guardada = cache.get(clave)
    if guardada is not None:
        return guardada
    valores = variables(marca.color_principal, marca.color_acento)
    lineas = [f"  {nombre}: {validar_color(valor)};" for nombre, valor in valores.items()]
    contenido = ":root {\n" + "\n".join(lineas) + "\n}\n"
    cache.set(clave, contenido, None)
    return contenido


def _obtener_para_cambiar():
    MarcaNegocio.objects.get_or_create(pk=1)
    return MarcaNegocio.objects.select_for_update().get(pk=1)


def _olvidar(version):
    cache.delete(f"{CLAVE_CACHE}:{version}")


def guardar_colores(principal, acento, usuario, request=None):
    principal = (principal or "").strip()
    acento = (acento or "").strip()
    if bool(principal) != bool(acento):
        raise MarcaInvalida("Escribe los dos colores o deja los dos vacíos.")
    if principal:
        principal, acento = validar_color(principal), validar_color(acento)
    with transaction.atomic():
        marca = _obtener_para_cambiar()
        antes = {"color_principal": marca.color_principal, "color_acento": marca.color_acento}
        MarcaNegocio.objects.filter(pk=1).update(color_principal=principal, color_acento=acento, version=F("version") + 1)
        marca.refresh_from_db()
        registrar("marca_cambiada", usuario=usuario, objeto=marca, datos={"cambio": "colores", "antes": antes, "despues": {"color_principal": principal, "color_acento": acento}}, request=request)
    _olvidar(marca.version - 1)
    return marca


def leer_subida(archivo):
    if archivo is None:
        raise MarcaInvalida("Elige el archivo del logo.")
    if archivo.size > LIMITE_LOGO:
        raise MarcaInvalida("El logo pasa de 1 MB.")
    contenido = archivo.read(LIMITE_LOGO + 1)
    if len(contenido) > LIMITE_LOGO:
        raise MarcaInvalida("El logo pasa de 1 MB.")
    return contenido


def preparar_logo(contenido):
    from caja import comprobantes
    from caja.models import ComprobanteRetiro

    if not contenido:
        raise MarcaInvalida("El archivo está vacío.")
    if len(contenido) > LIMITE_LOGO:
        raise MarcaInvalida("El logo pasa de 1 MB.")
    try:
        tipo = comprobantes.tipo_de(contenido)
        if tipo not in (ComprobanteRetiro.JPEG, ComprobanteRetiro.PNG):
            raise MarcaInvalida("El logo debe ser una imagen JPEG o PNG.")
        tipo, limpio = comprobantes.preparar(contenido)
    except comprobantes.ComprobanteInvalido as error:
        raise MarcaInvalida(str(error).replace("Solo se aceptan fotos JPEG o PNG y archivos PDF.", "El logo debe ser una imagen JPEG o PNG.").replace("El comprobante pasa de 5 MB.", "El logo pasa de 1 MB."))
    if tipo not in (ComprobanteRetiro.JPEG, ComprobanteRetiro.PNG):
        raise MarcaInvalida("El logo debe ser una imagen JPEG o PNG.")
    limpio = _reducir(tipo, limpio)
    if len(limpio) > LIMITE_LOGO:
        raise MarcaInvalida("El logo pasa de 1 MB al reconstruirlo; usa una imagen más pequeña.")
    return tipo, limpio


def _reducir(tipo, limpio):
    from PIL import Image

    from caja import comprobantes
    from caja.models import ComprobanteRetiro

    with Image.open(BytesIO(limpio)) as imagen:
        imagen.load()
        if max(imagen.size) <= LADO_MAXIMO_LOGO:
            return limpio
        imagen.thumbnail((LADO_MAXIMO_LOGO, LADO_MAXIMO_LOGO), Image.LANCZOS)
        salida = BytesIO()
        if tipo == ComprobanteRetiro.JPEG:
            comprobantes._solo_pixeles(imagen, "RGB").save(salida, format="JPEG", quality=85)
        else:
            comprobantes._solo_pixeles(imagen, "RGBA" if imagen.mode in ("RGBA", "LA", "P") else "RGB").save(salida, format="PNG")
    return salida.getvalue()


def guardar_logo(contenido, usuario, request=None):
    from caja import comprobantes

    tipo, limpio = preparar_logo(contenido)
    nombre, huella = comprobantes.guardar(tipo, limpio)
    try:
        with transaction.atomic():
            marca = _obtener_para_cambiar()
            antes = {"logo_sha256": marca.logo_sha256}
            anterior = marca.logo
            MarcaNegocio.objects.filter(pk=1).update(logo=nombre, logo_tipo=tipo, logo_sha256=huella, version=F("version") + 1)
            marca.refresh_from_db()
            registrar("marca_cambiada", usuario=usuario, objeto=marca, datos={"cambio": "logo", "antes": antes, "despues": {"logo_sha256": huella, "tipo": tipo, "tamano": len(limpio)}}, request=request)
    except Exception:
        comprobantes.descartar(nombre)
        raise
    _retirar_archivo(anterior)
    _olvidar(marca.version - 1)
    return marca


def _retirar_archivo(nombre):
    from caja import comprobantes

    if nombre and not MarcaNegocio.objects.filter(logo=nombre).exists():
        try:
            comprobantes.descartar(nombre)
        except comprobantes.ComprobanteInvalido:
            pass


def avisar_logo_alterado(marca, request=None):
    from auditoria.models import Evento

    if Evento.objects.filter(accion="logo_alterado", momento__gte=timezone.now() - timedelta(hours=HORAS_ENTRE_AVISOS)).exists():
        return
    registrar("logo_alterado", request=request, objeto=marca, datos={"archivo": marca.logo})


def quitar_logo(usuario, request=None):
    with transaction.atomic():
        marca = _obtener_para_cambiar()
        if not marca.logo:
            raise MarcaInvalida("No hay logo que quitar.")
        antes = {"logo_sha256": marca.logo_sha256}
        anterior = marca.logo
        MarcaNegocio.objects.filter(pk=1).update(logo="", logo_tipo="", logo_sha256="", version=F("version") + 1)
        marca.refresh_from_db()
        registrar("marca_cambiada", usuario=usuario, objeto=marca, datos={"cambio": "logo_quitado", "antes": antes}, request=request)
    _retirar_archivo(anterior)
    _olvidar(marca.version - 1)
    return marca


def leer_logo(marca):
    from caja import comprobantes

    if marca is None or not marca.logo:
        return None
    contenido = comprobantes.ruta_de(marca.logo).read_bytes()
    if hashlib.sha256(contenido).hexdigest() != marca.logo_sha256:
        raise MarcaInvalida("El archivo del logo no coincide con su huella.")
    return contenido
