import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("cobros", "0009_periodos_semanales_y_quincenales"),
        ("titulares", "0005_hojas_y_apellidos_opcionales"),
    ]

    operations = [
        migrations.CreateModel(
            name="TarifaAgrupacion",
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
                ("importe_centavos", models.PositiveBigIntegerField()),
                ("periodicidad", models.CharField(blank=True, max_length=12)),
                (
                    "dia_vencimiento",
                    models.PositiveSmallIntegerField(blank=True, null=True),
                ),
                ("activa", models.BooleanField(default=True)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                ("actualizada", models.DateTimeField(auto_now=True)),
                (
                    "agrupacion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tarifas",
                        to="titulares.agrupacion",
                    ),
                ),
                (
                    "concepto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tarifas",
                        to="cobros.conceptocobro",
                    ),
                ),
            ],
            options={
                "ordering": [
                    "concepto__prioridad",
                    "concepto__nombre",
                    "agrupacion__nombre",
                ],
            },
        ),
        migrations.CreateModel(
            name="OrigenCargo",
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
                ("periodicidad", models.CharField(max_length=12)),
                ("inicio", models.DateField()),
                ("fin", models.DateField()),
                (
                    "cargo",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="origen_tarifa",
                        to="cobros.cargo",
                    ),
                ),
                (
                    "tarifa",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cargos",
                        to="tarifas.tarifaagrupacion",
                    ),
                ),
            ],
            options={
                "ordering": ["inicio", "id"],
            },
        ),
        migrations.CreateModel(
            name="OpcionConcepto",
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
                ("por_cantidad", models.BooleanField(default=False)),
                ("cantidad_maxima", models.PositiveIntegerField(default=1)),
                ("solo_con_tarifa", models.BooleanField(default=False)),
                ("actualizada", models.DateTimeField(auto_now=True)),
                (
                    "concepto",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="opciones_tarifa",
                        to="cobros.conceptocobro",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("cantidad_maxima__gte", 1), ("cantidad_maxima__lte", 10000)
                        ),
                        name="opcion_cantidad_maxima_valida",
                    )
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="tarifaagrupacion",
            constraint=models.UniqueConstraint(
                fields=("concepto", "agrupacion"), name="tarifa_una_por_agrupacion"
            ),
        ),
        migrations.AddConstraint(
            model_name="tarifaagrupacion",
            constraint=models.CheckConstraint(
                condition=models.Q(("importe_centavos__gt", 0)),
                name="tarifa_importe_positivo",
            ),
        ),
        migrations.AddConstraint(
            model_name="tarifaagrupacion",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("dia_vencimiento__isnull", True),
                    models.Q(("dia_vencimiento__gte", 1), ("dia_vencimiento__lte", 28)),
                    _connector="OR",
                ),
                name="tarifa_dia_valido",
            ),
        ),
        migrations.AddConstraint(
            model_name="origencargo",
            constraint=models.CheckConstraint(
                condition=models.Q(("fin__gte", models.F("inicio"))),
                name="origen_periodo_valido",
            ),
        ),
    ]
