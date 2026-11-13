from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cobros", "0005_pago_bancario"),
    ]

    operations = [
        migrations.AddField(
            model_name="pago",
            name="fecha_banco",
            field=models.DateField(blank=True, null=True),
        ),
    ]
