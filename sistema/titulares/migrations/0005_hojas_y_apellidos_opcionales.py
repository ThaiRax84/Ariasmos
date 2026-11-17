import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("solicitudes", "0010_importacion_padron"),
        ("titulares", "0004_cuenta_interna"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="lotepadron",
            name="actualizados",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="lotepadron",
            name="autorizado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="lotepadron",
            name="saltados",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="lotepadron",
            name="solicitud",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="solicitudes.solicitud",
            ),
        ),
        migrations.AlterField(
            model_name="titular",
            name="apellidos",
            field=models.CharField(blank=True, max_length=150),
        ),
    ]
