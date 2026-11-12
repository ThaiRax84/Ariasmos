import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("cobros", "0001_initial"),
        ("titulares", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="conceptocobro",
            name="agrupacion",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="titulares.agrupacion",
            ),
        ),
        migrations.AddField(
            model_name="plancobro",
            name="concepto",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="planes",
                to="cobros.conceptocobro",
            ),
        ),
        migrations.AddField(
            model_name="plancobro",
            name="titular",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="planes",
                to="titulares.titular",
            ),
        ),
        migrations.AddField(
            model_name="conceptocobro",
            name="regla_recargo",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="conceptos",
                to="cobros.reglarecargo",
            ),
        ),
        migrations.AddConstraint(
            model_name="plancobro",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("vigente_hasta__isnull", True),
                    ("vigente_hasta__gte", models.F("vigente_desde")),
                    _connector="OR",
                ),
                name="plan_vigencia_valida",
            ),
        ),
        migrations.AddConstraint(
            model_name="plancobro",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("descuento_centesimas__isnull", True),
                    ("descuento_centesimas__lte", 10000),
                    _connector="OR",
                ),
                name="plan_descuento_valido",
            ),
        ),
        migrations.AddConstraint(
            model_name="conceptocobro",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("dia_vencimiento__isnull", True),
                    models.Q(("dia_vencimiento__gte", 1), ("dia_vencimiento__lte", 28)),
                    _connector="OR",
                ),
                name="concepto_dia_valido",
            ),
        ),
        migrations.AddConstraint(
            model_name="conceptocobro",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("tipo", "recurrente"), _negated=True),
                    models.Q(("periodicidad", ""), _negated=True),
                    _connector="OR",
                ),
                name="concepto_recurrente_con_periodo",
            ),
        ),
        migrations.AddConstraint(
            model_name="conceptocobro",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("aplica_a", "agrupacion"), _negated=True),
                    ("agrupacion__isnull", False),
                    _connector="OR",
                ),
                name="concepto_agrupacion_definida",
            ),
        ),
    ]
