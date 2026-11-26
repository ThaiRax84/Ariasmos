import hashlib
import re
import unicodedata
import uuid
from datetime import timedelta
from functools import cache

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.urls import reverse

from auditoria.servicios import registrar
from cobros import libro, recibo_pdf
from configuracion.models import Negocio, hoy_negocio, parametro
from configuracion.moneda import formatear
from cuentas.permisos import ve_ingresos
from licencias import reloj
from licencias import servicios as licencias
from nucleo import telefono
from titulares import contactos
from titulares.models import Contacto
from titulares.views import CAPTURA

from . import variables
from .models import Envio, PlantillaMensaje

CLAVE_DEL_RECIBO = "recibo"
PATRON_CLAVE = re.compile(r"[a-z0-9_]{1,40}")
CLAVE_RESERVADA = "nueva"
DIAS_DE_BAJAS = 30
LOTE = 100
LIMITE_PDF = 1_500_000
HORAS_PARA_RESOLVER = 2
NO_DISPONIBLE = "WhatsApp todavía no está disponible: Ariasmos Central no está conectado en este equipo."
ESTADOS_DE_CENTRAL = {
    "en_revision": PlantillaMensaje.EN_REVISION,
    "aprobada": PlantillaMensaje.APROBADA,
    "rechazada": PlantillaMensaje.RECHAZADA,
}
MOTIVOS = {
    "baja": "Esa persona pidió no recibir más mensajes por WhatsApp.",
    "tope": "Se llegó al tope de mensajes de este mes. Un administrador puede subirlo en «Mensajes por WhatsApp».",
    "sin_conexion": "El WhatsApp del negocio todavía no está conectado.",
    "plantilla": "El mensaje del recibo todavía no está aprobado o no se pudo armar.",
    "destino": "El teléfono del contacto no sirve para WhatsApp.",
    "proveedor": "WhatsApp no aceptó el mensaje. Intenta de nuevo en unos minutos.",
}
PAIS = "Este número es de un país al que tu servicio de mensajes no envía. Pide que lo activen."
INCIERTO = "No sabemos si salió. Inténtalo otra vez: no se cobra doble."
CON_REVERSION = "Ese pago fue cancelado: no se manda su recibo por WhatsApp."
PDF_GRANDE = "El recibo en PDF es demasiado grande para mandarlo por WhatsApp."
SIN_RESPUESTA = (
    "No se pudo hablar con Ariasmos Central. Intenta de nuevo en unos minutos."
)


class NoSePuedeEnviar(ValueError):
    def __init__(self, motivo, falta_consentimiento=False):
        super().__init__(motivo)
        self.falta_consentimiento = falta_consentimiento


def disponible():
    return licencias.servicios_disponibles()


def _pedir(accion, datos, adjunto=None):
    estado, respuesta = licencias.pedir(
        "/v1/" + accion.replace("_", "/", 1), accion, datos, adjunto
    )
    return respuesta if estado == 200 else None


def _sincronizar_plantillas(lista):
    if not isinstance(lista, list):
        return
    for central in lista:
        nuevo = (
            ESTADOS_DE_CENTRAL.get(central.get("estado"))
            if isinstance(central, dict)
            else None
        )
        if nuevo is not None:
            PlantillaMensaje.objects.filter(clave=central.get("clave")).exclude(
                estado=PlantillaMensaje.BORRADOR
            ).update(estado=nuevo, motivo=str(central.get("motivo") or "")[:300])


def estado():
    respuesta = _pedir("mensajes_estado", {})
    if respuesta is None:
        return {"disponible": False}
    respuesta.pop("acuse", None)
    _sincronizar_plantillas(respuesta.get("plantillas"))
    return {"disponible": True, **respuesta}


def _validar_plantilla(nombre, texto):
    if not 1 <= len(nombre) <= variables.LARGO_MAXIMO_NOMBRE:
        raise ValueError(
            f"El nombre debe tener de 1 a {variables.LARGO_MAXIMO_NOMBRE} letras."
        )
    if not 1 <= len(texto) <= variables.LARGO_MAXIMO_TEXTO:
        raise ValueError(
            f"El mensaje debe tener de 1 a {variables.LARGO_MAXIMO_TEXTO} letras."
        )
    variables.validar(texto)


def _mandar_a_revision(plantilla):
    respuesta = _pedir(
        "mensajes_plantilla",
        {
            "clave": plantilla.clave,
            "nombre": plantilla.nombre,
            "texto": plantilla.texto,
            "con_documento": plantilla.con_documento,
        },
    )
    resultado = respuesta.get("resultado") if respuesta else None
    if resultado in ESTADOS_DE_CENTRAL:
        return ESTADOS_DE_CENTRAL[resultado], str(respuesta.get("motivo") or "")[:300]
    return (
        PlantillaMensaje.BORRADOR,
        "Todavía no se pudo mandar a revisión. Se guardó como borrador.",
    )


