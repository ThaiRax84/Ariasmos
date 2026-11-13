from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cobros", "0007_pago_de_carpeta_vigilada"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pago",
            name="medio",
            field=models.CharField(
                choices=[
                    ("efectivo", "Efectivo"),
                    ("banco", "Banco"),
                    ("saldo_inicial", "Saldo inicial"),
                    ("devolucion", "Saldo a favor por devolución de artículos"),
                ],
                max_length=15,
            ),
        ),
    ]
