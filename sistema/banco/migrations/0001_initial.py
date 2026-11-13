import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MedioPago",
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
                ("nombre", models.CharField(max_length=60, unique=True)),
                ("orden", models.PositiveSmallIntegerField(default=10)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["orden", "nombre"],
            },
        ),
        migrations.CreateModel(
            name="Banco",
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
                ("clave", models.CharField(max_length=3, unique=True)),
                ("nombre", models.CharField(max_length=80)),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("banco", "Banco"),
                            ("no_bancario", "Institución no bancaria"),
                            ("banca_desarrollo", "Banca de desarrollo"),
                            ("otro", "Otro"),
                        ],
                        default="banco",
                        max_length=20,
                    ),
                ),
                (
                    "soporte",
                    models.CharField(
                        choices=[
                            ("archivo_verificado", "Archivo verificado"),
                            ("archivo_generico", "Archivo genérico"),
                            ("convenio", "Convenio"),
                            ("sin_probar", "Sin probar"),
                        ],
                        default="sin_probar",
                        max_length=20,
                    ),
                ),
                ("activo", models.BooleanField(default=True)),
                ("capturado_a_mano", models.BooleanField(default=False)),
            ],
            options={
                "ordering": ["nombre"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("clave__regex", "^[0-9]{3}$")),
                        name="banco_clave_tres_digitos",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="CuentaBancaria",
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
                ("clabe", models.CharField(max_length=18)),
                ("beneficiario", models.CharField(max_length=150)),
                ("numero_cuenta", models.CharField(blank=True, max_length=30)),
                ("convenio", models.CharField(blank=True, max_length=30)),
                (
                    "referencia_en",
                    models.CharField(
                        choices=[
                            ("ambos", "Referencia numérica y concepto"),
                            ("numerica", "Solo referencia numérica"),
                            ("concepto", "Solo concepto"),
                        ],
                        default="ambos",
                        max_length=10,
                    ),
                ),
                ("contacto_dudas", models.CharField(blank=True, max_length=150)),
                ("nota_adicional", models.TextField(blank=True)),
                ("principal", models.BooleanField(default=False)),
                ("activa", models.BooleanField(default=True)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                (
                    "banco",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cuentas",
                        to="banco.banco",
                    ),
                ),
                (
                    "medios",
                    models.ManyToManyField(
                        blank=True, related_name="cuentas", to="banco.mediopago"
                    ),
                ),
            ],
            options={
                "ordering": ["-principal", "banco__nombre"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("principal", True)),
                        fields=("principal",),
                        name="cuenta_bancaria_una_principal",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("clabe__regex", "^[0-9]{18}$")),
                        name="cuenta_bancaria_clabe_18",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("principal", False), ("activa", True), _connector="OR"
                        ),
                        name="cuenta_bancaria_principal_activa",
                    ),
                ],
            },
        ),
    ]
