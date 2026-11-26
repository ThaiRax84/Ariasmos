from django.db import migrations

DE_FABRICA = (
    ("pago", 0, "recibo"),
    ("antes", 3, "recordatorio"),
    ("atraso", 5, "atraso"),
    ("atraso", 15, "sin_acceso"),
)


def crear(apps, schema_editor):
    Aviso = apps.get_model("mensajes", "Aviso")
    Plantilla = apps.get_model("mensajes", "PlantillaMensaje")
    for momento, dias, clave in DE_FABRICA:
        Aviso.objects.get_or_create(
            momento=momento,
            dias=dias,
            plantilla=Plantilla.objects.get(clave=clave),
            defaults={"activo": False},
        )


def quitar(apps, schema_editor):
    apps.get_model("mensajes", "Aviso").objects.filter(
        activo=False, plantilla__clave__in=[c for *_, c in DE_FABRICA]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("mensajes", "0004_avisos_automaticos")]

    operations = [migrations.RunPython(crear, quitar)]
