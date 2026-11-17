from django.db import migrations, models


def crear_topes(apps, schema_editor):
    TopeDiarioBanco = apps.get_model("banco", "TopeDiarioBanco")
    for dia in range(7):
        TopeDiarioBanco.objects.get_or_create(dia=dia, defaults={"importe": 0})


class Migration(migrations.Migration):

    dependencies = [
        ("banco", "0007_retencion_por_movimiento"),
    ]

    operations = [
        migrations.AddField(
            model_name="movimientobancario",
            name="dia_aplicado_solo",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.CreateModel(
            name="TopeDiarioBanco",
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
                ("dia", models.PositiveSmallIntegerField(unique=True)),
                ("importe", models.PositiveBigIntegerField(default=0)),
            ],
            options={
                "ordering": ["dia"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("dia__lte", 6)),
                        name="tope_diario_dia_de_la_semana",
                    )
                ],
            },
        ),
        migrations.RunPython(crear_topes, migrations.RunPython.noop),
    ]
