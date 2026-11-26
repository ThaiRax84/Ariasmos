import hashlib
import re
import unicodedata
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction

from emision import reloj
from emision.servicios import anotar

from . import plantillas, proveedores, secretos
from .models import (
    Alta,
    Baja,
    Cuota,
    Documento,
    Mensaje,
    Plantilla,
    Remitente,
)
from .proveedores import FalloProveedor

HORAS_DEL_DOCUMENTO = 2
DIAS_DE_BAJAS = 30
LIMITE_ADJUNTO = 1_500_000
LARGO_VALOR = 200
PATRON_CLAVE = re.compile(r"[a-z0-9_]{1,40}")
PATRON_CLAVE_ENVIO = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
PATRON_DESTINO = re.compile(r"\+[0-9]{10,15}")
PATRON_SHA256 = re.compile(r"[0-9a-f]{64}")
PALABRAS_DE_BAJA = ("BAJA", "STOP", "ALTO")
PALABRA_DE_ALTA = "ALTA"
ESTADOS_DE_TWILIO = {
    "sent": Mensaje.ENVIADO,
    "delivered": Mensaje.ENTREGADO,
    "read": Mensaje.LEIDO,
    "failed": Mensaje.FALLIDO,
    "undelivered": Mensaje.FALLIDO,
}
DESDE = {
    Mensaje.ENVIADO: (Mensaje.ACEPTADO,),
    Mensaje.ENTREGADO: (Mensaje.ACEPTADO, Mensaje.ENVIADO),
    Mensaje.LEIDO: (Mensaje.ACEPTADO, Mensaje.ENVIADO, Mensaje.ENTREGADO),
    Mensaje.FALLIDO: (Mensaje.ACEPTADO, Mensaje.ENVIADO),
}
TERMINADOS = (Mensaje.ENTREGADO, Mensaje.LEIDO, Mensaje.FALLIDO)


class DatosInvalidos(Exception):
    pass


def _remitente(negocio):
    return Remitente.objects.filter(negocio=negocio, activo=True).first()


def cuota_de(negocio):
    return Cuota.objects.get_or_create(negocio=negocio)[0]


def enviados_del_mes(negocio):
    inicio = reloj.ahora().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (
        Mensaje.objects.filter(negocio=negocio, creado__gte=inicio)
        .exclude(estado=Mensaje.FALLIDO)
        .count()
    )


def purgar_documentos():
    Documento.objects.filter(vence__lte=reloj.ahora()).delete()


def _refrescar_plantillas(remitente):
    proveedor = proveedores.activo()
    for plantilla in Plantilla.objects.filter(
        negocio=remitente.negocio_id, estado=Plantilla.EN_REVISION
    ).exclude(id_proveedor=""):
        try:
            estado, motivo = proveedor.estado_plantilla(remitente, plantilla)
        except FalloProveedor:
            continue
        Plantilla.objects.filter(pk=plantilla.pk).update(estado=estado, motivo=motivo)


def estado(negocio):
    remitente = _remitente(negocio)
    if remitente is not None:
        _refrescar_plantillas(remitente)
    cuota = cuota_de(negocio)
    lista = Plantilla.objects.filter(negocio=negocio).order_by("clave")
    return {
        "conectado": remitente is not None,
        "numero_final": remitente.numero[-4:] if remitente else "",
        "plantillas": list(
            lista.values(
                "clave", "nombre", "texto", "con_documento", "estado", "motivo"
            )
        ),
        "enviados_mes": enviados_del_mes(negocio),
        "tope": cuota.tope,
        "tope_maximo": cuota.tope_maximo,
        "paises": cuota.paises,
    }


def _plantilla_nueva(negocio, datos):
    if (
        PATRON_CLAVE.fullmatch(datos["clave"]) is None
        or not 1 <= len(datos["nombre"]) <= 80
        or not 1 <= len(datos["texto"]) <= 900
        or "{" in datos["texto"]
        or "}" in datos["texto"]
    ):
        raise DatosInvalidos("plantilla")
    plantilla = Plantilla.objects.filter(
        negocio=negocio, clave=datos["clave"]
    ).first() or Plantilla(negocio=negocio, clave=datos["clave"])
    plantilla.nombre = datos["nombre"]
    plantilla.texto = datos["texto"]
    plantilla.con_documento = datos["con_documento"]
    plantilla.variables = plantillas.variables_de(datos["texto"])
    return plantilla


