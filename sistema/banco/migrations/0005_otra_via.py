import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banco", "0004_continuidad_y_revision"),
    ]

    operations = [
        migrations.AddField(
            model_name="importacion",
            name="otra_via",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="movimientobancario",
            name="confirmado_por",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="confirma_a",
                to="banco.movimientobancario",
            ),
        ),
        migrations.AddField(
            model_name="movimientobancario",
            name="mismo_que",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="otras_vias",
                to="banco.movimientobancario",
            ),
        ),
        migrations.AddField(
            model_name="movimientobancario",
            name="posible_duplicado",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="movimientobancario",
            name="estado",
            field=models.CharField(
                choices=[
                    ("aplicado", "Aplicado"),
                    ("por_identificar", "Por identificar"),
                    ("conciliado", "Depósito de caja conciliado"),
                    ("no_cobro", "No es un cobro"),
                    ("informativo", "Informativo"),
                    ("mismo", "Mismo movimiento que otro ya importado"),
                ],
                max_length=16,
            ),
        ),
    ]
