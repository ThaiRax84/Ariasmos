from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Respaldo",
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
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("respaldo", "Respaldo"),
                            ("prueba", "Prueba de restauración"),
                        ],
                        max_length=10,
                    ),
                ),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("terminado", models.DateTimeField(blank=True, null=True)),
                ("archivo", models.CharField(blank=True, max_length=120)),
                ("tamano", models.PositiveBigIntegerField(default=0)),
                ("sha256", models.CharField(blank=True, max_length=64)),
                (
                    "resultado",
                    models.CharField(
                        choices=[
                            ("en_curso", "En curso"),
                            ("correcto", "Correcto"),
                            ("fallo", "Falló"),
                        ],
                        default="en_curso",
                        max_length=10,
                    ),
                ),
                ("mensaje", models.CharField(blank=True, max_length=300)),
                ("conteos", models.JSONField(blank=True, default=dict)),
                ("automatico", models.BooleanField(default=False)),
                ("dia", models.DateField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-creado", "-id"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("automatico", True)),
                        fields=("tipo", "dia"),
                        name="respaldo_automatico_unico",
                    )
                ],
            },
        ),
    ]
