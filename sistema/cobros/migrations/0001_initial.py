from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ConceptoCobro",
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
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("unico", "Único"),
                            ("recurrente", "Recurrente"),
                            ("por_evento", "Por evento"),
                        ],
                        max_length=12,
                    ),
                ),
                ("importe_centavos", models.PositiveIntegerField(default=0)),
                (
                    "periodicidad",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("semanal", "Semanal"),
                            ("quincenal", "Quincenal"),
                            ("mensual", "Mensual"),
                            ("bimestral", "Bimestral"),
                            ("trimestral", "Trimestral"),
                            ("semestral", "Semestral"),
                            ("anual", "Anual"),
                        ],
                        max_length=12,
                    ),
                ),
                (
                    "dia_vencimiento",
                    models.PositiveSmallIntegerField(blank=True, null=True),
                ),
                (
                    "aplica_a",
                    models.CharField(
                        choices=[
                            ("nuevos", "Titulares nuevos"),
                            ("todos", "Todos los activos"),
                            ("agrupacion", "Una agrupación"),
                            ("manual", "Manual"),
                        ],
                        default="manual",
                        max_length=12,
                    ),
                ),
                ("prioridad", models.PositiveSmallIntegerField(default=100)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["prioridad", "nombre"],
            },
        ),
        migrations.CreateModel(
            name="PlanCobro",
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
                    "importe_centavos",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "descuento_centesimas",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("vigente_desde", models.DateField()),
                ("vigente_hasta", models.DateField(blank=True, null=True)),
                ("activo", models.BooleanField(default=True)),
                ("nota", models.CharField(blank=True, max_length=200)),
            ],
            options={
                "ordering": ["-vigente_desde"],
            },
        ),
        migrations.CreateModel(
            name="ReglaRecargo",
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
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("fijo", "Importe fijo"),
                            ("porcentaje", "Porcentaje"),
                        ],
                        default="fijo",
                        max_length=10,
                    ),
                ),
                ("valor", models.PositiveIntegerField(default=0)),
                ("dias_gracia", models.PositiveSmallIntegerField(default=0)),
                ("se_repite", models.BooleanField(default=False)),
                ("tope_centavos", models.PositiveIntegerField(blank=True, null=True)),
                ("activa", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["nombre"],
            },
        ),
    ]
