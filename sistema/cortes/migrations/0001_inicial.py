import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("caja", "0003_deposito_conciliado"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DefinicionCorte",
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
                            ("diario", "Corte diario de caja"),
                            ("mayor", "Corte mayor"),
                            ("cobranza", "Lista de cobranza"),
                        ],
                        max_length=10,
                        unique=True,
                    ),
                ),
                ("nombre", models.CharField(max_length=60)),
                ("activa", models.BooleanField(default=True)),
                (
                    "nivel",
                    models.CharField(
                        choices=[
                            ("completo", "Completo: nombres, matrícula y contacto"),
                            ("solo_nombres", "Solo nombres: sin matrícula ni contacto"),
                            ("sin_nombres", "Sin nombres: solo matrícula"),
                        ],
                        default="solo_nombres",
                        max_length=15,
                    ),
                ),
            ],
            options={
                "ordering": ["tipo"],
            },
        ),
        migrations.CreateModel(
            name="Destino",
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
                ("nombre", models.CharField(max_length=60)),
                (
                    "tipo",
                    models.CharField(
                        choices=[("carpeta", "Carpeta")],
                        default="carpeta",
                        max_length=10,
                    ),
                ),
                ("ruta", models.CharField(max_length=400)),
                ("activo", models.BooleanField(default=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["nombre"],
            },
        ),
        migrations.CreateModel(
            name="Corte",
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
                            ("diario", "Corte diario de caja"),
                            ("mayor", "Corte mayor"),
                            ("cobranza", "Lista de cobranza"),
                        ],
                        max_length=10,
                    ),
                ),
                ("fecha", models.DateField()),
                ("periodo_inicio", models.DateField()),
                ("periodo_fin", models.DateField()),
                ("numero", models.PositiveIntegerField(default=1)),
                ("automatico", models.BooleanField(default=False)),
                (
                    "estado",
                    models.CharField(
                        choices=[("borrador", "Borrador"), ("cerrado", "Cerrado")],
                        default="borrador",
                        max_length=10,
                    ),
                ),
                ("tardio", models.BooleanField(default=False)),
                ("sin_revisar", models.BooleanField(default=False)),
                ("cifras", models.JSONField(default=dict)),
                ("hash", models.CharField(blank=True, max_length=64)),
                ("cerrado_en", models.DateTimeField(blank=True, null=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                (
                    "caja",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="caja.caja",
                    ),
                ),
                (
                    "cerrado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "turno",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="corte",
                        to="caja.turno",
                    ),
                ),
                (
                    "usuario",
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
                "ordering": ["-fecha", "-id"],
            },
        ),
        migrations.CreateModel(
            name="Entrega",
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
                    "nivel",
                    models.CharField(
                        choices=[
                            ("completo", "Completo: nombres, matrícula y contacto"),
                            ("solo_nombres", "Solo nombres: sin matrícula ni contacto"),
                            ("sin_nombres", "Sin nombres: solo matrícula"),
                        ],
                        max_length=15,
                    ),
                ),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("pendiente", "Pendiente"),
                            ("entregada", "Entregada"),
                            ("fallida", "Fallida"),
                        ],
                        default="pendiente",
                        max_length=10,
                    ),
                ),
                ("intentos", models.PositiveIntegerField(default=0)),
                ("ultimo_error", models.CharField(blank=True, max_length=300)),
                ("proximo_intento", models.DateTimeField(blank=True, null=True)),
                ("ocupada_hasta", models.DateTimeField(blank=True, null=True)),
                ("entregada_en", models.DateTimeField(blank=True, null=True)),
                ("archivos", models.JSONField(blank=True, default=list)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                (
                    "corte",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="entregas",
                        to="cortes.corte",
                    ),
                ),
                (
                    "destino",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="entregas",
                        to="cortes.destino",
                    ),
                ),
            ],
            options={
                "ordering": ["-creada", "-id"],
            },
        ),
        migrations.CreateModel(
            name="ReglaDestino",
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
                            ("diario", "Corte diario de caja"),
                            ("mayor", "Corte mayor"),
                            ("cobranza", "Lista de cobranza"),
                        ],
                        max_length=10,
                    ),
                ),
                ("entregar", models.BooleanField(default=True)),
                (
                    "nivel",
                    models.CharField(
                        choices=[
                            ("completo", "Completo: nombres, matrícula y contacto"),
                            ("solo_nombres", "Solo nombres: sin matrícula ni contacto"),
                            ("sin_nombres", "Sin nombres: solo matrícula"),
                        ],
                        default="solo_nombres",
                        max_length=15,
                    ),
                ),
                (
                    "destino",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reglas",
                        to="cortes.destino",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="corte",
            constraint=models.UniqueConstraint(
                condition=models.Q(("tipo", "mayor")),
                fields=("tipo", "fecha"),
                name="corte_mayor_unico",
            ),
        ),
        migrations.AddConstraint(
            model_name="corte",
            constraint=models.UniqueConstraint(
                condition=models.Q(("automatico", True), ("tipo", "cobranza")),
                fields=("tipo", "fecha"),
                name="cobranza_automatica_unica",
            ),
        ),
        migrations.AddConstraint(
            model_name="corte",
            constraint=models.UniqueConstraint(
                condition=models.Q(("tipo", "diario")),
                fields=("tipo", "fecha", "caja", "numero"),
                name="corte_diario_numero",
            ),
        ),
        migrations.AddConstraint(
            model_name="corte",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("estado", "cerrado"), _negated=True),
                    models.Q(("hash", ""), _negated=True),
                    _connector="OR",
                ),
                name="corte_cerrado_con_hash",
            ),
        ),
        migrations.AddConstraint(
            model_name="entrega",
            constraint=models.UniqueConstraint(
                fields=("corte", "destino"), name="entrega_unica"
            ),
        ),
        migrations.AddConstraint(
            model_name="regladestino",
            constraint=models.UniqueConstraint(
                fields=("destino", "tipo"), name="regla_destino_unica"
            ),
        ),
    ]
