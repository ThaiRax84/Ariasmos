from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("caja", "0005_piezas_de_devolucion_de_articulos"),
    ]

    operations = [
        migrations.AddField(
            model_name="denominacion",
            name="tipo",
            field=models.CharField(
                choices=[("billete", "Billete"), ("moneda", "Moneda")],
                default="billete",
                max_length=8,
            ),
        ),
    ]
