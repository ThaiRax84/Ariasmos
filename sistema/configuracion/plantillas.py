import json

from django.conf import settings
from django.db import transaction

from auditoria.servicios import registrar
from banco.models import MedioPago
from caja.models import Caja, Denominacion
from cobros.models import ConceptoCobro
from cortes.models import DefinicionCorte
from cuentas.models import PermisoRol, Rol
from cuentas.permisos import INDISPENSABLES
from solicitudes.models import PoliticaAccion
from titulares.models import CampoContacto, MotivoBaja, RelacionContacto

from . import esquema, moneda
from .models import VOCABULARIO_BASE, Negocio, Vocabulario, vocabulario

ErrorPlantilla = esquema.PlantillaInvalida


def _archivos():
    return {ruta.stem: ruta for ruta in sorted(settings.PLANTILLAS_NEGOCIO.glob("*.json")) if ruta.stem.isidentifier()}


def disponibles():
    resultado = {}
    for nombre, ruta in _archivos().items():
        try:
            resultado[nombre] = esquema.desde_bytes(ruta.read_bytes())["nombre"]
        except esquema.PlantillaInvalida:
            continue
    return resultado


def leer(nombre):
    ruta = _archivos().get(nombre)
    if ruta is None:
        raise ErrorPlantilla("plantilla desconocida")
    return esquema.desde_bytes(ruta.read_bytes())


def cargar(nombre, usuario=None):
    return cargar_datos(leer(nombre), nombre, usuario)


def cargar_datos(datos, origen, usuario=None, request=None):
    datos = esquema.validar(datos)
    with transaction.atomic():
        for clave, texto in datos["vocabulario"].items():
            Vocabulario.objects.update_or_create(clave=clave, defaults={"texto": texto})
        for definicion in datos["roles"]:
            rol, _ = Rol.objects.update_or_create(
                nombre=definicion["nombre"],
                defaults={"nivel": definicion["nivel"], "minutos_inactividad": definicion["minutos_inactividad"], "requiere_totp": definicion["requiere_totp"]},
            )
            for permiso in definicion["permisos"]:
                PermisoRol.objects.get_or_create(rol=rol, permiso=permiso)
        for definicion in datos["politicas"]:
            PoliticaAccion.objects.update_or_create(accion=definicion["accion"], defaults={k: v for k, v in definicion.items() if k != "accion"})
        for motivo in datos["motivos_baja"]:
            MotivoBaja.objects.get_or_create(nombre=motivo)
        for relacion in datos["relaciones_contacto"]:
            RelacionContacto.objects.get_or_create(nombre=relacion)
        for nombre in datos["cajas"]:
            Caja.objects.get_or_create(nombre=nombre)
        negocio = Negocio.actual()
        if datos["moneda"] == (negocio.moneda if negocio else moneda.POR_DEFECTO):
            for valor in datos["denominaciones"]:
                Denominacion.objects.get_or_create(valor=valor)
        for definicion in datos["cortes"]:
            DefinicionCorte.objects.update_or_create(tipo=definicion["tipo"], defaults={"nombre": definicion["nombre"], "nivel": definicion["nivel"], "activa": definicion["activa"]})
        for orden, medio in enumerate(datos["medios_pago"], start=1):
            MedioPago.objects.get_or_create(nombre=medio, defaults={"orden": orden * 10})
        for campo in datos["campos_contacto"]:
            if campo["principal"]:
                CampoContacto.objects.filter(principal=True).exclude(etiqueta=campo["etiqueta"]).update(principal=False)
            CampoContacto.objects.update_or_create(etiqueta=campo["etiqueta"], defaults={k: v for k, v in campo.items() if k != "etiqueta"})
        for definicion in datos["conceptos"]:
            ConceptoCobro.objects.get_or_create(
                nombre=definicion["nombre"],
                defaults={"tipo": definicion["tipo"], "periodicidad": definicion["periodicidad"], "aplica_a": definicion["aplica_a"], "prioridad": definicion["prioridad"]},
            )
        registrar("plantilla_cargada", usuario=usuario, datos={"plantilla": origen, "nombre": datos["nombre"]}, request=request)
    return datos


