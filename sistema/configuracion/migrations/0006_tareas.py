from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("configuracion", "0005_fase2"),
    ]

    operations = [
        migrations.CreateModel(
            name="Tarea",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nombre", models.CharField(max_length=60, unique=True)),
                ("ultima_ejecucion", models.DateTimeField(blank=True, null=True)),
                ("ultima_fecha", models.DateField(blank=True, null=True)),
                ("exito", models.BooleanField(default=True)),
                ("resultado", models.CharField(blank=True, max_length=500)),
                ("ejecuciones", models.PositiveIntegerField(default=0)),
            ],
            options={
                "ordering": ["nombre"],
            },
        ),
    ]
