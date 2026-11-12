import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("cobros", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Agrupacion",
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
                ("nombre", models.CharField(max_length=100, unique=True)),
                ("activa", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["nombre"],
            },
        ),
        migrations.CreateModel(
            name="MotivoBaja",
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
                ("nombre", models.CharField(max_length=100, unique=True)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["nombre"],
            },
        ),
        migrations.CreateModel(
            name="RelacionContacto",
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
                ("activa", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["nombre"],
            },
        ),
        migrations.CreateModel(
            name="CampoContacto",
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
                ("etiqueta", models.CharField(max_length=60, unique=True)),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("telefono", "Teléfono"),
                            ("correo", "Correo electrónico"),
                            ("texto", "Texto"),
                        ],
                        max_length=10,
                    ),
                ),
                ("obligatorio", models.BooleanField(default=False)),
                ("principal", models.BooleanField(default=False)),
                ("orden", models.PositiveSmallIntegerField(default=10)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["orden", "etiqueta"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("principal", True)),
                        fields=("principal",),
                        name="campo_contacto_un_principal",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Titular",
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
                    "matricula",
                    models.CharField(editable=False, max_length=12, unique=True),
                ),
                ("nombre", models.CharField(max_length=100)),
                ("apellidos", models.CharField(max_length=150)),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("pendiente", "Pendiente"),
                            ("activo", "Activo"),
                            ("baja", "Baja"),
                            ("rechazado", "Rechazado"),
                        ],
                        default="pendiente",
                        max_length=10,
                    ),
                ),
                ("notas", models.TextField(blank=True)),
                ("constancia_consentimiento", models.BooleanField(default=False)),
                ("fecha_baja", models.DateTimeField(blank=True, null=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                (
                    "agrupacion",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="titulares",
                        to="titulares.agrupacion",
                    ),
                ),
                (
                    "conceptos_iniciales",
                    models.ManyToManyField(
                        blank=True, related_name="+", to="cobros.conceptocobro"
                    ),
                ),
                (
                    "creado_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "motivo_baja",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="titulares.motivobaja",
                    ),
                ),
            ],
            options={
                "ordering": ["apellidos", "nombre"],
            },
        ),
        migrations.CreateModel(
            name="Contacto",
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
                ("nombre", models.CharField(max_length=150)),
                ("valores", models.JSONField(blank=True, default=dict)),
                ("principal", models.BooleanField(default=False)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                (
                    "relacion",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="titulares.relacioncontacto",
                    ),
                ),
                (
                    "titular",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contactos",
                        to="titulares.titular",
                    ),
                ),
            ],
            options={
                "ordering": ["-principal", "nombre"],
            },
        ),
        migrations.AddConstraint(
            model_name="titular",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("estado__in", ["pendiente", "activo", "baja", "rechazado"])
                ),
                name="titular_estado_valido",
            ),
        ),
        migrations.AddConstraint(
            model_name="contacto",
            constraint=models.UniqueConstraint(
                condition=models.Q(("principal", True)),
                fields=("titular",),
                name="contacto_un_principal",
            ),
        ),
    ]
