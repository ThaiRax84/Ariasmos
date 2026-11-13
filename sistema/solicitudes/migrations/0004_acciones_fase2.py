from django.db import migrations, models


def politicas_nuevas(apps, schema_editor):
    from solicitudes.politicas import POR_DEFECTO, definicion

    Politica = apps.get_model("solicitudes", "PoliticaAccion")
    if not Politica.objects.exists():
        return
    for accion in POR_DEFECTO:
        if not Politica.objects.filter(accion=accion).exists():
            Politica.objects.create(**definicion(accion))


class Migration(migrations.Migration):

    dependencies = [
        ("solicitudes", "0003_correccion_nombre"),
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
                    ("cambio_familia", "Cambio de familia"),
                    ("beca", "Beca"),
                    ("prorroga", "Prórroga"),
                    ("cancelar_cargo", "Cancelación de cargo"),
                    ("condonar_recargo", "Condonación de recargo"),
                    ("revertir_pago", "Reversión de pago"),
                    ("pago_sobre_tope", "Pago mayor al tope"),
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
                    ("cambio_familia", "Cambio de familia"),
                    ("beca", "Beca"),
                    ("prorroga", "Prórroga"),
                    ("cancelar_cargo", "Cancelación de cargo"),
                    ("condonar_recargo", "Condonación de recargo"),
                    ("revertir_pago", "Reversión de pago"),
                    ("pago_sobre_tope", "Pago mayor al tope"),
                ],
                max_length=30,
            ),
        ),
        migrations.RunPython(politicas_nuevas, migrations.RunPython.noop),
    ]
