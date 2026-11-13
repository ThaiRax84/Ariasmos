import traceback

from django.utils import timezone

from auditoria.servicios import registrar, verificar_cadena
from banco import carpeta as carpeta_banco
from banco.models import depurar_cargas
from cobros import generacion
from cortes import servicios as cortes
from cuentas import secretos
from respaldos import servicios as respaldos
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


def _cargas(hoy):
    return f"{depurar_cargas()} archivos en revisión vencidos depurados"


def _secretos(hoy):
    cambiados = secretos.cifrar_pendientes()
    if secretos.en_claro():
        raise RuntimeError("quedan secretos del autenticador en claro")
    return f"{cambiados} secretos del autenticador cifrados"


def _carpeta_banco(hoy):
    informe = carpeta_banco.revisar()
    if informe.get("sin_carpeta"):
        return "sin carpeta vigilada del banco"
    return f"{informe['importados']} importados, {informe['rechazados']} rechazados y {informe['esperando']} en espera en la carpeta del banco"


def _mayores(hoy):
    return f"{len(cortes.generar_mayores(hoy))} cortes mayores generados"


def _vencidos(hoy):
    return f"{len(cortes.cerrar_vencidos(hoy))} cortes mayores cerrados sin revisar"


def _cobranza(hoy):
    return "lista de cobranza generada" if cortes.cobranza_programada(hoy) else "sin lista de cobranza hoy"


def _entregas(hoy):
    hechas, fallidas = cortes.ejecutar_entregas()
    if fallidas:
        raise RuntimeError(f"{fallidas} entregas fallaron y se reintentarán ({hechas} entregadas)")
    return f"{hechas} entregas hechas"


def _respaldo(hoy):
    if not respaldos.carpeta():
        return "sin carpeta de respaldo configurada"
    if not respaldos.toca_respaldo():
        return "todavía no toca respaldo"
    registro = respaldos.respaldar(automatico=True, dia=hoy)
    if registro is None:
        return "otro trabajador ya hizo el respaldo de hoy"
    if registro.resultado != registro.CORRECTO:
        raise RuntimeError(f"respaldo fallido: {registro.mensaje}")
    return f"respaldo {registro.archivo}"


def _prueba(hoy):
    if not respaldos.toca_prueba():
        return "todavía no toca prueba de restauración"
    registro = respaldos.probar(automatico=True, dia=hoy)
    if registro is None:
        return "otro trabajador ya hizo la prueba de hoy"
    if registro.resultado != registro.CORRECTO:
        raise RuntimeError(f"prueba de restauración fallida: {registro.mensaje}")
    return f"prueba de restauración correcta de {registro.archivo}"


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
    ("depurar_cargas", _cargas, False),
    ("carpeta_banco", _carpeta_banco, False),
    ("cifrar_secretos", _secretos, False),
    ("generar_cortes_mayores", _mayores, False),
    ("cerrar_cortes_vencidos", _vencidos, False),
    ("lista_cobranza", _cobranza, False),
    ("entregar_cortes", _entregas, False),
    ("respaldo", _respaldo, False),
    ("prueba_respaldo", _prueba, False),
    ("verificar_bitacora", _bitacora, True),
)


def ejecutar_ciclo(hoy=None):
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
    return informe
