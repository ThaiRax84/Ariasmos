from django.db import migrations, models


def conservar_instrucciones(apps, schema_editor):
    Negocio = apps.get_model("configuracion", "Negocio")
    for negocio in Negocio.objects.exclude(instrucciones_pago=""):
        Negocio.objects.filter(pk=negocio.pk).update(nota_ficha=negocio.instrucciones_pago)


class Migration(migrations.Migration):
    dependencies = [("configuracion", "0003_codigo_activacion")]

    operations = [
        migrations.AddField(model_name="negocio", name="nota_ficha", field=models.TextField(blank=True)),
        migrations.RunPython(conservar_instrucciones, migrations.RunPython.noop),
        migrations.RemoveField(model_name="negocio", name="instrucciones_pago"),
    ]
