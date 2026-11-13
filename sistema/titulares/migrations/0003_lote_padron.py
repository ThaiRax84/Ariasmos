import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("titulares", "0002_familias"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LotePadron",
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
                ("nombre_archivo", models.CharField(max_length=120)),
                ("sha256", models.CharField(max_length=64)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("filas", models.PositiveIntegerField(default=0)),
                ("creados", models.PositiveIntegerField(default=0)),
                ("duplicados", models.PositiveIntegerField(default=0)),
                ("con_error", models.PositiveIntegerField(default=0)),
                ("familias", models.PositiveIntegerField(default=0)),
                ("cargos", models.PositiveIntegerField(default=0)),
                ("a_favor", models.PositiveIntegerField(default=0)),
                ("resultado", models.JSONField(default=dict)),
                (
                    "creado_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-creado"],
            },
        ),
    ]
