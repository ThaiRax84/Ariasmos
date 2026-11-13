from django.conf import settings
from django.db import migrations, models

from nucleo import sobre


def cifrar(apps, schema_editor):
    clave = bytes(getattr(settings, "CLAVE_SECRETOS", b"") or b"")
    if len(clave) != sobre.LARGO_CLAVE:
        return
    derivada = sobre.derivar(clave, "totp")
    Usuario = apps.get_model("cuentas", "Usuario")
    for usuario in Usuario.objects.exclude(totp_cifrado="").only("pk", "totp_cifrado"):
        if not sobre.esta_cifrado(usuario.totp_cifrado):
            Usuario.objects.filter(pk=usuario.pk).update(totp_cifrado=sobre.cifrar_texto(derivada, usuario.totp_cifrado, f"totp|{usuario.pk}"))


class Migration(migrations.Migration):
    dependencies = [("cuentas", "0003_codigo_activacion")]

    operations = [
        migrations.RenameField(model_name="usuario", old_name="totp_secreto", new_name="totp_cifrado"),
        migrations.AlterField(model_name="usuario", name="totp_cifrado", field=models.CharField(blank=True, max_length=255)),
        migrations.RunPython(cifrar, migrations.RunPython.noop),
    ]
