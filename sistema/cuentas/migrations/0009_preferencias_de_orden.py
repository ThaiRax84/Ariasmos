import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cuentas", "0008_permisos_de_importacion"),
    ]

    operations = [
        migrations.CreateModel(
            name="PreferenciaOrden",
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
                ("lista", models.CharField(max_length=30)),
                ("clave", models.CharField(max_length=30)),
                ("descendente", models.BooleanField(default=False)),
                ("cambiado", models.DateTimeField(auto_now=True)),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ordenes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("usuario", "lista"), name="orden_uno_por_lista"
                    )
                ],
            },
        ),
    ]
