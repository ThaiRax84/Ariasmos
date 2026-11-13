from django.db import migrations

POLITICA = {"permiso_directo": "aprobar_solicitudes", "permiso_solicitar": "retirar_efectivo", "permiso_aprobar": "aprobar_solicitudes", "horas_caducidad": 72, "horas_resaltar": 24, "permite_delegacion": True, "permite_codigo": True}
REPARTO = {"turno_caja": ("retirar_efectivo",), "recibir_efectivo": ("revisar_retiros", "administrar_motivos_retiro")}


def agregar(apps, schema_editor):
    PoliticaAccion = apps.get_model("solicitudes", "PoliticaAccion")
    PermisoRol = apps.get_model("cuentas", "PermisoRol")
    if not PoliticaAccion.objects.exists():
        return
    for accion in ("retiro_caja", "revertir_retiro"):
        PoliticaAccion.objects.get_or_create(accion=accion, defaults=POLITICA)
    for base, nuevos in REPARTO.items():
        for rol_id in list(PermisoRol.objects.filter(permiso=base).values_list("rol_id", flat=True)):
            for permiso in nuevos:
                PermisoRol.objects.get_or_create(rol_id=rol_id, permiso=permiso)


class Migration(migrations.Migration):

    dependencies = [
        ("solicitudes", "0005_solicitudes_de_caja"),
        ("cuentas", "0005_permisos_de_retiros"),
    ]

    operations = [
        migrations.RunPython(agregar, migrations.RunPython.noop),
    ]
