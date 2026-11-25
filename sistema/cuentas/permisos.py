PERMISOS = {
    "ver_titulares": "Ver {padron_min} y saldos",
    "solicitar_alta_baja": "Solicitar alta, baja o reactivación",
    "alta_baja_directa": "Alta, baja o reactivación directa",
    "aprobar_solicitudes": "Aprobar solicitudes",
    "otorgar_delegaciones": "Otorgar delegaciones",
    "registrar_pago_efectivo": "Registrar pago en efectivo",
    "turno_caja": "Abrir y cerrar su turno de caja",
    "solicitar_ajustes": "Solicitar cancelación de recibo, condonación o {descuento_min}",
    "aplicar_ajustes": "Cancelar recibo, condonar recargo o aplicar {descuento_min}",
    "cargo_manual": "Cargo manual",
    "recibir_efectivo": "Recibir efectivo y revisar arqueos",
    "sugerir_conciliacion": "Sugerir identificación de movimientos bancarios",
    "conciliar_banco": "Importar banco y conciliar",
    "administrar_conceptos": "Administrar conceptos de cobro",
    "ver_cortes": "Ver cortes",
    "ver_ingresos": "Ver cuánto entra: importes de los cobros y ventas de otras personas y de los depósitos del banco",
    "cerrar_cortes": "Cerrar cortes",
    "aprobar_dispositivos": "Aprobar dispositivos",
    "administrar_usuarios": "Administrar usuarios",
    "administrar_roles": "Administrar roles y permisos",
    "administrar_politicas": "Administrar políticas de aprobación",
    "administrar_configuracion": "Administrar configuración",
    "ver_auditoria": "Ver auditoría",
    "administrar_respaldos": "Administrar respaldos",
    "retirar_efectivo": "Retirar efectivo de su caja para gastos",
    "revisar_retiros": "Revisar retiros de caja",
    "administrar_motivos_retiro": "Administrar motivos de retiro",
    "vender_articulos": "Vender artículos del inventario",
    "registrar_movimientos_inventario": "Registrar entradas y mermas de inventario",
    "subir_conteo_inventario": "Subir el conteo de inventario",
    "devolver_articulos": "Registrar devoluciones de artículos",
    "revisar_inventario": "Revisar movimientos de inventario",
    "administrar_articulos": "Administrar artículos del inventario",
    "configurar_topes_banco": "Configurar los topes del banco para aplicar pagos solos",
    "importar_padron": "Importar o actualizar {padron_min} desde una hoja, sin aprobación",
    "solicitar_importacion_padron": "Pedir que se importe o actualice {padron_min} desde una hoja",
    "configurar_limites_adeudo": "Configurar los límites de adeudo y sus excepciones",
    "configurar_rezagos": "Configurar las reglas de rezago y sus acciones",
}

OPCIONES = list(PERMISOS.items())

DELEGABLES = ("alta_baja_directa", "aprobar_solicitudes", "ver_ingresos")

INDISPENSABLES = ("administrar_usuarios", "administrar_roles")


def ve_ingresos(usuario):
    return usuario.tiene_permiso("ver_ingresos")


def etiqueta(permiso, voc=None):
    from configuracion.models import con_vocabulario

    return con_vocabulario(PERMISOS[permiso], voc)


def opciones(voc=None):
    if voc is None:
        from configuracion.models import vocabulario

        voc = vocabulario()
    return [(clave, etiqueta(clave, voc)) for clave in PERMISOS]


def unir(nombres, conjuncion="o"):
    nombres = list(nombres)
    if len(nombres) < 2:
        return "".join(nombres)
    return f"{', '.join(nombres[:-1])} {conjuncion} {nombres[-1]}"


def roles_con(*permisos):
    from .models import Rol

    return list(Rol.objects.filter(asignaciones__permiso__in=permisos).distinct().order_by("nivel", "nombre").values_list("nombre", flat=True))


def quienes(*permisos):
    nombres = roles_con(*permisos)
    if nombres:
        return unir(nombres)
    return "quien tenga el permiso «" + etiqueta(permisos[0]) + "»"
