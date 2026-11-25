from django.db import migrations

DE_FABRICA = (
    (
        "recibo",
        "Recibo de pago",
        "Hola [nombre], recibimos tu pago de [importe]. Aquí está tu recibo.",
        True,
    ),
    (
        "recordatorio",
        "Recordatorio de pago",
        "Hola [nombre], te recordamos que [concepto] vence el [fecha].",
        False,
    ),
    (
        "atraso",
        "Pago atrasado",
        "Hola [nombre], [concepto] venció hace [dias] días. Saldo: [adeudo].",
        False,
    ),
    (
        "sin_acceso",
        "Sin acceso por adeudo",
        "Hola [nombre], por el adeudo de [adeudo] no podemos dar acceso a [alumno].",
        False,
    ),
)


def crear(apps, schema_editor):
    PlantillaMensaje = apps.get_model("mensajes", "PlantillaMensaje")
    for clave, nombre, texto, con_documento in DE_FABRICA:
        PlantillaMensaje.objects.get_or_create(
            clave=clave,
            defaults={
                "nombre": nombre,
                "texto": texto,
                "con_documento": con_documento,
                "estado": "borrador",
            },
        )


def quitar(apps, schema_editor):
    apps.get_model("mensajes", "PlantillaMensaje").objects.filter(
        clave__in=[c for c, *_ in DE_FABRICA], estado="borrador"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("mensajes", "0001_initial")]

    operations = [migrations.RunPython(crear, quitar)]
