import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banco", "0006_carpeta_vigilada"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="movimientobancario",
            name="liberado_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="movimientobancario",
            name="liberado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="movimientobancario",
            name="retencion",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="movimientobancario",
            name="sin_respaldo",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="movimientobancario",
            name="sin_respaldo_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
