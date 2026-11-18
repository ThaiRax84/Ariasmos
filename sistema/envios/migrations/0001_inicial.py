from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="EnvioUsado",
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
                ("ficha", models.CharField(max_length=64, unique=True)),
                ("ruta", models.CharField(max_length=300)),
                ("destino", models.CharField(blank=True, default="", max_length=500)),
                ("creado", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "verbose_name": "envío usado",
                "verbose_name_plural": "envíos usados",
            },
        ),
    ]
