import django.db.models.deletion
from django.db import migrations, models


def activo_desde(apps, schema_editor):
    Titular = apps.get_model("titulares", "Titular")
    for titular in Titular.objects.filter(estado="activo", activo_desde__isnull=True):
        Titular.objects.filter(pk=titular.pk).update(activo_desde=titular.creado.date())


class Migration(migrations.Migration):

    dependencies = [
        ("titulares", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Familia",
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
                ("nombre", models.CharField(max_length=100)),
                ("activa", models.BooleanField(default=True)),
                ("creada", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["nombre"],
            },
        ),
        migrations.RemoveConstraint(
            model_name="contacto",
            name="contacto_un_principal",
        ),
        migrations.AddField(
            model_name="titular",
            name="activo_desde",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="contacto",
            name="titular",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="contactos",
                to="titulares.titular",
            ),
        ),
        migrations.AddField(
            model_name="contacto",
            name="familia",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="contactos",
                to="titulares.familia",
            ),
        ),
        migrations.AddField(
            model_name="titular",
            name="familia",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="miembros",
                to="titulares.familia",
            ),
        ),
        migrations.AddConstraint(
            model_name="contacto",
            constraint=models.UniqueConstraint(
                condition=models.Q(("principal", True), ("titular__isnull", False)),
                fields=("titular",),
                name="contacto_un_principal",
            ),
        ),
        migrations.AddConstraint(
            model_name="contacto",
            constraint=models.UniqueConstraint(
                condition=models.Q(("familia__isnull", False), ("principal", True)),
                fields=("familia",),
                name="contacto_familia_un_principal",
            ),
        ),
        migrations.AddConstraint(
            model_name="contacto",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("titular__isnull", False), ("familia__isnull", True)),
                    models.Q(("titular__isnull", True), ("familia__isnull", False)),
                    _connector="OR",
                ),
                name="contacto_de_titular_o_familia",
            ),
        ),
        migrations.RunPython(activo_desde, migrations.RunPython.noop),
    ]
