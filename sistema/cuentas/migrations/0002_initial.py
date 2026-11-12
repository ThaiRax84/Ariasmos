import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("cuentas", "0001_initial"),
        ("solicitudes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="codigousado",
            name="solicitud",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="codigos",
                to="solicitudes.solicitud",
            ),
        ),
        migrations.AddField(
            model_name="codigousado",
            name="usado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="delegacion",
            name="otorgante",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="delegaciones_otorgadas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="delegacion",
            name="receptor",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="delegaciones",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="delegacion",
            name="revocada_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="dispositivo",
            name="aprobado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="dispositivo",
            name="revocado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="permisorol",
            name="rol",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="asignaciones",
                to="cuentas.rol",
            ),
        ),
        migrations.AddField(
            model_name="usuario",
            name="rol",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="usuarios",
                to="cuentas.rol",
            ),
        ),
        migrations.AddConstraint(
            model_name="codigousado",
            constraint=models.UniqueConstraint(
                fields=("autorizador", "paso"), name="codigo_un_solo_uso"
            ),
        ),
        migrations.AddConstraint(
            model_name="delegacion",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("vence__isnull", False),
                    ("usos_maximos__isnull", False),
                    _connector="OR",
                ),
                name="delegacion_con_limite",
            ),
        ),
        migrations.AddConstraint(
            model_name="delegacion",
            constraint=models.CheckConstraint(
                condition=models.Q(("otorgante", models.F("receptor")), _negated=True),
                name="delegacion_a_otro",
            ),
        ),
        migrations.AddConstraint(
            model_name="permisorol",
            constraint=models.UniqueConstraint(
                fields=("rol", "permiso"), name="permiso_rol_unico"
            ),
        ),
    ]