def guardar_plantilla(clave, nombre, texto, usuario):
    nombre, texto = nombre.strip(), texto.strip()
    if PATRON_CLAVE.fullmatch(clave) is None:
        raise ValueError("La clave del mensaje no es válida.")
    _validar_plantilla(nombre, texto)
    plantilla = PlantillaMensaje.objects.filter(
        clave=clave
    ).first() or PlantillaMensaje(clave=clave)
    plantilla.nombre, plantilla.texto = nombre, texto
    plantilla.estado, plantilla.motivo = _mandar_a_revision(plantilla)
    plantilla.save()
    registrar(
        "mensaje_guardado",
        usuario=usuario,
        objeto=plantilla,
        datos={"clave": clave, "estado": plantilla.estado},
    )
    return plantilla


def fijar_tope(tope, usuario):
    respuesta = _pedir("mensajes_tope", {"tope": tope})
    if respuesta is None:
        raise ValueError(NO_DISPONIBLE)
    if respuesta.get("resultado") != "guardado":
        raise ValueError(
            "El tope debe ser un número entre 1 y el máximo que tiene tu plan."
        )
    registrar("mensajes_tope_cambiado", usuario=usuario, datos={"tope": tope})


def lector_de_telefonos():
    campos = [c for c in contactos.campos_activos() if c.tipo == c.TELEFONO]
    prefijo = str(parametro("prefijo_pais_telefono"))
    digitos = parametro("digitos_telefono_nacional")

    def telefono_de(contacto):
        for campo in campos:
            if contacto.valor(campo):
                try:
                    return "+" + telefono.normalizar(
                        contacto.valor(campo), prefijo, digitos
                    )
                except telefono.TelefonoInvalido:
                    return ""
        return ""

    return telefono_de


def _valores_del_recibo(recibo, contacto, usadas):
    resumen = recibo_pdf.resumen(recibo)
    titular, pago = resumen["titular"], resumen["pago"]
    pendientes = cache(lambda: libro.pendientes_de([titular.pk]))

    def dias_de_atraso():
        hoy = hoy_negocio()
        return str(
            max(
                (
                    (hoy - p.vencimiento).days
                    for p in pendientes()
                    if p.vencimiento < hoy
                ),
                default=0,
            )
        )

    valores = {
        "nombre": lambda: contacto.nombre,
        "alumno": lambda: titular.nombre_completo,
        "concepto": lambda: ", ".join(
            dict.fromkeys(a.cargo.concepto.nombre for a in resumen["aplicaciones"])
        ),
        "importe": lambda: formatear(pago.importe),
        "adeudo": lambda: formatear(sum(p.saldo for p in pendientes())),
        "fecha": lambda: libro.fecha_local(pago.fecha).strftime("%d/%m/%Y"),
        "dias": dias_de_atraso,
        "folio": lambda: str(recibo),
        "negocio": lambda: Negocio.actual().nombre,
    }
    return {nombre: valores[nombre]() for nombre in usadas}


def plantilla_del_recibo():
    return PlantillaMensaje.objects.filter(
        clave=CLAVE_DEL_RECIBO, estado=PlantillaMensaje.APROBADA
    ).first()


def _puede_ver(recibo, usuario):
    return ve_ingresos(usuario) or recibo.pago.registrado_por_id == usuario.pk


def _exigir_permisos(recibo, usuario):
    if not usuario.tiene_permiso("enviar_whatsapp") or not _puede_ver(recibo, usuario):
        raise PermissionDenied


def falta_de(contacto, numero):
    if not numero:
        return "telefono"
    if contacto.baja_whatsapp:
        return "baja"
    if not contacto.acepta_whatsapp:
        return "consentimiento"
    return None


FALTAS_DEL_RECIBO = {
    "telefono": "No hay un teléfono en el contacto principal. Agrégalo en su ficha.",
    "baja": "Esa persona pidió no recibir mensajes por WhatsApp.",
    "consentimiento": "Esa persona todavía no aceptó recibir mensajes por WhatsApp. Marca la casilla en su ficha cuando lo acepte.",
}


def _destinatario(recibo):
    contacto = contactos.principal(recibo.pago.titular)
    numero = lector_de_telefonos()(contacto) if contacto else ""
    falta = falta_de(contacto, numero)
    if falta:
        raise NoSePuedeEnviar(
            FALTAS_DEL_RECIBO[falta], falta_consentimiento=falta == "consentimiento"
        )
    return contacto, numero


def _clave_del_envio(recibo, reenviar):
    ultimo = Envio.objects.filter(recibo=recibo).first()
    if ultimo is None:
        return f"recibo-{recibo.pk}-1"
    if reenviar and ultimo.estado in Envio.SIN_ENTREGAR:
        return f"recibo-{recibo.pk}-{Envio.objects.filter(recibo=recibo).count() + 1}"
    return ultimo.clave_envio


