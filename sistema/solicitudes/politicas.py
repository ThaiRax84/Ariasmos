ALTAS = ("alta_baja_directa", "solicitar_alta_baja", "aprobar_solicitudes")
AJUSTES = ("aplicar_ajustes", "solicitar_ajustes", "aprobar_solicitudes")
RETIROS = ("aprobar_solicitudes", "retirar_efectivo", "aprobar_solicitudes")

POR_DEFECTO = {
    "correccion_nombre": ALTAS,
    "cambio_familia": ALTAS,
    "beca": AJUSTES,
    "prorroga": AJUSTES,
    "cancelar_cargo": AJUSTES,
    "condonar_recargo": AJUSTES,
    "revertir_pago": AJUSTES,
    "pago_sobre_tope": AJUSTES,
    "retiro_caja": RETIROS,
    "revertir_retiro": RETIROS,
}


def definicion(accion):
    directo, solicitar, aprobar = POR_DEFECTO[accion]
    return {
        "accion": accion,
        "permiso_directo": directo,
        "permiso_solicitar": solicitar,
        "permiso_aprobar": aprobar,
        "horas_caducidad": 72,
        "horas_resaltar": 24,
        "permite_delegacion": True,
        "permite_codigo": True,
    }
