from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banco", "0009_cuenta_clabe_u_otra"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="importacion",
            name="importacion_con_responsable",
        ),
        migrations.AlterField(
            model_name="importacion",
            name="origen",
            field=models.CharField(
                choices=[
                    ("manual", "Subida por una persona"),
                    ("carpeta", "Carpeta vigilada"),
                    ("aviso", "Aviso de llegada"),
                ],
                default="manual",
                max_length=10,
            ),
        ),
        migrations.AddConstraint(
            model_name="importacion",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("origen__in", ("carpeta", "aviso")),
                    ("creada_por__isnull", False),
                    _connector="OR",
                ),
                name="importacion_con_responsable",
            ),
        ),
    ]
