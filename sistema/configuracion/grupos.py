import unicodedata

from django.db.models import PROTECT

from tarifas.models import TarifaAgrupacion
from titulares.models import Agrupacion

MAXIMO_GRUPOS = 20


def nombre_limpio(texto):
    return " ".join(str(texto).split())


def clave_de_nombre(texto):
    sin_acentos = "".join(c for c in unicodedata.normalize("NFD", nombre_limpio(texto)) if unicodedata.category(c) != "Mn")
    return sin_acentos.casefold()


def guardar_grupos(nombres):
    existentes = list(Agrupacion.objects.all())
    por_clave = {clave_de_nombre(a.nombre): a for a in existentes}
    ocupados = {a.nombre for a in existentes}
    conservar = []
    for nombre in nombres:
        agrupacion = por_clave.get(clave_de_nombre(nombre))
        if agrupacion is None:
            agrupacion = Agrupacion.objects.create(nombre=nombre)
        else:
            _actualizar(agrupacion, nombre, ocupados)
        conservar.append(agrupacion.pk)
    _retirar_sobrantes(Agrupacion.objects.exclude(pk__in=conservar))


def _actualizar(agrupacion, nombre, ocupados):
    cambios = []
    if not agrupacion.activa:
        agrupacion.activa = True
        cambios.append("activa")
    if agrupacion.nombre != nombre and nombre not in ocupados:
        agrupacion.nombre = nombre
        cambios.append("nombre")
    if cambios:
        agrupacion.save(update_fields=cambios)


def _con_referencias(agrupaciones):
    referidas = set()
    for relacion in Agrupacion._meta.get_fields(include_hidden=True):
        if relacion.auto_created and not relacion.concrete and relacion.on_delete is PROTECT and relacion.related_model is not TarifaAgrupacion:
            columna = relacion.field.attname
            referidas.update(relacion.related_model._base_manager.filter(**{f"{columna}__in": agrupaciones}).values_list(columna, flat=True))
    return referidas


def _retirar_sobrantes(sobrantes):
    referidas = _con_referencias(sobrantes)
    libres = sobrantes.exclude(pk__in=referidas)
    TarifaAgrupacion.objects.filter(agrupacion__in=libres).delete()
    libres.delete()
    Agrupacion.objects.filter(pk__in=referidas).update(activa=False)


def reiniciar_grupos():
    quitar_tarifas()
    libres = Agrupacion.objects.exclude(pk__in=_con_referencias(Agrupacion.objects.all()))
    libres.delete()


def quitar_tarifas():
    TarifaAgrupacion.objects.all().delete()


def guardar_tarifas(importes):
    actuales = {(t.concepto_id, t.agrupacion_id): t for t in TarifaAgrupacion.objects.all()}
    nuevas, cambiadas, quitar = [], [], []
    for (concepto_id, agrupacion_id), centavos in importes.items():
        tarifa = actuales.get((concepto_id, agrupacion_id))
        if centavos is None:
            if tarifa is not None:
                quitar.append(tarifa.pk)
        elif tarifa is None:
            nuevas.append(TarifaAgrupacion(concepto_id=concepto_id, agrupacion_id=agrupacion_id, importe_centavos=centavos))
        else:
            tarifa.importe_centavos, tarifa.activa = centavos, True
            cambiadas.append(tarifa)
    TarifaAgrupacion.objects.filter(pk__in=quitar).delete()
    TarifaAgrupacion.objects.bulk_create(nuevas)
    TarifaAgrupacion.objects.bulk_update(cambiadas, ["importe_centavos", "activa"])
