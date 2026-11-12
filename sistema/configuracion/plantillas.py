import json

from django.conf import settings
from django.db import transaction

from auditoria.servicios import registrar
from cobros.models import ConceptoCobro
from cuentas.models import PermisoRol, Rol
from cuentas.permisos import PERMISOS
from solicitudes.models import PoliticaAccion
from titulares.models import CampoContacto, MotivoBaja, RelacionContacto

from .models import VOCABULARIO_BASE, Vocabulario


class ErrorPlantilla(ValueError):
    pass


def disponibles():
    carpeta = settings.PLANTILLAS_NEGOCIO
    resultado = {}
    for ruta in sorted(carpeta.glob("*.json")):
        with ruta.open(encoding="utf-8") as archivo:
            datos = json.load(archivo)
        resultado[ruta.stem] = datos.get("nombre", ruta.stem)
    return resultado


def leer(nombre):
    if nombre not in disponibles():
        raise ErrorPlantilla("plantilla desconocida")
    with (settings.PLANTILLAS_NEGOCIO / f"{nombre}.json").open(encoding="utf-8") as archivo:
        return json.load(archivo)


def cargar(nombre, usuario=None):
    datos = leer(nombre)
    with transaction.atomic():
        for clave, texto in datos.get("vocabulario", {}).items():
            if clave in VOCABULARIO_BASE:
                Vocabulario.objects.update_or_create(clave=clave, defaults={"texto": texto})
        for definicion in datos.get("roles", []):
            desconocidos = set(definicion["permisos"]) - set(PERMISOS)
            if desconocidos:
                raise ErrorPlantilla(f"permisos desconocidos: {sorted(desconocidos)}")
            rol, _ = Rol.objects.update_or_create(
                nombre=definicion["nombre"],
                defaults={
                    "nivel": definicion.get("nivel", 1),
                    "minutos_inactividad": definicion.get("minutos_inactividad", 30),
                    "requiere_totp": definicion.get("requiere_totp", False),
                },
            )
            for permiso in definicion["permisos"]:
                PermisoRol.objects.get_or_create(rol=rol, permiso=permiso)
        for definicion in datos.get("politicas", []):
            PoliticaAccion.objects.update_or_create(accion=definicion["accion"], defaults={k: v for k, v in definicion.items() if k != "accion"})
        for motivo in datos.get("motivos_baja", []):
            MotivoBaja.objects.get_or_create(nombre=motivo)
        for relacion in datos.get("relaciones_contacto", []):
            RelacionContacto.objects.get_or_create(nombre=relacion)
        for orden, campo in enumerate(datos.get("campos_contacto", []), start=1):
            if campo.get("principal"):
                CampoContacto.objects.filter(principal=True).exclude(etiqueta=campo["etiqueta"]).update(principal=False)
            CampoContacto.objects.update_or_create(
                etiqueta=campo["etiqueta"],
                defaults={
                    "tipo": campo["tipo"],
                    "obligatorio": campo.get("obligatorio", False),
                    "principal": campo.get("principal", False),
                    "orden": campo.get("orden", orden * 10),
                },
            )
        for definicion in datos.get("conceptos", []):
            ConceptoCobro.objects.get_or_create(
                nombre=definicion["nombre"],
                defaults={
                    "tipo": definicion["tipo"],
                    "periodicidad": definicion.get("periodicidad", ""),
                    "aplica_a": definicion.get("aplica_a", ConceptoCobro.MANUAL),
                    "prioridad": definicion.get("prioridad", 100),
                },
            )
        registrar("plantilla_cargada", usuario=usuario, datos={"plantilla": nombre})
    return datos


def rol_inicial(datos):
    return Rol.objects.get(nombre=datos["rol_inicial"])


def conceptos_con_recargo(datos):
    return {c["nombre"] for c in datos.get("conceptos", []) if c.get("recargo")}
