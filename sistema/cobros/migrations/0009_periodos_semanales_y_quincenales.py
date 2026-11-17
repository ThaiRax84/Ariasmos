from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cobros", "0008_medio_devolucion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cargo",
            name="periodo",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AlterField(
            model_name="conceptocobro",
            name="aplica_a",
            field=models.CharField(
                choices=[
                    ("nuevos", "{titulares} nuevos"),
                    ("todos", "Todos los activos"),
                    ("agrupacion", "{agrupacion}"),
                    ("manual", "Manual"),
                ],
                default="manual",
                max_length=12,
            ),
        ),
    ]
