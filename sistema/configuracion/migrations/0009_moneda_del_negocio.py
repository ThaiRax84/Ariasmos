from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("configuracion", "0008_parametros_banco"),
    ]

    operations = [
        migrations.AddField(
            model_name="negocio",
            name="moneda",
            field=models.CharField(default="MXN", max_length=3),
        ),
    ]
