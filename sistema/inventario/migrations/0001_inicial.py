import django.db.models.deletion
import django.db.models.expressions
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("caja", "0004_piezas_arqueo_y_retiros"),
        ("cobros", "0008_medio_devolucion"),
        ("solicitudes", "0007_acciones_de_inventario"),
        ("titulares", "0004_cuenta_interna"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Articulo",
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
                ("clave", models.CharField(max_length=30, unique=True)),
                ("nombre", models.CharField(max_length=150)),
                ("precio", models.PositiveBigIntegerField()),
                ("minimo", models.PositiveIntegerField(default=0)),
                ("activo", models.BooleanField(default=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                (
                    "concepto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="articulos",
                        to="cobros.conceptocobro",
                    ),
                ),
            ],
            options={
                "ordering": ["nombre", "clave"],
            },
        ),
        migrations.CreateModel(
            name="Conteo",
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
                ("creado", models.DateTimeField(auto_now_add=True)),
                (
                    "origen",
                    models.CharField(
                        choices=[
                            ("archivo", "Archivo subido"),
                            ("pantalla", "Capturado en pantalla"),
                        ],
                        max_length=8,
                    ),
                ),
                ("nombre_archivo", models.CharField(blank=True, max_length=120)),
                ("sha256", models.CharField(blank=True, max_length=64)),
                ("inicial", models.BooleanField(default=False)),
                ("aplicado_en", models.DateTimeField(blank=True, null=True)),
                (
                    "aplicado_por",
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
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="conteo",
                        to="solicitudes.solicitud",
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
            ],
            options={
                "ordering": ["-creado", "-id"],
            },
        ),
        migrations.CreateModel(
            name="Devolucion",
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
                    "medio",
                    models.CharField(
                        choices=[
                            ("saldo", "Saldo a favor"),
                            ("efectivo", "Efectivo"),
                            ("sin_dinero", "Se canceló lo pendiente"),
                            ("reversion", "Reversión del pago"),
                        ],
                        max_length=10,
                    ),
                ),
                ("motivo", models.CharField(max_length=300)),
                ("importe_cancelado", models.PositiveBigIntegerField(default=0)),
                ("importe_dinero", models.PositiveBigIntegerField(default=0)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                (
                    "revision",
                    models.CharField(
                        choices=[
                            ("por_revisar", "Por revisar"),
                            ("revisado", "Revisado"),
                            ("observado", "Observado"),
                            ("no_aplica", "No requiere revisión"),
                        ],
                        default="por_revisar",
                        max_length=12,
                    ),
                ),
                ("revisado_en", models.DateTimeField(blank=True, null=True)),
                ("nota_revision", models.CharField(blank=True, max_length=300)),
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
                    "pago_credito",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="devolucion_articulos",
                        to="cobros.pago",
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
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="devoluciones_articulos",
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
            ],
            options={
                "ordering": ["-creada", "-id"],
            },
        ),
        migrations.CreateModel(
            name="RegistroInventario",
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
                        choices=[("entrada", "Entrada"), ("merma", "Merma")],
                        max_length=8,
                    ),
                ),
                ("cantidad", models.PositiveIntegerField()),
                ("motivo", models.CharField(max_length=150)),
                ("nota", models.CharField(blank=True, max_length=300)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                (
                    "comprobante",
                    models.CharField(
                        choices=[
                            ("sin", "Sin comprobante"),
                            ("adjunto", "Con comprobante"),
                        ],
                        default="sin",
                        max_length=8,
                    ),
                ),
                (
                    "revision",
                    models.CharField(
                        choices=[
                            ("por_revisar", "Por revisar"),
                            ("revisado", "Revisado"),
                            ("observado", "Observado"),
                            ("no_aplica", "No requiere revisión"),
                        ],
                        default="por_revisar",
                        max_length=12,
                    ),
                ),
                ("revisado_en", models.DateTimeField(blank=True, null=True)),
                ("nota_revision", models.CharField(blank=True, max_length=300)),
                (
                    "articulo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="registros",
                        to="inventario.articulo",
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
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-creado", "-id"],
            },
        ),
        migrations.CreateModel(
            name="ComprobanteInventario",
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
                ("tipo", models.CharField(max_length=4)),
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
                    "registro",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="archivo_comprobante",
                        to="inventario.registroinventario",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="RenglonConteo",
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
                ("contado", models.BigIntegerField()),
                ("esperado", models.BigIntegerField()),
                ("diferencia", models.BigIntegerField()),
                (
                    "articulo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="conteos",
                        to="inventario.articulo",
                    ),
                ),
                (
                    "conteo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="renglones",
                        to="inventario.conteo",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="RenglonVenta",
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
                ("cantidad", models.PositiveIntegerField()),
                ("precio_unitario", models.PositiveBigIntegerField()),
                ("existencia_antes", models.BigIntegerField()),
                ("sin_existencia", models.BooleanField(default=False)),
                ("revisado_en", models.DateTimeField(blank=True, null=True)),
                (
                    "articulo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="vendidos",
                        to="inventario.articulo",
                    ),
                ),
                (
                    "cargo",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="renglon_venta",
                        to="cobros.cargo",
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
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="RenglonDevolucion",
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
                ("cantidad", models.PositiveIntegerField()),
                ("buen_estado", models.BooleanField(default=True)),
                (
                    "devolucion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="renglones",
                        to="inventario.devolucion",
                    ),
                ),
                (
                    "renglon",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="devueltos",
                        to="inventario.renglonventa",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="Venta",
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
                    "modo",
                    models.CharField(
                        choices=[
                            ("ahora", "Lo paga ahora"),
                            ("adeudo", "Se va a su adeudo"),
                        ],
                        max_length=8,
                    ),
                ),
                ("total", models.PositiveBigIntegerField()),
                ("creada", models.DateTimeField(auto_now_add=True)),
                (
                    "pago",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="venta",
                        to="cobros.pago",
                    ),
                ),
                (
                    "titular",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ventas",
                        to="titulares.titular",
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
            ],
            options={
                "ordering": ["-creada", "-id"],
            },
        ),
        migrations.AddField(
            model_name="renglonventa",
            name="venta",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="renglones",
                to="inventario.venta",
            ),
        ),
        migrations.CreateModel(
            name="MovimientoInventario",
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
                            ("carga_inicial", "Carga inicial"),
                            ("entrada", "Entrada"),
                            ("venta", "Venta"),
                            ("devolucion", "Devolución"),
                            ("merma", "Merma"),
                            ("ajuste_conteo", "Ajuste por conteo"),
                        ],
                        max_length=14,
                    ),
                ),
                ("cantidad", models.BigIntegerField()),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("nota", models.CharField(blank=True, max_length=300)),
                (
                    "articulo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movimientos",
                        to="inventario.articulo",
                    ),
                ),
                (
                    "conteo",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movimientos",
                        to="inventario.conteo",
                    ),
                ),
                (
                    "devolucion",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movimientos",
                        to="inventario.devolucion",
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
                    "registro",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movimientos",
                        to="inventario.registroinventario",
                    ),
                ),
                (
                    "venta",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movimientos",
                        to="inventario.venta",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.AddField(
            model_name="devolucion",
            name="venta",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="devoluciones",
                to="inventario.venta",
            ),
        ),
        migrations.AddConstraint(
            model_name="articulo",
            constraint=models.CheckConstraint(
                condition=models.Q(("clave__regex", "^[A-Z0-9][A-Z0-9._-]{0,29}$")),
                name="articulo_clave_valida",
            ),
        ),
        migrations.AddConstraint(
            model_name="articulo",
            constraint=models.CheckConstraint(
                condition=models.Q(("precio__gt", 0)), name="articulo_precio_positivo"
            ),
        ),
        migrations.AddConstraint(
            model_name="articulo",
            constraint=models.CheckConstraint(
                condition=models.Q(("minimo__lte", 1000000)),
                name="articulo_minimo_razonable",
            ),
        ),
        migrations.AddConstraint(
            model_name="conteo",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("aplicado_por__isnull", True),
                    models.Q(("aplicado_por", models.F("usuario")), _negated=True),
                    _connector="OR",
                ),
                name="conteo_aprobado_por_otra_persona",
            ),
        ),
        migrations.AddConstraint(
            model_name="registroinventario",
            constraint=models.CheckConstraint(
                condition=models.Q(("cantidad__gte", 1), ("cantidad__lte", 10000)),
                name="registro_inventario_cantidad",
            ),
        ),
        migrations.AddConstraint(
            model_name="registroinventario",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("revision__in", ["por_revisar", "no_aplica"]),
                        ("revisado_por__isnull", True),
                    ),
                    models.Q(
                        ("revision__in", ["revisado", "observado"]),
                        ("revisado_por__isnull", False),
                        models.Q(("revisado_por", models.F("usuario")), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="registro_inventario_revision_ajena",
            ),
        ),
        migrations.AddConstraint(
            model_name="comprobanteinventario",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("archivo__regex", "^[0-9a-f]{32}\\.(jpg|png|pdf)$")
                ),
                name="comprobante_inventario_nombre_aleatorio",
            ),
        ),
        migrations.AddConstraint(
            model_name="renglonconteo",
            constraint=models.UniqueConstraint(
                fields=("conteo", "articulo"), name="renglon_conteo_articulo_unico"
            ),
        ),
        migrations.AddConstraint(
            model_name="renglonconteo",
            constraint=models.CheckConstraint(
                condition=models.Q(("contado__gte", 0), ("contado__lte", 1000000)),
                name="renglon_conteo_contado",
            ),
        ),
        migrations.AddConstraint(
            model_name="renglonconteo",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "diferencia",
                        django.db.models.expressions.CombinedExpression(
                            models.F("contado"), "-", models.F("esperado")
                        ),
                    )
                ),
                name="renglon_conteo_diferencia",
            ),
        ),
        migrations.AddConstraint(
            model_name="renglondevolucion",
            constraint=models.CheckConstraint(
                condition=models.Q(("cantidad__gte", 1), ("cantidad__lte", 10000)),
                name="renglon_devolucion_cantidad",
            ),
        ),
        migrations.AddConstraint(
            model_name="venta",
            constraint=models.CheckConstraint(
                condition=models.Q(("total__gt", 0)), name="venta_total_positivo"
            ),
        ),
        migrations.AddConstraint(
            model_name="renglonventa",
            constraint=models.CheckConstraint(
                condition=models.Q(("cantidad__gte", 1), ("cantidad__lte", 10000)),
                name="renglon_venta_cantidad",
            ),
        ),
        migrations.AddConstraint(
            model_name="renglonventa",
            constraint=models.CheckConstraint(
                condition=models.Q(("precio_unitario__gt", 0)),
                name="renglon_venta_precio",
            ),
        ),
        migrations.AddConstraint(
            model_name="renglonventa",
            constraint=models.UniqueConstraint(
                fields=("venta", "articulo"), name="renglon_venta_articulo_unico"
            ),
        ),
        migrations.AddConstraint(
            model_name="movimientoinventario",
            constraint=models.CheckConstraint(
                condition=models.Q(("cantidad", 0), _negated=True),
                name="movimiento_inventario_distinto_de_cero",
            ),
        ),
        migrations.AddConstraint(
            model_name="movimientoinventario",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("tipo", "venta"), ("venta__isnull", False), ("cantidad__lt", 0)
                    ),
                    models.Q(
                        ("tipo", "devolucion"),
                        ("devolucion__isnull", False),
                        ("cantidad__gt", 0),
                    ),
                    models.Q(
                        ("tipo", "merma"),
                        models.Q(
                            ("registro__isnull", False),
                            ("devolucion__isnull", False),
                            _connector="OR",
                        ),
                        ("cantidad__lt", 0),
                    ),
                    models.Q(
                        ("tipo", "entrada"),
                        ("registro__isnull", False),
                        ("cantidad__gt", 0),
                    ),
                    models.Q(
                        ("tipo__in", ["ajuste_conteo", "carga_inicial"]),
                        ("conteo__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="movimiento_inventario_coherente",
            ),
        ),
        migrations.AddConstraint(
            model_name="devolucion",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("medio", "efectivo"), _negated=True),
                    models.Q(
                        ("turno__isnull", False),
                        ("importe_dinero__gt", 0),
                        ("solicitud__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="devolucion_efectivo_con_turno_y_solicitud",
            ),
        ),
        migrations.AddConstraint(
            model_name="devolucion",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("medio", "saldo"), _negated=True),
                    models.Q(
                        ("pago_credito__isnull", False), ("importe_dinero__gt", 0)
                    ),
                    _connector="OR",
                ),
                name="devolucion_saldo_con_pago",
            ),
        ),
        migrations.AddConstraint(
            model_name="devolucion",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("medio", "sin_dinero"), _negated=True),
                    ("importe_dinero", 0),
                    _connector="OR",
                ),
                name="devolucion_sin_dinero",
            ),
        ),
        migrations.AddConstraint(
            model_name="devolucion",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("revision__in", ["por_revisar", "no_aplica"]),
                        ("revisado_por__isnull", True),
                    ),
                    models.Q(
                        ("revision__in", ["revisado", "observado"]),
                        ("revisado_por__isnull", False),
                        models.Q(("revisado_por", models.F("usuario")), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="devolucion_revision_ajena",
            ),
        ),
    ]
