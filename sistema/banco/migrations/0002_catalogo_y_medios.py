from django.db import migrations


def poblar(apps, schema_editor):
    from banco.catalogo import cargar

    cargar(apps.get_model("banco", "Banco"))


class Migration(migrations.Migration):
    dependencies = [("banco", "0001_initial")]

    operations = [migrations.RunPython(poblar, migrations.RunPython.noop)]
