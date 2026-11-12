from django.conf import settings
from django.db import transaction

from auditoria.servicios import registrar
from configuracion.models import Negocio
from nucleo import matricula as generador

from .models import Contacto, Titular


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
            datos={"matricula": asignada, "conceptos": [c.pk for c in conceptos]},
            request=request,
        )
        if contacto is not None:
            guardar_contacto(usuario, titular, contacto, principal=True, request=request)
    return titular


def guardar_contacto(usuario, titular, datos, contacto=None, principal=None, request=None):
    with transaction.atomic():
        nuevo = contacto is None
        antes = None
        if nuevo:
            contacto = Contacto(titular=titular)
        else:
            antes = {"nombre": contacto.nombre, "relacion": contacto.relacion_id, "valores": dict(contacto.valores), "principal": contacto.principal}
        if principal is None:
            principal = contacto.principal if not nuevo else not Contacto.objects.filter(titular=titular, principal=True).exists()
        if principal:
            Contacto.objects.filter(titular=titular, principal=True).exclude(pk=contacto.pk).update(principal=False)
        contacto.nombre = datos["nombre"]
        contacto.relacion = datos.get("relacion")
        contacto.valores = datos.get("valores", {})
        contacto.principal = principal
        contacto.save()
        despues = {"nombre": contacto.nombre, "relacion": contacto.relacion_id, "valores": dict(contacto.valores), "principal": contacto.principal}
        registrar(
            "contacto_creado" if nuevo else "contacto_editado",
            usuario=usuario,
            objeto=contacto,
            datos={"titular": titular.pk, "antes": antes, "despues": despues},
            request=request,
        )
    return contacto
