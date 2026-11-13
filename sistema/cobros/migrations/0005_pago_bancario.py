import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banco", "0003_importacion"),
        ("cobros", "0004_sin_descuento_de_plan"),
    ]

    operations = [
        migrations.AddField(
            model_name="pago",
            name="movimiento",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pagos",
                to="banco.movimientobancario",
            ),
        ),
        migrations.AlterField(
            model_name="pago",
            name="fecha",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
