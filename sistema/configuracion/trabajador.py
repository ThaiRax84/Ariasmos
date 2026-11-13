import traceback

from django.db import close_old_connections
from django.utils import timezone

from auditoria.servicios import registrar, verificar_cadena
from cobros import generacion
from cuentas.servicios import depurar_pendientes
from solicitudes import motor

from .models import Tarea, hoy_negocio


def _cargos(hoy):
    return f"{generacion.generar_recurrentes(hoy)} cargos recurrentes"


def _recargos(hoy):
    return f"{generacion.generar_recargos(hoy)} recargos"


def _solicitudes(hoy):
    motor.caducar_vencidas()
    return "solicitudes vencidas caducadas"


def _equipos(hoy):
    return f"{depurar_pendientes()} equipos pendientes depurados"


def _bitacora(hoy):
    resultado = verificar_cadena(guardar=True)
    if not resultado.valida:
        raise RuntimeError(f"bitácora no íntegra: {resultado.motivo} en el evento {resultado.numero}")
    return f"bitácora íntegra ({resultado.total} eventos)"


TAREAS = (
    ("generar_cargos", _cargos, False),
    ("generar_recargos", _recargos, False),
    ("caducar_solicitudes", _solicitudes, False),
    ("depurar_equipos", _equipos, False),
    ("verificar_bitacora", _bitacora, True),
)


def ejecutar_ciclo(hoy=None):
    close_old_connections()
    hoy = hoy or hoy_negocio()
    informe = []
    for nombre, funcion, diaria in TAREAS:
        tarea, _ = Tarea.objects.get_or_create(nombre=nombre)
        if diaria and tarea.exito and tarea.ultima_fecha is not None and tarea.ultima_fecha >= hoy:
            informe.append((nombre, True, "ya se hizo hoy"))
            continue
        try:
            texto = funcion(hoy)
            exito = True
        except Exception as error:
            texto = f"{type(error).__name__}: {error}"[:500]
            exito = False
            registrar("tarea_fallida", datos={"tarea": nombre, "error": texto, "detalle": traceback.format_exc()[-1500:]})
        Tarea.objects.filter(pk=tarea.pk).update(ultima_ejecucion=timezone.now(), ultima_fecha=hoy, exito=exito, resultado=texto, ejecuciones=tarea.ejecuciones + 1)
        informe.append((nombre, exito, texto))
    close_old_connections()
    return informe
