from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("configuracion", "0009_moneda_del_negocio"),
    ]

    operations = [
        migrations.AddField(
            model_name="negocio",
            name="periodo_cerrado_hasta",
            field=models.DateField(blank=True, null=True),
        ),
    ]
