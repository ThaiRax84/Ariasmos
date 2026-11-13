from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cobros", "0003_libro"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="plancobro",
            name="plan_descuento_valido",
        ),
        migrations.RemoveField(
            model_name="plancobro",
            name="descuento_centesimas",
        ),
    ]
