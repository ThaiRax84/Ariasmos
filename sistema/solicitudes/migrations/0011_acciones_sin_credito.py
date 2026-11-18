from django.db import migrations, models

NUEVAS = {"cargo_sin_credito": "cargo_manual", "venta_sin_credito": "vender_articulos"}


def politicas(apps, schema_editor):
    PoliticaAccion = apps.get_model("solicitudes", "PoliticaAccion")
    if not PoliticaAccion.objects.exists():
        return
    for accion, solicitar in NUEVAS.items():
        PoliticaAccion.objects.get_or_create(
            accion=accion,
            defaults={"permiso_directo": "aplicar_ajustes", "permiso_solicitar": solicitar, "permiso_aprobar": "aprobar_solicitudes", "horas_caducidad": 72, "horas_resaltar": 24, "permite_delegacion": True, "permite_codigo": True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("cuentas", "0009_permisos_de_rezagos"),
        ("solicitudes", "0010_importacion_padron"),
    ]

    operations = [
        migrations.AlterField(
            model_name="politicaaccion",
            name="accion",
            field=models.CharField(
                choices=[
                    ("alta", "Alta"),
                    ("baja", "Baja"),
                    ("reactivacion", "Reactivación"),
                    ("correccion_nombre", "Corrección de nombre"),
                    ("cambio_familia", "Cambio de {familia_min}"),
                    ("beca", "{descuento}"),
                    ("prorroga", "Prórroga"),
                    ("cancelar_cargo", "Cancelación de cargo"),
                    ("condonar_recargo", "Condonación de recargo"),
                    ("revertir_pago", "Reversión de pago"),
                    ("pago_sobre_tope", "Pago mayor al tope"),
                    ("retiro_caja", "Retiro de caja"),
                    ("revertir_retiro", "Reversión de retiro de caja"),
                    ("conteo_inventario", "Conteo de inventario"),
                    ("devolucion_efectivo", "Devolución de artículos en efectivo"),
                    (
                        "importacion_padron",
                        "Importación o actualización desde una hoja",
                    ),
                    ("cargo_sin_credito", "Cargo manual sin crédito"),
                    ("venta_sin_credito", "Venta al adeudo sin crédito"),
                ],
                max_length=30,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="politicaaccion",
            name="permiso_aprobar",
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
            model_name="politicaaccion",
            name="permiso_directo",
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
            model_name="politicaaccion",
            name="permiso_solicitar",
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
            model_name="solicitud",
            name="accion",
            field=models.CharField(
                choices=[
                    ("alta", "Alta"),
                    ("baja", "Baja"),
                    ("reactivacion", "Reactivación"),
                    ("correccion_nombre", "Corrección de nombre"),
                    ("cambio_familia", "Cambio de {familia_min}"),
                    ("beca", "{descuento}"),
                    ("prorroga", "Prórroga"),
                    ("cancelar_cargo", "Cancelación de cargo"),
                    ("condonar_recargo", "Condonación de recargo"),
                    ("revertir_pago", "Reversión de pago"),
                    ("pago_sobre_tope", "Pago mayor al tope"),
                    ("retiro_caja", "Retiro de caja"),
                    ("revertir_retiro", "Reversión de retiro de caja"),
                    ("conteo_inventario", "Conteo de inventario"),
                    ("devolucion_efectivo", "Devolución de artículos en efectivo"),
                    (
                        "importacion_padron",
                        "Importación o actualización desde una hoja",
                    ),
                    ("cargo_sin_credito", "Cargo manual sin crédito"),
                    ("venta_sin_credito", "Venta al adeudo sin crédito"),
                ],
                max_length=30,
            ),
        ),
        migrations.RunPython(politicas, migrations.RunPython.noop),
    ]
