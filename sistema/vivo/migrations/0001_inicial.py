from django.db import migrations, models


def sembrar(apps, schema_editor):
    Contador = apps.get_model("vivo", "Contador")
    for tema in ("cobros", "transferencias", "titulares", "solicitudes", "caja", "banco", "inventario"):
        Contador.objects.get_or_create(tema=tema)


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Contador",
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
                ("tema", models.CharField(max_length=20, unique=True)),
                ("valor", models.PositiveBigIntegerField(default=0)),
            ],
            options={
                "ordering": ["tema"],
            },
        ),
        migrations.RunPython(sembrar, migrations.RunPython.noop),
    ]
