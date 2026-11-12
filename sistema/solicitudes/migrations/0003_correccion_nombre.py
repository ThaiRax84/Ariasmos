from django.db import migrations, models


def politica_por_defecto(apps, schema_editor):
    Politica = apps.get_model("solicitudes", "PoliticaAccion")
    if Politica.objects.exists() and not Politica.objects.filter(accion="correccion_nombre").exists():
        Politica.objects.create(
            accion="correccion_nombre",
            permiso_directo="alta_baja_directa",
            permiso_solicitar="solicitar_alta_baja",
            permiso_aprobar="aprobar_solicitudes",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("solicitudes", "0002_endurecimiento"),
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
                ],
                max_length=30,
                unique=True,
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
                ],
                max_length=30,
            ),
        ),
        migrations.RunPython(politica_por_defecto, migrations.RunPython.noop),
    ]