def guardar_plantilla(negocio, datos):
    plantilla = _plantilla_nueva(negocio, datos)
    remitente = _remitente(negocio)
    if remitente is None:
        return {
            "resultado": "sin_conexion",
            "motivo": "El negocio no tiene WhatsApp conectado.",
        }
    try:
        id_proveedor, estado_nuevo, motivo = proveedores.activo().crear_plantilla(
            remitente, plantilla
        )
    except FalloProveedor as fallo:
        return {"resultado": "sin_conexion", "motivo": fallo.motivo[:300]}
    plantilla.id_proveedor, plantilla.estado, plantilla.motivo = (
        id_proveedor,
        estado_nuevo,
        motivo[:300],
    )
    plantilla.save()
    anotar("plantilla_enviada", negocio, clave=plantilla.clave, estado=estado_nuevo)
    return {"resultado": estado_nuevo, "motivo": plantilla.motivo}


def fijar_tope(negocio, tope):
    cuota = cuota_de(negocio)
    if not 1 <= tope <= cuota.tope_maximo:
        return {"resultado": "fuera_de_rango"}
    Cuota.objects.filter(pk=cuota.pk).update(tope=tope)
    anotar("tope_cambiado", negocio, tope=tope)
    return {"resultado": "guardado"}


def _respuesta(resultado, mensaje_id=""):
    return {"resultado": resultado, "id": str(mensaje_id)}


def _valor_limpio(valor):
    return (
        bool(valor.strip())
        and len(valor) <= LARGO_VALOR
        and "     " not in valor
        and not set(valor) & set("{}")
        and not any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in valor)
    )


def _valores_validos(plantilla, valores):
    return set(valores) == set(plantilla.variables) and all(
        _valor_limpio(valor) for valor in valores.values()
    )


def _validar_adjunto(plantilla, datos, adjunto):
    if not plantilla.con_documento:
        if adjunto is not None:
            raise DatosInvalidos("adjunto_sobra")
        return
    if (
        adjunto is None
        or len(adjunto) > LIMITE_ADJUNTO
        or not adjunto.startswith(b"%PDF-")
        or hashlib.sha256(adjunto).hexdigest() != datos.get("adjunto_sha256")
    ):
        raise DatosInvalidos("adjunto")


def _registrar(instalacion, plantilla, datos, destino, adjunto):
    negocio = instalacion.negocio
    with transaction.atomic():
        if enviados_del_mes(negocio) >= cuota_de(negocio).tope:
            return None
        _validar_adjunto(plantilla, datos, adjunto)
        mensaje = Mensaje.objects.create(
            negocio=negocio,
            instalacion=instalacion,
            plantilla=plantilla,
            clave_envio=datos["clave_envio"],
            destino_final=destino[-4:],
            destino_resumen=secretos.resumen_de_numero(destino),
        )
        if plantilla.con_documento:
            Documento.objects.create(
                mensaje=mensaje,
                contenido=adjunto,
                vence=reloj.ahora() + timedelta(hours=HORAS_DEL_DOCUMENTO),
            )
    return mensaje


def _cambiar_estado(mensaje, nuevo, error=""):
    Mensaje.objects.filter(pk=mensaje.pk).update(
        estado=nuevo, error=error[:200], actualizado=reloj.ahora()
    )
    if nuevo in TERMINADOS:
        Documento.objects.filter(mensaje=mensaje).delete()


def _entregar_al_proveedor(remitente, mensaje, plantilla, destino, datos):
    documento = Documento.objects.filter(mensaje=mensaje).first()
    url_documento = (
        f"{settings.URL_PUBLICA}/v1/documentos/{documento.token}.pdf"
        if documento
        else ""
    )
    url_estado = f"{settings.URL_PUBLICA}/v1/twilio/estado/{mensaje.pk}"
    try:
        id_proveedor = proveedores.activo().enviar(
            remitente, plantilla, destino, datos["valores"], url_documento, url_estado
        )
    except FalloProveedor as fallo:
        _cambiar_estado(mensaje, Mensaje.FALLIDO, fallo.motivo)
        return _respuesta("proveedor", mensaje.pk)
    Mensaje.objects.filter(pk=mensaje.pk).update(id_proveedor=id_proveedor[:64])
    return _respuesta("aceptado", mensaje.pk)


