from django.conf import settings
from django.db import transaction

from auditoria.servicios import diferencias, registrar
from configuracion.models import Negocio
from nucleo import matricula as generador

from . import contactos
from .models import CampoContacto, Contacto, Titular


def foto_titular(titular):
    return {
        "nombre": titular.nombre,
        "apellidos": titular.apellidos,
        "agrupacion": str(titular.agrupacion) if titular.agrupacion_id else None,
        "notas": titular.notas,
        "estado": titular.get_estado_display(),
        "motivo_baja": str(titular.motivo_baja) if titular.motivo_baja_id else None,
    }


def foto_contacto(contacto):
    foto = {
        "Nombre del contacto": contacto.nombre,
        "Relación": str(contacto.relacion) if contacto.relacion_id else None,
        "Contacto principal": "Sí" if contacto.principal else "No",
    }
    for campo in CampoContacto.objects.all():
        valor = contacto.valor(campo)
        foto[campo.etiqueta] = contactos.mostrar_valor(campo, valor) if valor else None
    return foto


def siguiente_matricula(negocio):
    contador = negocio.contador_matricula
    while True:
        propuesta, contador = generador.generar(
            settings.CLAVE_MATRICULA,
            contador,
            sede=negocio.sede,
            ranuras=negocio.ranuras,
            longitud=negocio.longitud_matricula,
        )
        if not Titular.objects.filter(matricula=propuesta).exists():
            return propuesta, contador


def crear_titular(usuario, datos, contacto=None, conceptos=(), request=None):
    with transaction.atomic():
        negocio = Negocio.objects.get(pk=1)
        asignada, contador = siguiente_matricula(negocio)
        Negocio.objects.filter(pk=1).update(contador_matricula=contador)
        titular = Titular.objects.create(matricula=asignada, creado_por=usuario, estado=Titular.PENDIENTE, **datos)
        if conceptos:
            titular.conceptos_iniciales.set(conceptos)
        registrar(
            "titular_creado",
            usuario=usuario,
            objeto=titular,
            datos={"matricula": asignada, "conceptos": [str(c) for c in conceptos], "cambios": diferencias({}, foto_titular(titular))},
            request=request,
        )
        if contacto is not None:
            guardar_contacto(usuario, titular, contacto, principal=True, request=request)
    return titular


def guardar_contacto(usuario, titular, datos, contacto=None, principal=None, request=None):
    with transaction.atomic():
        nuevo = contacto is None
        if nuevo:
            contacto = Contacto(titular=titular)
            antes = {}
        else:
            antes = foto_contacto(contacto)
        if principal is None:
            principal = contacto.principal if not nuevo else not Contacto.objects.filter(titular=titular, principal=True).exists()
        if principal:
            for otro in Contacto.objects.filter(titular=titular, principal=True).exclude(pk=contacto.pk):
                otro.principal = False
                otro.save(update_fields=["principal", "actualizado"])
                registrar("contacto_editado", usuario=usuario, objeto=otro, datos={"contacto": otro.nombre, "cambios": {"Contacto principal": ["Sí", "No"]}}, request=request)
        contacto.nombre = datos["nombre"]
        contacto.relacion = datos.get("relacion")
        contacto.valores = datos.get("valores", {})
        contacto.principal = principal
        contacto.save()
        cambios = diferencias(antes, foto_contacto(contacto))
        if nuevo or cambios:
            registrar(
                "contacto_creado" if nuevo else "contacto_editado",
                usuario=usuario,
                objeto=contacto,
                datos={"contacto": contacto.nombre, "cambios": cambios},
                request=request,
            )
    return contacto
