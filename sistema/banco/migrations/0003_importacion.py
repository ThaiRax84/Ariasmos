import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banco", "0002_catalogo_y_medios"),
        ("caja", "0002_caja_inicial"),
        ("cobros", "0004_sin_descuento_de_plan"),
        ("titulares", "0002_familias"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CargaTemporal",
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
                ("token", models.CharField(max_length=43, unique=True)),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("banco_pdf", "Estado de cuenta"),
                            ("banco_archivo", "Archivo de movimientos"),
                            ("padron", "Padrón"),
                        ],
                        max_length=14,
                    ),
                ),
                ("nombre_archivo", models.CharField(max_length=120)),
                ("sha256", models.CharField(max_length=64)),
                ("datos", models.JSONField(default=dict)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Importacion",
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
                ("nombre_archivo", models.CharField(max_length=120)),
                ("sha256", models.CharField(db_index=True, max_length=64)),
                (
                    "adaptador",
                    models.CharField(
                        choices=[
                            ("estado_pdf", "Estado de cuenta en PDF"),
                            ("archivo", "Archivo de movimientos"),
                        ],
                        max_length=12,
                    ),
                ),
                ("periodo_inicio", models.DateField(blank=True, null=True)),
                ("periodo_fin", models.DateField(blank=True, null=True)),
                ("saldo_inicial", models.BigIntegerField(blank=True, null=True)),
                ("saldo_final", models.BigIntegerField(blank=True, null=True)),
                ("depositos", models.BigIntegerField(default=0)),
                ("retiros", models.BigIntegerField(default=0)),
                ("movimientos", models.PositiveIntegerField(default=0)),
                ("nuevos", models.PositiveIntegerField(default=0)),
                ("duplicados", models.PositiveIntegerField(default=0)),
                ("aplicados", models.PositiveIntegerField(default=0)),
                ("sugeridos", models.PositiveIntegerField(default=0)),
                ("sin_pista", models.PositiveIntegerField(default=0)),
                ("depositos_emparejados", models.PositiveIntegerField(default=0)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                (
                    "creada_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "cuenta",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="importaciones",
                        to="banco.cuentabancaria",
                    ),
                ),
            ],
            options={
                "ordering": ["-creada", "-id"],
            },
        ),
        migrations.CreateModel(
            name="MapeoColumnas",
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
                ("mapeo", models.JSONField(default=dict)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                (
                    "cuenta",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mapeo",
                        to="banco.cuentabancaria",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ReglaPagador",
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
                ("cuenta_pagador", models.CharField(max_length=18, unique=True)),
                ("confirmaciones", models.PositiveIntegerField(default=0)),
                ("ultima_vez", models.DateTimeField(blank=True, null=True)),
                ("activa", models.BooleanField(default=True)),
                (
                    "titular",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reglas_pagador",
                        to="titulares.titular",
                    ),
                ),
            ],
            options={
                "ordering": ["cuenta_pagador"],
            },
        ),
        migrations.CreateModel(
            name="MovimientoBancario",
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
                ("fecha", models.DateField()),
                ("folio", models.CharField(blank=True, max_length=40)),
                ("descripcion", models.CharField(blank=True, max_length=300)),
                ("importe", models.PositiveBigIntegerField()),
                ("saldo", models.BigIntegerField(blank=True, null=True)),
                (
                    "sentido",
                    models.CharField(
                        choices=[("abono", "Abono"), ("cargo", "Cargo")], max_length=6
                    ),
                ),
                (
                    "clase",
                    models.CharField(
                        choices=[
                            ("spei", "SPEI"),
                            ("mismo_banco", "Mismo banco"),
                            ("efectivo", "Depósito en efectivo"),
                            ("devolucion", "Devolución"),
                            ("otro", "Otro"),
                            ("archivo", "Abono"),
                        ],
                        max_length=12,
                    ),
                ),
                ("hora", models.CharField(blank=True, max_length=8)),
                ("banco_origen", models.CharField(blank=True, max_length=80)),
                (
                    "cuenta_pagador",
                    models.CharField(blank=True, db_index=True, max_length=18),
                ),
                ("nombre_pagador", models.CharField(blank=True, max_length=150)),
                ("rastreo", models.CharField(blank=True, max_length=40)),
                ("referencia", models.CharField(blank=True, max_length=40)),
                ("concepto", models.CharField(blank=True, max_length=200)),
                ("huella", models.CharField(max_length=400, unique=True)),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("aplicado", "Aplicado"),
                            ("por_identificar", "Por identificar"),
                            ("conciliado", "Depósito de caja conciliado"),
                            ("no_cobro", "No es un cobro"),
                            ("informativo", "Informativo"),
                        ],
                        max_length=16,
                    ),
                ),
                ("sugerencia", models.CharField(blank=True, max_length=12)),
                ("alternativas", models.JSONField(blank=True, default=list)),
                ("motivo", models.CharField(blank=True, max_length=40)),
                ("coincide_importe", models.BooleanField(default=False)),
                ("propuesta_en", models.DateTimeField(blank=True, null=True)),
                ("nota", models.CharField(blank=True, max_length=300)),
                ("resuelto_en", models.DateTimeField(blank=True, null=True)),
                (
                    "cuenta",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movimientos",
                        to="banco.cuentabancaria",
                    ),
                ),
                (
                    "importacion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="lista",
                        to="banco.importacion",
                    ),
                ),
                (
                    "pago",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="cobros.pago",
                    ),
                ),
                (
                    "propuesta",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="titulares.titular",
                    ),
                ),
                (
                    "propuesta_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "resuelto_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "traslado",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movimiento",
                        to="caja.traslado",
                    ),
                ),
            ],
            options={
                "ordering": ["fecha", "id"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("importe__gt", 0)),
                        name="movimiento_importe_positivo",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("estado", "aplicado"), _negated=True),
                            ("pago__isnull", False),
                            _connector="OR",
                        ),
                        name="movimiento_aplicado_con_pago",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("estado", "conciliado"), _negated=True),
                            ("traslado__isnull", False),
                            _connector="OR",
                        ),
                        name="movimiento_conciliado_con_traslado",
                    ),
                ],
            },
        ),
    ]
