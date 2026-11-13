from django.db import migrations

DENOMINACIONES = (100000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100, 50)


def caja_inicial(apps, schema_editor):
    Negocio = apps.get_model("configuracion", "Negocio")
    Caja = apps.get_model("caja", "Caja")
    Denominacion = apps.get_model("caja", "Denominacion")
    if not Negocio.objects.filter(configurado=True).exists():
        return
    if not Caja.objects.exists():
        Caja.objects.create(nombre="Caja 1")
    if not Denominacion.objects.exists():
        for valor in DENOMINACIONES:
            Denominacion.objects.create(valor=valor)


class Migration(migrations.Migration):
    dependencies = [("caja", "0001_initial"), ("configuracion", "0005_fase2")]

    operations = [migrations.RunPython(caja_inicial, migrations.RunPython.noop)]
