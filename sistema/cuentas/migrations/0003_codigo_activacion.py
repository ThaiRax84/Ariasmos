import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cuentas", "0002_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CodigoActivacion",
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
                ("hash_codigo", models.CharField(max_length=64, unique=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("caduca", models.DateTimeField()),
                ("usado_en", models.DateTimeField(blank=True, null=True)),
                ("invalidado", models.BooleanField(default=False)),
                (
                    "creado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="codigos_activacion",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-creado"],
            },
        ),
    ]