def _repetido(instalacion, datos):
    previo = (
        Mensaje.objects.filter(
            negocio=instalacion.negocio,
            instalacion=instalacion,
            clave_envio=datos["clave_envio"],
        )
        .values_list("pk", flat=True)
        .first()
    )
    return None if previo is None else _respuesta("repetido", previo)


def enviar(instalacion, datos, adjunto):
    negocio = instalacion.negocio
    purgar_documentos()
    remitente = _remitente(negocio)
    if remitente is None:
        return _respuesta("sin_conexion")
    destino = secretos.normalizar_numero(datos["destino"])
    if (repetido := _repetido(instalacion, datos)) is not None:
        return repetido
    plantilla = Plantilla.objects.filter(
        negocio=negocio, clave=datos["plantilla"], estado=Plantilla.APROBADA
    ).first()
    if plantilla is None or not _valores_validos(plantilla, datos["valores"]):
        return _respuesta("plantilla")
    if PATRON_DESTINO.fullmatch(destino) is None:
        return _respuesta("destino")
    if not any(destino.startswith(f"+{p}") for p in cuota_de(negocio).paises):
        return _respuesta("pais")
    if Baja.objects.filter(
        negocio=negocio, resumen=secretos.resumen_de_numero(destino)
    ).exists():
        return _respuesta("baja")
    try:
        mensaje = _registrar(instalacion, plantilla, datos, destino, adjunto)
    except IntegrityError:
        return _repetido(instalacion, datos)
    if mensaje is None:
        return _respuesta("tope")
    return _entregar_al_proveedor(remitente, mensaje, plantilla, destino, datos)


def consultar(instalacion, ids):
    desde = reloj.ahora() - timedelta(days=DIAS_DE_BAJAS)
    propios = Mensaje.objects.filter(
        negocio=instalacion.negocio, instalacion=instalacion
    )
    bajas = Baja.objects.filter(negocio=instalacion.negocio).values("resumen")
    altas = Alta.objects.filter(negocio=instalacion.negocio, momento__gte=desde).values(
        "resumen"
    )
    return {
        "mensajes": [
            {"id": str(fila["id"]), "estado": fila["estado"], "error": fila["error"]}
            for fila in propios.filter(pk__in=ids).values("id", "estado", "error")
        ],
        "bajas": list(
            propios.filter(creado__gte=desde, destino_resumen__in=bajas).values_list(
                "clave_envio", flat=True
            )
        ),
        "altas": list(
            propios.filter(creado__gte=desde, destino_resumen__in=altas).values_list(
                "clave_envio", flat=True
            )
        ),
    }


def aplicar_estado(mensaje, estado_twilio, codigo_error):
    nuevo = ESTADOS_DE_TWILIO.get(estado_twilio)
    if nuevo is None:
        return
    error = codigo_error if nuevo == Mensaje.FALLIDO else ""
    with transaction.atomic():
        cambiados = Mensaje.objects.filter(
            pk=mensaje.pk, estado__in=DESDE[nuevo]
        ).update(estado=nuevo, error=error[:200], actualizado=reloj.ahora())
        if cambiados and nuevo in TERMINADOS:
            Documento.objects.filter(mensaje=mensaje).delete()


def _palabra(cuerpo):
    sin_acentos = unicodedata.normalize("NFKD", cuerpo.strip().upper())
    return "".join(c for c in sin_acentos if not unicodedata.combining(c))


def aplicar_entrante(negocio, origen, cuerpo):
    numero = secretos.normalizar_numero(origen.removeprefix("whatsapp:"))
    if PATRON_DESTINO.fullmatch(numero) is None:
        return
    resumen = secretos.resumen_de_numero(numero)
    palabra = _palabra(cuerpo)
    if palabra in PALABRAS_DE_BAJA:
        Alta.objects.filter(negocio=negocio, resumen=resumen).delete()
        _, nueva = Baja.objects.get_or_create(negocio=negocio, resumen=resumen)
        if nueva:
            anotar("baja_whatsapp", negocio)
    elif palabra == PALABRA_DE_ALTA:
        borradas, _ = Baja.objects.filter(negocio=negocio, resumen=resumen).delete()
        if borradas:
            Alta.objects.update_or_create(
                negocio=negocio, resumen=resumen, defaults={"momento": reloj.ahora()}
            )
            anotar("alta_whatsapp", negocio)
