from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banco", "0003_importacion"),
        ("caja", "0002_caja_inicial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="traslado",
            name="traslado_coherente",
        ),
        migrations.AlterField(
            model_name="traslado",
            name="estado",
            field=models.CharField(
                choices=[
                    ("pendiente", "Pendiente de confirmar"),
                    ("confirmado", "Confirmado"),
                    ("rechazado", "Rechazado"),
                    ("por_conciliar", "Por conciliar"),
                    ("conciliado", "Conciliado con el banco"),
                ],
                max_length=15,
            ),
        ),
        migrations.AddConstraint(
            model_name="traslado",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("tipo", "entrega"),
                        ("destino__isnull", False),
                        ("estado__in", ["pendiente", "confirmado", "rechazado"]),
                    ),
                    models.Q(
                        ("tipo", "deposito"),
                        ("destino__isnull", True),
                        ("cuenta_bancaria__isnull", False),
                        ("fecha_deposito__isnull", False),
                        ("estado__in", ["por_conciliar", "conciliado"]),
                    ),
                    _connector="OR",
                ),
                name="traslado_coherente",
            ),
        ),
    ]
