from collections import namedtuple

from django.db import transaction
from django.utils import timezone

from auditoria.servicios import registrar
from configuracion.models import Parametro, parametro
from titulares import contactos
from titulares.models import Titular

from . import avisos, servicios
from .models import Aviso, PlantillaMensaje

DIAS_DE_LA_SEMANA = (
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
)
FALTAS = {
    "sin_contacto": "Todavía no tiene un contacto principal.",
    "telefono": "Su contacto principal no tiene teléfono.",
    "baja": "Pidió no recibir más mensajes por WhatsApp.",
    "consentimiento": "Todavía no aceptó recibir mensajes por WhatsApp.",
}
Receptor = namedtuple("Receptor", ["titular", "contacto", "falta", "final"])
Fila = namedtuple("Fila", ["aviso", "cuando", "mensaje", "a_quien", "pausa"])


def _mismo_documento(aviso):
    if not avisos.sirve_el_documento(aviso):
        raise ValueError(
            "Ese mensaje no sirve para este aviso: el aviso al registrar un pago lleva el recibo en PDF y los demás no."
        )


def _aprobada(aviso):
    if aviso.plantilla.estado != PlantillaMensaje.APROBADA:
        raise ValueError(
            "Ese mensaje todavía no está aprobado por Meta. Cuando esté «Listo para usar» podrás encender el aviso."
        )


def guardar(aviso, plantilla, dias, agrupaciones, usuario):
    es_pago = aviso.momento == Aviso.PAGO
    aviso.plantilla, aviso.dias = plantilla, 0 if es_pago else dias
    _mismo_documento(aviso)
    if aviso.activo:
        _aprobada(aviso)
    with transaction.atomic():
        if aviso.pk is None:
            _admitir_nuevo(aviso)
        aviso.save()
        aviso.agrupaciones.set([] if es_pago else agrupaciones)
    registrar(
        "aviso_guardado",
        usuario=usuario,
        objeto=aviso,
        datos=_datos(aviso),
    )


def _admitir_nuevo(aviso):
    if Aviso.objects.count() >= Aviso.MAXIMO_DE_AVISOS:
        raise ValueError(f"Solo puede haber {Aviso.MAXIMO_DE_AVISOS} avisos.")
    if aviso.momento == Aviso.PAGO and Aviso.objects.filter(momento=Aviso.PAGO).exists():
        raise ValueError("Ya hay un aviso al registrar un pago. Cámbialo en lugar de agregar otro.")


def _datos(aviso):
    return {
        "momento": aviso.momento,
        "dias": aviso.dias,
        "plantilla": aviso.plantilla.clave,
        "activo": aviso.activo,
    }


def cambiar_activo(aviso, activo, usuario):
    if activo and not aviso.activo:
        _mismo_documento(aviso)
        _aprobada(aviso)
        aviso.activado = timezone.now()
    aviso.activo = activo
    aviso.save()
    registrar("aviso_guardado", usuario=usuario, objeto=aviso, datos=_datos(aviso))


def borrar(aviso, usuario):
    if aviso.momento == Aviso.PAGO:
        raise ValueError("El aviso al registrar un pago no se puede borrar; solo se puede apagar.")
    registrar("aviso_borrado", usuario=usuario, objeto=aviso, datos=_datos(aviso))
    aviso.delete()


def limites():
    return {
        "inicio": avisos.hora_de("avisos_hora_inicio"),
        "fin": avisos.hora_de("avisos_hora_fin"),
        "maximo": parametro("avisos_maximo_semana"),
        "dias_sin_envio": sorted(avisos.dias_sin_envio()),
    }


def guardar_limites(inicio, fin, maximo, dias_sin_envio, usuario):
    nuevos = {
        "avisos_hora_inicio": inicio.strftime("%H:%M"),
        "avisos_hora_fin": fin.strftime("%H:%M"),
        "avisos_maximo_semana": maximo,
        "avisos_dias_sin_envio": ",".join(str(d) for d in sorted(dias_sin_envio)),
    }
    with transaction.atomic():
        for clave, valor in nuevos.items():
            Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})
    registrar("avisos_limites", usuario=usuario, datos=nuevos)


def _cuando(aviso):
    if aviso.momento == Aviso.PAGO:
        return "Al registrar un pago"
    if aviso.momento == Aviso.ANTES:
        return f"{aviso.dias} {'día' if aviso.dias == 1 else 'días'} antes de que venza"
    return "Al primer día de atraso" if aviso.dias == 1 else f"A los {aviso.dias} días de atraso"


def _a_quien(aviso):
    if aviso.momento == Aviso.PAGO:
        return "A quien paga"
    nombres = [a.nombre for a in aviso.agrupaciones.all()]
    if not nombres:
        return "Todos"
    return "Solo " + (", ".join(nombres[:-1]) + " y " + nombres[-1] if len(nombres) > 1 else nombres[0])


def filas():
    lista = Aviso.objects.select_related("plantilla").prefetch_related("agrupaciones")
    return [
        Fila(
            a,
            _cuando(a),
            a.plantilla.nombre + (", con el PDF" if a.plantilla.con_documento else ""),
            _a_quien(a),
            avisos.pausa(a) if a.activo else "",
        )
        for a in lista
    ]


def receptores():
    titulares = list(Titular.objects.filter(estado__in=avisos.ESTADOS))
    principales = contactos.principales(titulares)
    telefono_de = servicios.lector_de_telefonos()
    lista = []
    for titular in titulares:
        contacto = principales[titular.pk]
        numero = telefono_de(contacto) if contacto else ""
        falta = servicios.falta_de(contacto, numero) if contacto else "sin_contacto"
        lista.append(Receptor(titular, contacto, falta, numero[-4:]))
    return lista
