from django.db import migrations


def poblar(apps, schema_editor):
    from banco.catalogo import cargar, sembrar_medios

    cargar(apps.get_model("banco", "Banco"))
    sembrar_medios(apps.get_model("banco", "MedioPago"))


class Migration(migrations.Migration):
    dependencies = [("banco", "0001_initial")]

    operations = [migrations.RunPython(poblar, migrations.RunPython.noop)]
