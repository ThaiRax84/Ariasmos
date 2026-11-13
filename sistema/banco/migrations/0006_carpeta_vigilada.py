import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banco", "0005_otra_via"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ArchivoVigilado",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nombre", models.CharField(max_length=255, unique=True)),
                ("tamano", models.BigIntegerField()),
                ("modificado", models.BigIntegerField()),
                ("visto_en", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["nombre"],
            },
        ),
        migrations.AddField(
            model_name="importacion",
            name="liberada_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="importacion",
            name="liberada_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="importacion",
            name="origen",
            field=models.CharField(
                choices=[
                    ("manual", "Subida por una persona"),
                    ("carpeta", "Carpeta vigilada"),
                ],
                default="manual",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="importacion",
            name="retenida",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="importacion",
            name="creada_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="importacion",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("origen", "carpeta"),
                    ("creada_por__isnull", False),
                    _connector="OR",
                ),
                name="importacion_con_responsable",
            ),
        ),
    ]
