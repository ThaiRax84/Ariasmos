import django.db.models.deletion
import django.db.models.expressions
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("caja", "0001_initial"),
        ("cobros", "0002_initial"),
        ("solicitudes", "0003_correccion_nombre"),
        ("titulares", "0002_familias"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Beca",
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
                ("puntos_base", models.PositiveIntegerField()),
                ("vigente_desde", models.DateField()),
                ("vigente_hasta", models.DateField(blank=True, null=True)),
                ("motivo", models.CharField(max_length=300)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                (
                    "autorizada_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "concepto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="becas",
                        to="cobros.conceptocobro",
                    ),
                ),
                (
                    "creada_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "solicitud",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="solicitudes.solicitud",
                    ),
                ),
                (
                    "titular",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="becas",
                        to="titulares.titular",
                    ),
                ),
            ],
            options={
                "ordering": ["-vigente_desde", "-id"],
            },
        ),
        migrations.CreateModel(
            name="Cargo",
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
                ("periodo", models.CharField(blank=True, max_length=7)),
                ("descripcion", models.CharField(blank=True, max_length=200)),
                ("cantidad", models.PositiveIntegerField(default=1)),
                ("importe_original", models.PositiveBigIntegerField()),
                ("descuento", models.PositiveBigIntegerField(default=0)),
                ("importe_final", models.PositiveBigIntegerField()),
                ("vencimiento", models.DateField()),
                (
                    "origen",
                    models.CharField(
                        choices=[
                            ("automatico", "Automático"),
                            ("manual", "Manual"),
                            ("recargo", "Recargo"),
                            ("saldo_inicial", "Saldo inicial"),
                        ],
                        max_length=15,
                    ),
                ),
                ("fecha_recargo", models.DateField(blank=True, null=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                (
                    "beca",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cargos",
                        to="cobros.beca",
                    ),
                ),
                (
                    "cargo_base",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="recargos",
                        to="cobros.cargo",
                    ),
                ),
                (
                    "concepto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cargos",
                        to="cobros.conceptocobro",
                    ),
                ),
                (
                    "creado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "titular",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cargos",
                        to="titulares.titular",
                    ),
                ),
            ],
            options={
                "ordering": ["vencimiento", "id"],
            },
        ),
        migrations.CreateModel(
            name="CancelacionCargo",
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
                            ("cancelacion", "Cancelación"),
                            ("condonacion", "Condonación de recargo"),
                        ],
                        max_length=12,
                    ),
                ),
                ("importe", models.PositiveBigIntegerField()),
                ("motivo", models.CharField(max_length=300)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                (
                    "autorizada_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ejecutada_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "solicitud",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="solicitudes.solicitud",
                    ),
                ),
                (
                    "cargo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cancelaciones",
                        to="cobros.cargo",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="Pago",
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
                ("importe", models.PositiveBigIntegerField()),
                (
                    "medio",
                    models.CharField(
                        choices=[
                            ("efectivo", "Efectivo"),
                            ("banco", "Banco"),
                            ("saldo_inicial", "Saldo inicial"),
                        ],
                        max_length=15,
                    ),
                ),
                ("fecha", models.DateTimeField(auto_now_add=True)),
                (
                    "ficha",
                    models.CharField(blank=True, max_length=64, null=True, unique=True),
                ),
                (
                    "registrado_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "solicitud",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="solicitudes.solicitud",
                    ),
                ),
                (
                    "titular",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pagos",
                        to="titulares.titular",
                    ),
                ),
                (
                    "turno",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pagos",
                        to="caja.turno",
                    ),
                ),
            ],
            options={
                "ordering": ["fecha", "id"],
            },
        ),
        migrations.CreateModel(
            name="Aplicacion",
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
                ("importe", models.PositiveBigIntegerField()),
                ("creada", models.DateTimeField(auto_now_add=True)),
                (
                    "cargo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="aplicaciones",
                        to="cobros.cargo",
                    ),
                ),
                (
                    "pago",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="aplicaciones",
                        to="cobros.pago",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="Prorroga",
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
                ("fecha_limite", models.DateField()),
                ("motivo", models.CharField(max_length=300)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                (
                    "autorizada_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "cargo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="prorrogas",
                        to="cobros.cargo",
                    ),
                ),
                (
                    "creada_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "solicitud",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="solicitudes.solicitud",
                    ),
                ),
            ],
            options={
                "ordering": ["-fecha_limite", "-id"],
            },
        ),
        migrations.CreateModel(
            name="Recibo",
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
                ("serie", models.CharField(max_length=10)),
                ("folio", models.PositiveBigIntegerField()),
                ("codigo", models.CharField(max_length=11)),
                ("emitido", models.DateTimeField(auto_now_add=True)),
                (
                    "pago",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="recibo",
                        to="cobros.pago",
                    ),
                ),
            ],
            options={
                "ordering": ["serie", "folio"],
            },
        ),
        migrations.CreateModel(
            name="ReversionPago",
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
                ("motivo", models.CharField(max_length=300)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                (
                    "autorizada_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ejecutada_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "pago",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reversion",
                        to="cobros.pago",
                    ),
                ),
                (
                    "solicitud",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="solicitudes.solicitud",
                    ),
                ),
                (
                    "turno",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="devoluciones",
                        to="caja.turno",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="SerieRecibo",
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
                ("nombre", models.CharField(max_length=10, unique=True)),
                ("siguiente", models.PositiveBigIntegerField(default=1)),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("siguiente__gte", 1)),
                        name="serie_siguiente_positivo",
                    )
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="beca",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("puntos_base__gte", 1), ("puntos_base__lte", 10000)
                ),
                name="beca_porcentaje_valido",
            ),
        ),
        migrations.AddConstraint(
            model_name="beca",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("vigente_hasta__isnull", True),
                    ("vigente_hasta__gte", models.F("vigente_desde")),
                    _connector="OR",
                ),
                name="beca_vigencia_valida",
            ),
        ),
        migrations.AddConstraint(
            model_name="cargo",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "importe_final",
                        django.db.models.expressions.CombinedExpression(
                            models.F("importe_original"), "-", models.F("descuento")
                        ),
                    )
                ),
                name="cargo_importe_final",
            ),
        ),
        migrations.AddConstraint(
            model_name="cargo",
            constraint=models.CheckConstraint(
                condition=models.Q(("descuento__lte", models.F("importe_original"))),
                name="cargo_descuento_menor",
            ),
        ),
        migrations.AddConstraint(
            model_name="cargo",
            constraint=models.CheckConstraint(
                condition=models.Q(("cantidad__gte", 1)), name="cargo_cantidad_positiva"
            ),
        ),
        migrations.AddConstraint(
            model_name="cargo",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("origen", "recargo"),
                        ("cargo_base__isnull", False),
                        ("fecha_recargo__isnull", False),
                    ),
                    models.Q(
                        models.Q(("origen", "recargo"), _negated=True),
                        ("cargo_base__isnull", True),
                        ("fecha_recargo__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="cargo_recargo_ligado",
            ),
        ),
        migrations.AddConstraint(
            model_name="cargo",
            constraint=models.UniqueConstraint(
                condition=models.Q(("origen", "recargo")),
                fields=("cargo_base", "fecha_recargo"),
                name="cargo_recargo_unico",
            ),
        ),
        migrations.AddConstraint(
            model_name="cargo",
            constraint=models.UniqueConstraint(
                condition=models.Q(("origen", "automatico")),
                fields=("titular", "concepto", "periodo"),
                name="cargo_automatico_unico",
            ),
        ),
        migrations.AddConstraint(
            model_name="cancelacioncargo",
            constraint=models.CheckConstraint(
                condition=models.Q(("importe__gt", 0)),
                name="cancelacion_importe_positivo",
            ),
        ),
        migrations.AddConstraint(
            model_name="pago",
            constraint=models.CheckConstraint(
                condition=models.Q(("importe__gt", 0)), name="pago_importe_positivo"
            ),
        ),
        migrations.AddConstraint(
            model_name="pago",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("medio", "efectivo"), _negated=True),
                    ("turno__isnull", False),
                    _connector="OR",
                ),
                name="pago_efectivo_con_turno",
            ),
        ),
        migrations.AddConstraint(
            model_name="aplicacion",
            constraint=models.CheckConstraint(
                condition=models.Q(("importe__gt", 0)),
                name="aplicacion_importe_positivo",
            ),
        ),
        migrations.AddConstraint(
            model_name="recibo",
            constraint=models.UniqueConstraint(
                fields=("serie", "folio"), name="recibo_folio_unico"
            ),
        ),
        migrations.AddConstraint(
            model_name="recibo",
            constraint=models.CheckConstraint(
                condition=models.Q(("folio__gte", 1)), name="recibo_folio_positivo"
            ),
        ),
    ]