def rol_inicial(datos):
    return Rol.objects.get(nombre=datos["rol_inicial"])


def recargos(datos):
    return {c["nombre"]: c["recargo"] for c in datos["conceptos"] if c["recargo"]}


def exportar():
    roles = list(Rol.objects.prefetch_related("asignaciones").order_by("nivel", "nombre"))
    definiciones = [
        {"nombre": r.nombre, "nivel": r.nivel, "minutos_inactividad": r.minutos_inactividad, "requiere_totp": r.requiere_totp, "permisos": sorted(a.permiso for a in r.asignaciones.all())}
        for r in roles
    ]
    candidatos = [d for d in definiciones if set(INDISPENSABLES) <= set(d["permisos"]) and d["requiere_totp"]]
    if not candidatos:
        raise ErrorPlantilla("Ningún rol administra usuarios y roles con autenticador; no se puede exportar.")
    conceptos = []
    for concepto in ConceptoCobro.objects.filter(activo=True).exclude(aplica_a=ConceptoCobro.AGRUPACION).select_related("regla_recargo"):
        regla = concepto.regla_recargo
        conceptos.append(
            {
                "nombre": concepto.nombre,
                "tipo": concepto.tipo,
                "periodicidad": concepto.periodicidad,
                "aplica_a": concepto.aplica_a,
                "prioridad": min(concepto.prioridad, 1000),
                "recargo": {"tipo": regla.tipo, "dias_gracia": min(regla.dias_gracia, 60), "se_repite": regla.se_repite} if regla else False,
            }
        )
    datos = {
        "nombre": "Configuración exportada",
        "moneda": moneda.codigo_actual(),
        "descripcion": "Plantilla generada desde la configuración de una instalación, sin cifras ni datos de personas.",
        "vocabulario": {clave: texto for clave, texto in vocabulario().items() if clave in VOCABULARIO_BASE},
        "roles": definiciones,
        "rol_inicial": max(candidatos, key=lambda d: d["nivel"])["nombre"],
        "politicas": [
            {
                "accion": p.accion,
                "permiso_directo": p.permiso_directo,
                "permiso_solicitar": p.permiso_solicitar,
                "permiso_aprobar": p.permiso_aprobar,
                "horas_caducidad": p.horas_caducidad,
                "horas_resaltar": p.horas_resaltar,
                "permite_delegacion": p.permite_delegacion,
                "permite_codigo": p.permite_codigo,
            }
            for p in PoliticaAccion.objects.all()
        ],
        "motivos_baja": list(MotivoBaja.objects.filter(activo=True).values_list("nombre", flat=True)),
        "relaciones_contacto": list(RelacionContacto.objects.filter(activa=True).values_list("nombre", flat=True)),
        "campos_contacto": [
            {"etiqueta": c.etiqueta, "tipo": c.tipo, "obligatorio": c.obligatorio, "principal": c.principal, "orden": c.orden}
            for c in CampoContacto.objects.filter(activo=True)
        ],
        "conceptos": conceptos,
        "medios_pago": list(MedioPago.objects.filter(activo=True).values_list("nombre", flat=True)),
        "cajas": list(Caja.objects.filter(activa=True).values_list("nombre", flat=True)),
        "denominaciones": list(Denominacion.objects.filter(activa=True).values_list("valor", flat=True)),
        "cortes": [{"tipo": d.tipo, "nombre": d.nombre, "nivel": d.nivel, "activa": d.activa} for d in DefinicionCorte.objects.all()],
    }
    esquema.validar(datos)
    return datos


def a_json(datos):
    return json.dumps(datos, ensure_ascii=False, indent=2) + "\n"