def _envio_para(recibo, usuario, contacto, plantilla, numero, reenviar, aviso):
    clave = _clave_del_envio(recibo, reenviar)
    existente = Envio.objects.filter(clave_envio=clave).first()
    if existente is not None:
        reintentable = (Envio.PENDIENTE, Envio.INCIERTO) + (
            (Envio.NO_ENVIADO,) if aviso else ()
        )
        return existente, existente.estado in reintentable
    try:
        return Envio.objects.create(
            clave_envio=clave,
            plantilla=plantilla,
            contacto=contacto,
            titular=recibo.pago.titular,
            recibo=recibo,
            aviso=aviso,
            destino_final=numero[-4:],
            enviado_por=usuario,
        ), True
    except IntegrityError:
        return Envio.objects.get(clave_envio=clave), False


def _fijar_estado(envio, estado, motivo=""):
    Envio.objects.filter(pk=envio.pk).update(estado=estado, motivo=motivo)
    envio.estado, envio.motivo = estado, motivo


def _aplicar_resultado(envio, respuesta):
    if respuesta is None:
        return _fijar_estado(envio, Envio.INCIERTO, INCIERTO)
    resultado = respuesta.get("resultado")
    if resultado in ("aceptado", "repetido"):
        try:
            id_central = uuid.UUID(str(respuesta.get("id")))
        except ValueError:
            return _fijar_estado(envio, Envio.NO_ENVIADO, SIN_RESPUESTA)
        Envio.objects.filter(pk=envio.pk).update(
            id_central=id_central, estado=Envio.ACEPTADO, motivo=""
        )
        envio.id_central, envio.estado, envio.motivo = id_central, Envio.ACEPTADO, ""
        return
    if resultado == "pais":
        envio.delete()
        raise NoSePuedeEnviar(PAIS)
    if resultado == "baja":
        Contacto.objects.filter(pk=envio.contacto_id).update(baja_whatsapp=True)
    _fijar_estado(envio, Envio.NO_ENVIADO, MOTIVOS.get(resultado, SIN_RESPUESTA))


def _pdf_del_recibo(recibo):
    pdf = recibo_pdf.generar(recibo, Negocio.actual())
    if len(pdf) > LIMITE_PDF:
        raise NoSePuedeEnviar(PDF_GRANDE)
    return pdf


def _pedir_el_envio(envio, recibo, plantilla, numero, contacto, pdf):
    textos = {
        nombre: variables.limpiar_valor(valor)
        for nombre, valor in _valores_del_recibo(
            recibo, contacto, variables.usadas(plantilla.texto)
        ).items()
    }
    datos = {
        "clave_envio": envio.clave_envio,
        "plantilla": plantilla.clave,
        "destino": numero,
        "valores": textos,
    }
    if plantilla.con_documento:
        datos["adjunto_sha256"] = hashlib.sha256(pdf).hexdigest()
    _aplicar_resultado(
        envio,
        _pedir("mensajes_enviar", datos, pdf if plantilla.con_documento else None),
    )


def enviar_recibo(recibo, usuario, reenviar=False):
    _exigir_permisos(recibo, usuario)
    return mandar_recibo(recibo, usuario, plantilla_del_recibo(), reenviar)


def mandar_recibo(recibo, usuario, plantilla, reenviar=False, aviso=None):
    if not disponible() or plantilla is None:
        raise NoSePuedeEnviar(NO_DISPONIBLE)
    if hasattr(recibo.pago, "reversion"):
        raise NoSePuedeEnviar(CON_REVERSION)
    contacto, numero = _destinatario(recibo)
    pdf = _pdf_del_recibo(recibo)
    envio, por_pedir = _envio_para(
        recibo, usuario, contacto, plantilla, numero, reenviar, aviso
    )
    if por_pedir:
        _pedir_el_envio(envio, recibo, plantilla, numero, contacto, pdf)
        registrar(
            "whatsapp_enviado",
            usuario=usuario,
            objeto=envio,
            titular=envio.titular_id,
            datos={
                "recibo": str(recibo),
                "plantilla": plantilla.clave,
                "destino_final": envio.destino_final,
                "estado": envio.estado,
            },
        )
    return envio


def enlace_al_consentimiento(contacto, usuario):
    if contacto is None or not any(usuario.tiene_permiso(p) for p in CAPTURA):
        return ""
    if contacto.titular_id:
        return reverse(
            "titulares:contacto_editar", args=[contacto.titular_id, contacto.pk]
        )
    return reverse(
        "titulares:familia_contacto_editar", args=[contacto.familia_id, contacto.pk]
    )


