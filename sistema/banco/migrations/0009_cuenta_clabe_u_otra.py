import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banco", "0008_topes_del_banco"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="cuentabancaria",
            name="cuenta_bancaria_clabe_18",
        ),
        migrations.AddField(
            model_name="cuentabancaria",
            name="banco_nombre",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="cuentabancaria",
            name="tipo",
            field=models.CharField(
                choices=[("clabe", "CLABE"), ("otra", "Otra cuenta")],
                default="clabe",
                max_length=5,
            ),
        ),
        migrations.AlterField(
            model_name="cargatemporal",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("banco_pdf", "Estado de cuenta"),
                    ("banco_archivo", "Archivo de movimientos"),
                    ("padron", "Importación de registros"),
                ],
                max_length=14,
            ),
        ),
        migrations.AlterField(
            model_name="cuentabancaria",
            name="banco",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cuentas",
                to="banco.banco",
            ),
        ),
        migrations.AlterField(
            model_name="cuentabancaria",
            name="clabe",
            field=models.CharField(blank=True, max_length=18),
        ),
        migrations.AlterField(
            model_name="cuentabancaria",
            name="numero_cuenta",
            field=models.CharField(blank=True, max_length=34),
        ),
        migrations.AddConstraint(
            model_name="cuentabancaria",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("tipo", "clabe"),
                        ("clabe__regex", "^[0-9]{18}$"),
                        ("banco__isnull", False),
                    ),
                    models.Q(
                        ("tipo", "otra"),
                        ("clabe", ""),
                        models.Q(("numero_cuenta", ""), _negated=True),
                        models.Q(("banco_nombre", ""), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="cuenta_bancaria_clabe_u_otra",
            ),
        ),
    ]
