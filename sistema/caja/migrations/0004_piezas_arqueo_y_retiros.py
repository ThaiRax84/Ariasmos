import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("caja", "0003_deposito_conciliado"),
        ("cobros", "0006_fecha_banco_de_referencia"),
        ("solicitudes", "0004_acciones_fase2"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MotivoRetiro",
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
                ("nombre", models.CharField(max_length=100, unique=True)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["nombre"],
            },
        ),
        migrations.AddField(
            model_name="arqueo",
            name="con_reconteo",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="arqueo",
            name="esperado_piezas",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="arqueo",
            name="primer_contado",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="arqueo",
            name="primer_conteo",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="turno",
            name="propuestas_cambio",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="turno",
            name="rechazos_retiro",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="RetiroCaja",
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
                ("importe", models.PositiveBigIntegerField()),
                ("nota", models.CharField(blank=True, max_length=300)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                (
                    "revision",
                    models.CharField(
                        choices=[
                            ("por_revisar", "Por revisar"),
                            ("revisado", "Revisado"),
                            ("observado", "Observado"),
                        ],
                        default="por_revisar",
                        max_length=12,
                    ),
                ),
                ("revisado_en", models.DateTimeField(blank=True, null=True)),
                ("nota_revision", models.CharField(blank=True, max_length=300)),
                (
                    "comprobante",
                    models.CharField(
                        choices=[
                            ("pendiente", "Comprobante pendiente"),
                            ("adjunto", "Con comprobante"),
                            ("sin_comprobante", "Sin comprobante"),
                        ],
                        default="pendiente",
                        max_length=16,
                    ),
                ),
                (
                    "motivo_sin_comprobante",
                    models.CharField(blank=True, max_length=300),
                ),
                (
                    "autorizado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "caja",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="retiros",
                        to="caja.caja",
                    ),
                ),
                (
                    "motivo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="retiros",
                        to="caja.motivoretiro",
                    ),
                ),
                (
                    "registrado_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="retiros",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "revisado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
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
                    "turno",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="retiros",
                        to="caja.turno",
                    ),
                ),
            ],
            options={
                "ordering": ["-creado", "-id"],
            },
        ),
        migrations.CreateModel(
            name="MovimientoPiezas",
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
                    "origen",
                    models.CharField(
                        choices=[
                            ("apertura", "Fondo de apertura"),
                            ("recibido", "Recibido en un cobro"),
                            ("cambio", "Cambio entregado"),
                            ("retiro", "Retiro de caja"),
                            ("reversion_retiro", "Reversión de retiro"),
                            ("devolucion", "Devolución de un pago"),
                            ("traslado", "Entrega o depósito"),
                        ],
                        max_length=20,
                    ),
                ),
                ("denominacion", models.PositiveIntegerField()),
                ("piezas", models.BigIntegerField()),
                ("creado", models.DateTimeField(auto_now_add=True)),
                (
                    "pago",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="piezas",
                        to="cobros.pago",
                    ),
                ),
                (
                    "reversion",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="piezas",
                        to="cobros.reversionpago",
                    ),
                ),
                (
                    "traslado",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="piezas",
                        to="caja.traslado",
                    ),
                ),
                (
                    "turno",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="piezas",
                        to="caja.turno",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "retiro",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="piezas",
                        to="caja.retirocaja",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="ComprobanteRetiro",
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
                ("archivo", models.CharField(max_length=64, unique=True)),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("jpeg", "Imagen JPEG"),
                            ("png", "Imagen PNG"),
                            ("pdf", "PDF"),
                        ],
                        max_length=4,
                    ),
                ),
                ("tamano", models.PositiveIntegerField()),
                ("sha256", models.CharField(max_length=64)),
                ("subido_en", models.DateTimeField(auto_now_add=True)),
                (
                    "subido_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "retiro",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="archivo_comprobante",
                        to="caja.retirocaja",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ReversionRetiro",
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
                    "retiro",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reversion",
                        to="caja.retirocaja",
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
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="retiros_devueltos",
                        to="caja.turno",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="ConteoArqueo",
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
                ("numero", models.PositiveSmallIntegerField()),
                ("conteo", models.JSONField(default=dict)),
                ("contado", models.PositiveBigIntegerField()),
                ("nota", models.CharField(blank=True, max_length=500)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                (
                    "turno",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="conteos",
                        to="caja.turno",
                    ),
                ),
            ],
            options={
                "ordering": ["turno", "numero"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("turno", "numero"), name="conteo_unico_por_numero"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("numero__in", [1, 2])),
                        name="conteo_primero_o_reconteo",
                    ),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="retirocaja",
            constraint=models.UniqueConstraint(
                fields=("serie", "folio"), name="retiro_folio_unico"
            ),
        ),
        migrations.AddConstraint(
            model_name="retirocaja",
            constraint=models.CheckConstraint(
                condition=models.Q(("importe__gt", 0)), name="retiro_importe_positivo"
            ),
        ),
        migrations.AddConstraint(
            model_name="retirocaja",
            constraint=models.CheckConstraint(
                condition=models.Q(("folio__gte", 1)), name="retiro_folio_positivo"
            ),
        ),
        migrations.AddConstraint(
            model_name="retirocaja",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("revisado_por", models.F("registrado_por")), _negated=True
                ),
                name="retiro_revision_ajena",
            ),
        ),
        migrations.AddConstraint(
            model_name="retirocaja",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("revision", "por_revisar"), ("revisado_por__isnull", True)
                    ),
                    models.Q(
                        ("revision__in", ["revisado", "observado"]),
                        ("revisado_por__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="retiro_revision_coherente",
            ),
        ),
        migrations.AddConstraint(
            model_name="movimientopiezas",
            constraint=models.CheckConstraint(
                condition=models.Q(("piezas", 0), _negated=True),
                name="piezas_distinto_de_cero",
            ),
        ),
        migrations.AddConstraint(
            model_name="movimientopiezas",
            constraint=models.CheckConstraint(
                condition=models.Q(("denominacion__gt", 0)),
                name="piezas_denominacion_positiva",
            ),
        ),
        migrations.AddConstraint(
            model_name="comprobanteretiro",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("archivo__regex", "^[0-9a-f]{32}\\.(jpg|png|pdf)$")
                ),
                name="comprobante_nombre_aleatorio",
            ),
        ),
    ]
