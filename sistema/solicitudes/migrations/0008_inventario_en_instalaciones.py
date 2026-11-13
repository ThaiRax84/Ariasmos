from django.db import migrations

POLITICAS = {
    "conteo_inventario": {"permiso_directo": "aprobar_solicitudes", "permiso_solicitar": "subir_conteo_inventario", "permiso_aprobar": "aprobar_solicitudes", "horas_caducidad": 72, "horas_resaltar": 24, "permite_delegacion": True, "permite_codigo": True},
    "devolucion_efectivo": {"permiso_directo": "aprobar_solicitudes", "permiso_solicitar": "devolver_articulos", "permiso_aprobar": "aprobar_solicitudes", "horas_caducidad": 72, "horas_resaltar": 24, "permite_delegacion": True, "permite_codigo": True},
}
REPARTO = {
    "registrar_pago_efectivo": ("vender_articulos", "devolver_articulos"),
    "turno_caja": ("registrar_movimientos_inventario", "subir_conteo_inventario"),
    "recibir_efectivo": ("revisar_inventario",),
    "administrar_conceptos": ("administrar_articulos",),
}


def agregar(apps, schema_editor):
    PoliticaAccion = apps.get_model("solicitudes", "PoliticaAccion")
    PermisoRol = apps.get_model("cuentas", "PermisoRol")
    if not PoliticaAccion.objects.exists():
        return
    for accion, politica in POLITICAS.items():
        PoliticaAccion.objects.get_or_create(accion=accion, defaults=politica)
    for base, nuevos in REPARTO.items():
        for rol_id in list(PermisoRol.objects.filter(permiso=base).values_list("rol_id", flat=True)):
            for permiso in nuevos:
                PermisoRol.objects.get_or_create(rol_id=rol_id, permiso=permiso)


class Migration(migrations.Migration):

    dependencies = [
        ("solicitudes", "0007_acciones_de_inventario"),
        ("cuentas", "0006_permisos_de_inventario"),
    ]

    operations = [
        migrations.RunPython(agregar, migrations.RunPython.noop),
    ]