def situacion_del_recibo(recibo, usuario):
    plantilla = plantilla_del_recibo()
    if (
        plantilla is None
        or not disponible()
        or not usuario.tiene_permiso("enviar_whatsapp")
        or recibo.pago.titular.interno
        or hasattr(recibo.pago, "reversion")
    ):
        return None
    ultimo = Envio.objects.filter(recibo=recibo).first()
    try:
        contacto, numero = _destinatario(recibo)
    except NoSePuedeEnviar as aviso:
        enlace = (
            enlace_al_consentimiento(contactos.principal(recibo.pago.titular), usuario)
            if aviso.falta_consentimiento
            else ""
        )
        return {"aviso": str(aviso), "pedir_permiso": enlace, "ultimo": ultimo}
    return {
        "contacto": contacto,
        "final": numero[-4:],
        "ultimo": ultimo,
        "reintentar": ultimo is not None
        and ultimo.estado in Envio.SIN_ENTREGAR + (Envio.INCIERTO,),
    }


def _marcar_bajas(claves):
    ids = list(
        Contacto.objects.filter(
            pk__in=Envio.objects.filter(clave_envio__in=claves).values("contacto_id"),
            baja_whatsapp=False,
        ).values_list("pk", flat=True)
    )
    Contacto.objects.filter(pk__in=ids).update(baja_whatsapp=True)
    for pk in ids:
        registrar("whatsapp_baja", datos={"contacto": pk})


def _marcar_altas(claves):
    Contacto.objects.filter(
        pk__in=Envio.objects.filter(clave_envio__in=claves).values("contacto_id"),
        baja_whatsapp=True,
    ).update(baja_whatsapp=False)


def _actualizar_envios(respuesta):
    nuevos = {
        fila.get("id"): fila
        for fila in respuesta.get("mensajes", [])
        if isinstance(fila, dict)
    }
    cambiados = 0
    for envio in Envio.objects.filter(
        estado__in=Envio.EN_CURSO, id_central__isnull=False
    ):
        fila = nuevos.get(str(envio.id_central))
        if (
            fila is not None
            and fila.get("estado") in Envio.AVANCES
            and fila["estado"] != envio.estado
        ):
            motivo = (
                f"No se pudo entregar el mensaje (código {fila.get('error') or 'desconocido'})."
                if fila["estado"] == Envio.FALLIDO
                else ""
            )
            _fijar_estado(envio, fila["estado"], motivo)
            cambiados += 1
    return cambiados


def _resolver_incierto(envio):
    if envio.cargo_id:
        from . import avisos

        return avisos.reintentar(envio)
    try:
        contacto, numero = _destinatario(envio.recibo)
        pdf = _pdf_del_recibo(envio.recibo)
        _pedir_el_envio(envio, envio.recibo, envio.plantilla, numero, contacto, pdf)
    except NoSePuedeEnviar as aviso:
        Envio.objects.filter(pk=envio.pk).update(
            estado=Envio.NO_ENVIADO, motivo=str(aviso)
        )


def _resolver_inciertos():
    desde = reloj.ahora() - timedelta(hours=HORAS_PARA_RESOLVER)
    for envio in Envio.objects.filter(
        estado=Envio.INCIERTO,
        creado__gte=desde,
        plantilla__estado=PlantillaMensaje.APROBADA,
    ).select_related("recibo__pago", "plantilla")[:LOTE]:
        _resolver_incierto(envio)


def actualizar_estados():
    if not disponible():
        return 0
    _resolver_inciertos()
    if PlantillaMensaje.objects.filter(estado=PlantillaMensaje.EN_REVISION).exists():
        estado()
    en_curso = list(
        Envio.objects.filter(estado__in=Envio.EN_CURSO, id_central__isnull=False)
        .order_by("creado")
        .values_list("id_central", flat=True)[:LOTE]
    )
    desde = reloj.ahora() - timedelta(days=DIAS_DE_BAJAS)
    if not en_curso and not Envio.objects.filter(creado__gte=desde).exists():
        return 0
    respuesta = _pedir("mensajes_consultar", {"ids": [str(i) for i in en_curso]})
    if respuesta is None:
        return 0
    for clave, marcar in (("bajas", _marcar_bajas), ("altas", _marcar_altas)):
        marcar([c for c in respuesta.get(clave, []) if isinstance(c, str)])
    return _actualizar_envios(respuesta)


def clave_para(nombre):
    base = (
        re.sub(
            r"[^a-z0-9]+",
            "_",
            unicodedata.normalize("NFKD", nombre)
            .encode("ascii", "ignore")
            .decode()
            .lower(),
        ).strip("_")[:30]
        or "mensaje"
    )
    if base == CLAVE_RESERVADA:
        base = "mensaje_nuevo"
    clave, numero = base, 1
    while PlantillaMensaje.objects.filter(clave=clave).exists():
        numero += 1
        clave = f"{base}_{numero}"
    return clave
