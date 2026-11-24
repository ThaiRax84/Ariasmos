from django.db import migrations, models

PERMISO = "ver_ingresos"


def otorgar(apps, schema_editor):
    from auditoria.servicios import registrar

    PermisoRol = apps.get_model("cuentas", "PermisoRol")
    con_cortes = PermisoRol.objects.filter(permiso="ver_cortes").select_related("rol").order_by("rol__nivel", "rol__nombre")
    for asignacion in con_cortes:
        _, creado = PermisoRol.objects.get_or_create(rol_id=asignacion.rol_id, permiso=PERMISO)
        if creado:
            registrar("permiso_agregado", datos={"permiso": PERMISO, "papel": asignacion.rol.nombre})


def quitar(apps, schema_editor):
    apps.get_model("cuentas", "PermisoRol").objects.filter(permiso=PERMISO).delete()
    apps.get_model("cuentas", "Delegacion").objects.filter(permiso=PERMISO).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cuentas", "0010_merge_20261118_1411"),
        ("auditoria", "0003_bitacora_sellada"),
    ]

    operations = [
        migrations.AlterField(
            model_name="delegacion",
            name="permiso",
            field=models.CharField(
                choices=[
                    ("ver_titulares", "Ver {padron_min} y saldos"),
                    ("solicitar_alta_baja", "Solicitar alta, baja o reactivación"),
                    ("alta_baja_directa", "Alta, baja o reactivación directa"),
                    ("aprobar_solicitudes", "Aprobar solicitudes"),
                    ("otorgar_delegaciones", "Otorgar delegaciones"),
                    ("registrar_pago_efectivo", "Registrar pago en efectivo"),
                    ("turno_caja", "Abrir y cerrar su turno de caja"),
                    (
                        "solicitar_ajustes",
                        "Solicitar cancelación de recibo, condonación o {descuento_min}",
                    ),
                    (
                        "aplicar_ajustes",
                        "Cancelar recibo, condonar recargo o aplicar {descuento_min}",
                    ),
                    ("cargo_manual", "Cargo manual"),
                    ("recibir_efectivo", "Recibir efectivo y revisar arqueos"),
                    (
                        "sugerir_conciliacion",
                        "Sugerir identificación de movimientos bancarios",
                    ),
                    ("conciliar_banco", "Importar banco y conciliar"),
                    ("administrar_conceptos", "Administrar conceptos de cobro"),
                    ("ver_cortes", "Ver cortes"),
                    (
                        "ver_ingresos",
                        "Ver cuánto entra: importes de los cobros y ventas de otras personas y de los depósitos del banco",
                    ),
                    ("cerrar_cortes", "Cerrar cortes"),
                    ("aprobar_dispositivos", "Aprobar dispositivos"),
                    ("administrar_usuarios", "Administrar usuarios"),
                    ("administrar_roles", "Administrar roles y permisos"),
                    ("administrar_politicas", "Administrar políticas de aprobación"),
                    ("administrar_configuracion", "Administrar configuración"),
                    ("ver_auditoria", "Ver auditoría"),
                    ("administrar_respaldos", "Administrar respaldos"),
                    ("retirar_efectivo", "Retirar efectivo de su caja para gastos"),
                    ("revisar_retiros", "Revisar retiros de caja"),
                    ("administrar_motivos_retiro", "Administrar motivos de retiro"),
                    ("vender_articulos", "Vender artículos del inventario"),
                    (
                        "registrar_movimientos_inventario",
                        "Registrar entradas y mermas de inventario",
                    ),
                    ("subir_conteo_inventario", "Subir el conteo de inventario"),
                    ("devolver_articulos", "Registrar devoluciones de artículos"),
                    ("revisar_inventario", "Revisar movimientos de inventario"),
                    ("administrar_articulos", "Administrar artículos del inventario"),
                    (
                        "configurar_topes_banco",
                        "Configurar los topes del banco para aplicar pagos solos",
                    ),
                    (
                        "importar_padron",
                        "Importar o actualizar {padron_min} desde una hoja, sin aprobación",
                    ),
                    (
                        "solicitar_importacion_padron",
                        "Pedir que se importe o actualice {padron_min} desde una hoja",
                    ),
                    (
                        "configurar_limites_adeudo",
                        "Configurar los límites de adeudo y sus excepciones",
                    ),
                    (
                        "configurar_rezagos",
                        "Configurar las reglas de rezago y sus acciones",
                    ),
                ],
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name="permisorol",
            name="permiso",
            field=models.CharField(
                choices=[
                    ("ver_titulares", "Ver {padron_min} y saldos"),
                    ("solicitar_alta_baja", "Solicitar alta, baja o reactivación"),
                    ("alta_baja_directa", "Alta, baja o reactivación directa"),
                    ("aprobar_solicitudes", "Aprobar solicitudes"),
                    ("otorgar_delegaciones", "Otorgar delegaciones"),
                    ("registrar_pago_efectivo", "Registrar pago en efectivo"),
                    ("turno_caja", "Abrir y cerrar su turno de caja"),
                    (
                        "solicitar_ajustes",
                        "Solicitar cancelación de recibo, condonación o {descuento_min}",
                    ),
                    (
                        "aplicar_ajustes",
                        "Cancelar recibo, condonar recargo o aplicar {descuento_min}",
                    ),
                    ("cargo_manual", "Cargo manual"),
                    ("recibir_efectivo", "Recibir efectivo y revisar arqueos"),
                    (
                        "sugerir_conciliacion",
                        "Sugerir identificación de movimientos bancarios",
                    ),
                    ("conciliar_banco", "Importar banco y conciliar"),
                    ("administrar_conceptos", "Administrar conceptos de cobro"),
                    ("ver_cortes", "Ver cortes"),
                    (
                        "ver_ingresos",
                        "Ver cuánto entra: importes de los cobros y ventas de otras personas y de los depósitos del banco",
                    ),
                    ("cerrar_cortes", "Cerrar cortes"),
                    ("aprobar_dispositivos", "Aprobar dispositivos"),
                    ("administrar_usuarios", "Administrar usuarios"),
                    ("administrar_roles", "Administrar roles y permisos"),
                    ("administrar_politicas", "Administrar políticas de aprobación"),
                    ("administrar_configuracion", "Administrar configuración"),
                    ("ver_auditoria", "Ver auditoría"),
                    ("administrar_respaldos", "Administrar respaldos"),
                    ("retirar_efectivo", "Retirar efectivo de su caja para gastos"),
                    ("revisar_retiros", "Revisar retiros de caja"),
                    ("administrar_motivos_retiro", "Administrar motivos de retiro"),
                    ("vender_articulos", "Vender artículos del inventario"),
                    (
                        "registrar_movimientos_inventario",
                        "Registrar entradas y mermas de inventario",
                    ),
                    ("subir_conteo_inventario", "Subir el conteo de inventario"),
                    ("devolver_articulos", "Registrar devoluciones de artículos"),
                    ("revisar_inventario", "Revisar movimientos de inventario"),
                    ("administrar_articulos", "Administrar artículos del inventario"),
                    (
                        "configurar_topes_banco",
                        "Configurar los topes del banco para aplicar pagos solos",
                    ),
                    (
                        "importar_padron",
                        "Importar o actualizar {padron_min} desde una hoja, sin aprobación",
                    ),
                    (
                        "solicitar_importacion_padron",
                        "Pedir que se importe o actualice {padron_min} desde una hoja",
                    ),
                    (
                        "configurar_limites_adeudo",
                        "Configurar los límites de adeudo y sus excepciones",
                    ),
                    (
                        "configurar_rezagos",
                        "Configurar las reglas de rezago y sus acciones",
                    ),
                ],
                max_length=40,
            ),
        ),
        migrations.RunPython(otorgar, quitar),
    ]
