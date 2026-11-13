import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banco", "0006_carpeta_vigilada"),
        ("caja", "0004_piezas_arqueo_y_retiros"),
        ("cobros", "0006_fecha_banco_de_referencia"),
        ("solicitudes", "0006_retiros_en_instalaciones"),
        ("titulares", "0003_lote_padron"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="pago",
            name="registrado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="pago",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("registrado_por__isnull", False),
                    models.Q(("medio", "banco"), ("movimiento__isnull", False)),
                    _connector="OR",
                ),
                name="pago_con_responsable",
            ),
        ),
    ]
