from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cobros", "0008_medio_devolucion"),
        ("titulares", "0003_lote_padron"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="titular",
            options={
                "default_manager_name": "objects",
                "ordering": ["apellidos", "nombre"],
            },
        ),
        migrations.AddField(
            model_name="titular",
            name="interno",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddConstraint(
            model_name="titular",
            constraint=models.UniqueConstraint(
                condition=models.Q(("interno", True)),
                fields=("interno",),
                name="titular_una_cuenta_interna",
            ),
        ),
        migrations.AddConstraint(
            model_name="titular",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("interno", False),
                    models.Q(("estado", "activo"), ("familia__isnull", True)),
                    _connector="OR",
                ),
                name="titular_interno_activo_sin_familia",
            ),
        ),
    ]
