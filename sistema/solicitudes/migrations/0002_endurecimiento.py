import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("solicitudes", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="IntentoCodigo",
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
                            ("fallido", "Código erróneo"),
                            ("bloqueo", "Vía de código bloqueada"),
                        ],
                        max_length=10,
                    ),
                ),
                ("motivo", models.CharField(blank=True, max_length=20)),
                ("momento", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("visto", models.BooleanField(default=False)),
                (
                    "autorizador",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="intentos_de_codigo",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "capturista",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "solicitud",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="intentos_de_codigo",
                        to="solicitudes.solicitud",
                    ),
                ),
            ],
            options={
                "ordering": ["-momento"],
            },
        ),
    ]
