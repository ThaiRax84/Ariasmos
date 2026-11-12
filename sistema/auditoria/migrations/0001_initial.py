from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Evento",
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
                ("momento", models.DateTimeField()),
                ("usuario_texto", models.CharField(blank=True, max_length=150)),
                ("accion", models.CharField(db_index=True, max_length=60)),
                ("objeto_tipo", models.CharField(blank=True, max_length=60)),
                ("objeto_id", models.CharField(blank=True, max_length=40)),
                ("datos", models.JSONField(blank=True, default=dict)),
                ("ip", models.CharField(blank=True, max_length=45)),
                (
                    "hash_anterior",
                    models.CharField(
                        default="0000000000000000000000000000000000000000000000000000000000000000",
                        max_length=64,
                        unique=True,
                    ),
                ),
                ("hash", models.CharField(max_length=64, unique=True)),
            ],
            options={
                "ordering": ["-id"],
            },
        ),
    ]
