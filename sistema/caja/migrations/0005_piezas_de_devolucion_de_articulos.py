import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("caja", "0004_piezas_arqueo_y_retiros"),
        ("inventario", "0001_inicial"),
    ]

    operations = [
        migrations.AddField(
            model_name="movimientopiezas",
            name="devolucion_articulos",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="piezas",
                to="inventario.devolucion",
            ),
        ),
        migrations.AlterField(
            model_name="movimientopiezas",
            name="origen",
            field=models.CharField(
                choices=[
                    ("apertura", "Fondo de apertura"),
                    ("recibido", "Recibido en un cobro"),
                    ("cambio", "Cambio entregado"),
                    ("retiro", "Retiro de caja"),
                    ("reversion_retiro", "Reversión de retiro"),
                    ("devolucion", "Devolución de un pago"),
                    ("devolucion_articulos", "Devolución de artículos"),
                    ("traslado", "Entrega o depósito"),
                ],
                max_length=20,
            ),
        ),
    ]
