import django.db.models.deletion
import django.db.models.expressions
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("banco", "0002_catalogo_y_medios"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Caja",
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
                ("serie_recibos", models.CharField(default="A", max_length=10)),
                ("activa", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["nombre"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("serie_recibos__regex", "^[A-Z0-9]{1,10}$")
                        ),
                        name="caja_serie_valida",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Denominacion",
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
                ("valor", models.PositiveIntegerField(unique=True)),
                ("activa", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["-valor"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("valor__gt", 0)),
                        name="denominacion_positiva",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Turno",
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
                ("fondo_inicial", models.PositiveBigIntegerField(default=0)),
                (
                    "estado",
                    models.CharField(
                        choices=[("abierto", "Abierto"), ("cerrado", "Cerrado")],
                        default="abierto",
                        max_length=10,
                    ),
                ),
                ("abierto_en", models.DateTimeField(auto_now_add=True)),
                ("cerrado_en", models.DateTimeField(blank=True, null=True)),
                (
                    "caja",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="turnos",
                        to="caja.caja",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="turnos",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-abierto_en"],
            },
        ),
        migrations.CreateModel(
            name="Arqueo",
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
                ("conteo", models.JSONField(default=dict)),
                ("contado", models.PositiveBigIntegerField()),
                ("esperado", models.PositiveBigIntegerField()),
                ("diferencia", models.BigIntegerField()),
                ("nota", models.CharField(blank=True, max_length=500)),
                ("supera_umbral", models.BooleanField(default=False)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                (
                    "turno",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="arqueo",
                        to="caja.turno",
                    ),
                ),
            ],
            options={
                "ordering": ["-creado"],
            },
        ),
        migrations.CreateModel(
            name="Traslado",
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
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("entrega", "Entrega"),
                            ("deposito", "Depósito bancario"),
                        ],
                        max_length=10,
                    ),
                ),
                ("importe", models.PositiveBigIntegerField()),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("pendiente", "Pendiente de confirmar"),
                            ("confirmado", "Confirmado"),
                            ("rechazado", "Rechazado"),
                            ("por_conciliar", "Por conciliar"),
                        ],
                        max_length=15,
                    ),
                ),
                ("nota", models.CharField(blank=True, max_length=300)),
                ("referencia", models.CharField(blank=True, max_length=60)),
                ("fecha_deposito", models.DateField(blank=True, null=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("resuelto_en", models.DateTimeField(blank=True, null=True)),
                (
                    "cuenta_bancaria",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="banco.cuentabancaria",
                    ),
                ),
                (
                    "destino",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="traslados_recibidos",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "origen",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="traslados_enviados",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-creado"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("importe__gt", 0)),
                        name="traslado_importe_positivo",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("origen", models.F("destino")), _negated=True
                        ),
                        name="traslado_a_otra_persona",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("tipo", "entrega"),
                                ("destino__isnull", False),
                                (
                                    "estado__in",
                                    ["pendiente", "confirmado", "rechazado"],
                                ),
                            ),
                            models.Q(
                                ("tipo", "deposito"),
                                ("destino__isnull", True),
                                ("cuenta_bancaria__isnull", False),
                                ("fecha_deposito__isnull", False),
                                ("estado", "por_conciliar"),
                            ),
                            _connector="OR",
                        ),
                        name="traslado_coherente",
                    ),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="turno",
            constraint=models.UniqueConstraint(
                condition=models.Q(("estado", "abierto")),
                fields=("usuario",),
                name="turno_uno_abierto_por_persona",
            ),
        ),
        migrations.AddConstraint(
            model_name="turno",
            constraint=models.UniqueConstraint(
                condition=models.Q(("estado", "abierto")),
                fields=("caja",),
                name="turno_uno_abierto_por_caja",
            ),
        ),
        migrations.AddConstraint(
            model_name="turno",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("cerrado_en__isnull", True), ("estado", "abierto")),
                    models.Q(("cerrado_en__isnull", False), ("estado", "cerrado")),
                    _connector="OR",
                ),
                name="turno_cierre_coherente",
            ),
        ),
        migrations.AddConstraint(
            model_name="arqueo",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "diferencia",
                        django.db.models.expressions.CombinedExpression(
                            models.F("contado"), "-", models.F("esperado")
                        ),
                    )
                ),
                name="arqueo_diferencia_coherente",
            ),
        ),
    ]
