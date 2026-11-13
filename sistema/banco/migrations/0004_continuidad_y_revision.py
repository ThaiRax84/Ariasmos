import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banco", "0003_importacion"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="importacion",
            name="continuidad",
            field=models.CharField(
                choices=[
                    ("verificada", "Verificada: continúa el estado anterior"),
                    ("primera", "Primera de la cuenta"),
                    ("con_hueco", "Con hueco: hay días sin importar"),
                    ("no_verificable", "No verificable: archivo editable"),
                ],
                default="con_hueco",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="importacion",
            name="revisada_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="importacion",
            name="revisada_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
