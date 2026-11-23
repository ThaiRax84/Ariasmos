import hashlib
import re
import secrets
from datetime import datetime, time, timedelta, timezone

from django.db import transaction
from django.db.models import F

from nucleo import licencia

from . import ajustes, llave, reloj
from .models import Bitacora, CodigoActivacion, Instalacion, Negocio

ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LARGO_CODIGO = 20
GRUPO_CODIGO = 5
PATRON_CODIGO = re.compile(f"[{ALFABETO}]{{{LARGO_CODIGO}}}")


def anotar(accion, negocio=None, origen="", **datos):
    Bitacora.objects.create(momento=reloj.ahora(), accion=accion, negocio=negocio, origen=origen, datos=datos)


def normalizar(codigo):
    return codigo.upper().replace("-", "").replace(" ", "")


def resumen_de(codigo):
    return hashlib.sha256(normalizar(codigo).encode("utf-8")).hexdigest()


def codigo_valido(codigo):
    return codigo.isascii() and PATRON_CODIGO.fullmatch(normalizar(codigo)) is not None


def pago_al_corriente(negocio):
    return negocio.pagado_hasta is not None and negocio.pagado_hasta >= reloj.ahora().astimezone(timezone.utc).date()


def crear_negocio(nombre, contacto="", plan="base", modulos=(), instalaciones=1):
    if instalaciones < 1:
        raise ValueError("Un negocio necesita al menos una instalación permitida.")
    with transaction.atomic():
        negocio = Negocio.objects.create(nombre=nombre, contacto=contacto, plan=plan, modulos=list(modulos), instalaciones_permitidas=instalaciones)
        anotar("negocio_creado", negocio)
    return negocio


def crear_codigo(negocio):
    crudo = "".join(secrets.choice(ALFABETO) for _ in range(LARGO_CODIGO))
    vence = reloj.ahora() + timedelta(days=ajustes.valor("dias_codigo"))
    with transaction.atomic():
        CodigoActivacion.objects.create(negocio=negocio, resumen=resumen_de(crudo), vence=vence)
        anotar("codigo_creado", negocio, vence=licencia.texto_de(vence))
    return "-".join(crudo[i:i + GRUPO_CODIGO] for i in range(0, LARGO_CODIGO, GRUPO_CODIGO))


def registrar_pago(negocio, hasta):
    with transaction.atomic():
        Negocio.objects.filter(pk=negocio.pk).update(pagado_hasta=hasta)
        negocio.pagado_hasta = hasta
        anotar("pago_registrado", negocio, hasta=hasta.isoformat())


def revocar(negocio, huella=None, deshacer=False):
    with transaction.atomic():
        if huella is None:
            Negocio.objects.filter(pk=negocio.pk).update(revocado=not deshacer)
            negocio.revocado = not deshacer
        elif not Instalacion.objects.filter(negocio=negocio, huella=huella).update(revocada=not deshacer):
            raise LookupError("Ese negocio no tiene una instalación con esa huella.")
        anotar("revocacion_deshecha" if deshacer else "revocacion", negocio, instalacion=huella or "")


def _vencimiento(negocio, emitida):
    vence = emitida + timedelta(days=ajustes.valor("dias_vigencia"))
    if negocio.pagado_hasta is None:
        return vence
    return min(vence, datetime.combine(negocio.pagado_hasta, time(23, 59, 59), tzinfo=timezone.utc))


def emitir(instalacion):
    negocio = instalacion.negocio
    emitida = reloj.ahora().replace(microsecond=0)
    with transaction.atomic():
        Instalacion.objects.filter(pk=instalacion.pk).update(serie=F("serie") + 1)
        instalacion.refresh_from_db(fields=["serie"])
        carga = {
            "formato": licencia.FORMATO,
            "producto": licencia.PRODUCTO,
            "tipo": "licencia",
            "negocio": str(negocio.pk),
            "instalacion": instalacion.huella,
            "plan": negocio.plan,
            "modulos": list(negocio.modulos),
            "serie": instalacion.serie,
            "emitida": licencia.texto_de(emitida),
            "vence": licencia.texto_de(_vencimiento(negocio, emitida)),
            "dias_gracia": ajustes.valor("dias_gracia"),
        }
        anotar("licencia_emitida", negocio, instalacion=instalacion.huella, serie=instalacion.serie, vence=carga["vence"])
    return licencia.firmar(carga, llave.privada())


def revocacion_de(instalacion):
    carga = {
        "formato": licencia.FORMATO,
        "producto": licencia.PRODUCTO,
        "tipo": "revocacion",
        "negocio": str(instalacion.negocio_id),
        "instalacion": instalacion.huella,
        "emitida": licencia.texto_de(reloj.ahora()),
    }
    return licencia.firmar(carga, llave.privada())


def acuse_de(huella, sello):
    carga = {
        "formato": licencia.FORMATO,
        "producto": licencia.PRODUCTO,
        "tipo": "acuse",
        "instalacion": huella,
        "sello": sello,
        "hora": licencia.texto_de(reloj.ahora()),
    }
    return licencia.firmar(carga, llave.privada())
