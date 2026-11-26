import unicodedata

from tarifas.models import TarifaAgrupacion
from titulares.models import Agrupacion

MAXIMO_GRUPOS = 20


def nombre_limpio(texto):
    return " ".join(str(texto).split())


def clave_de_nombre(texto):
    sin_acentos = "".join(c for c in unicodedata.normalize("NFD", nombre_limpio(texto)) if unicodedata.category(c) != "Mn")
    return sin_acentos.casefold()


def guardar_grupos(nombres):
    existentes = {clave_de_nombre(a.nombre): a for a in Agrupacion.objects.all()}
    conservar = []
    for nombre in nombres:
        agrupacion = existentes.get(clave_de_nombre(nombre))
        if agrupacion is None:
            agrupacion = Agrupacion.objects.create(nombre=nombre)
        elif not agrupacion.activa:
            agrupacion.activa = True
            agrupacion.save(update_fields=["activa"])
        conservar.append(agrupacion.pk)
    _retirar_sobrantes(conservar)


def _retirar_sobrantes(conservar):
    sobrantes = Agrupacion.objects.exclude(pk__in=conservar)
    con_titulares = set(sobrantes.filter(titulares__isnull=False).values_list("pk", flat=True))
    sin_titulares = sobrantes.exclude(pk__in=con_titulares)
    TarifaAgrupacion.objects.filter(agrupacion__in=sin_titulares).delete()
    sin_titulares.delete()
    Agrupacion.objects.filter(pk__in=con_titulares).update(activa=False)


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
