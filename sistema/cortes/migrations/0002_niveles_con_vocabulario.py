from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cortes", "0001_inicial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="definicioncorte",
            name="nivel",
            field=models.CharField(
                choices=[
                    ("completo", "Completo"),
                    ("solo_nombres", "Solo nombres"),
                    ("sin_nombres", "Sin nombres"),
                ],
                default="solo_nombres",
                max_length=15,
            ),
        ),
        migrations.AlterField(
            model_name="entrega",
            name="nivel",
            field=models.CharField(
                choices=[
                    ("completo", "Completo"),
                    ("solo_nombres", "Solo nombres"),
                    ("sin_nombres", "Sin nombres"),
                ],
                max_length=15,
            ),
        ),
        migrations.AlterField(
            model_name="regladestino",
            name="nivel",
            field=models.CharField(
                choices=[
                    ("completo", "Completo"),
                    ("solo_nombres", "Solo nombres"),
                    ("sin_nombres", "Sin nombres"),
                ],
                default="solo_nombres",
                max_length=15,
            ),
        ),
    ]
