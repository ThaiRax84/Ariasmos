import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("titulares", "0005_hojas_y_apellidos_opcionales"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LimiteAdeudo",
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
                    "modo_importe",
                    models.CharField(
                        choices=[
                            ("ilimitado", "Ilimitado"),
                            ("valor", "Hasta un valor"),
                        ],
                        default="ilimitado",
                        max_length=10,
                    ),
                ),
                ("importe_maximo", models.PositiveBigIntegerField(default=0)),
                (
                    "modo_dias",
                    models.CharField(
                        choices=[
                            ("ilimitado", "Ilimitado"),
                            ("valor", "Hasta un valor"),
                        ],
                        default="ilimitado",
                        max_length=10,
                    ),
                ),
                ("dias_maximos", models.PositiveIntegerField(default=0)),
                ("actualizado", models.DateTimeField(auto_now=True)),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("id", 1)), name="limite_adeudo_unico"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("modo_importe__in", ["ilimitado", "valor"])
                        ),
                        name="limite_modo_importe_valido",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("modo_dias__in", ["ilimitado", "valor"])),
                        name="limite_modo_dias_valido",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ExcepcionLimite",
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
                    "modo_importe",
                    models.CharField(
                        choices=[
                            ("negocio", "Como el negocio"),
                            ("ilimitado", "Ilimitado"),
                            ("valor", "Hasta un valor"),
                        ],
                        default="negocio",
                        max_length=10,
                    ),
                ),
                ("importe_maximo", models.PositiveBigIntegerField(default=0)),
                (
                    "modo_dias",
                    models.CharField(
                        choices=[
                            ("negocio", "Como el negocio"),
                            ("ilimitado", "Ilimitado"),
                            ("valor", "Hasta un valor"),
                        ],
                        default="negocio",
                        max_length=10,
                    ),
                ),
                ("dias_maximos", models.PositiveIntegerField(default=0)),
                ("motivo", models.CharField(max_length=300)),
                ("vigente_hasta", models.DateField(blank=True, null=True)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                ("actualizada", models.DateTimeField(auto_now=True)),
                (
                    "creada_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "titular",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="excepcion_limite",
                        to="titulares.titular",
                    ),
                ),
            ],
            options={
                "ordering": ["titular__apellidos", "titular__nombre"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("modo_importe__in", ["negocio", "ilimitado", "valor"])
                        ),
                        name="excepcion_modo_importe_valido",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("modo_dias__in", ["negocio", "ilimitado", "valor"])
                        ),
                        name="excepcion_modo_dias_valido",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ReglaRezago",
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
                ("texto", models.CharField(max_length=60)),
                (
                    "alcance",
                    models.CharField(
                        choices=[
                            ("todos", "Todos"),
                            ("agrupacion", "{agrupacion}"),
                            ("titular", "{titular}"),
                        ],
                        default="todos",
                        max_length=12,
                    ),
                ),
                ("dias_minimos", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "importe_minimo",
                    models.PositiveBigIntegerField(blank=True, null=True),
                ),
                ("al_rebasar_limite", models.BooleanField(default=False)),
                ("aviso_inicio", models.BooleanField(default=False)),
                ("marca", models.BooleanField(default=False)),
                ("sin_credito", models.BooleanField(default=False)),
                ("cobranza", models.BooleanField(default=False)),
                ("activa", models.BooleanField(default=True)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                ("actualizada", models.DateTimeField(auto_now=True)),
                (
                    "agrupacion",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="titulares.agrupacion",
                    ),
                ),
                (
                    "titular",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reglas_rezago",
                        to="titulares.titular",
                    ),
                ),
            ],
            options={
                "ordering": ["alcance", "dias_minimos", "nombre", "id"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("alcance", "todos"),
                                ("agrupacion__isnull", True),
                                ("titular__isnull", True),
                            ),
                            models.Q(
                                ("alcance", "agrupacion"),
                                ("agrupacion__isnull", False),
                                ("titular__isnull", True),
                            ),
                            models.Q(
                                ("alcance", "titular"),
                                ("titular__isnull", False),
                                ("agrupacion__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        name="regla_rezago_alcance_coherente",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("dias_minimos__isnull", False),
                            ("importe_minimo__isnull", False),
                            ("al_rebasar_limite", True),
                            _connector="OR",
                        ),
                        name="regla_rezago_con_condicion",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("aviso_inicio", True),
                            ("marca", True),
                            ("sin_credito", True),
                            ("cobranza", True),
                            _connector="OR",
                        ),
                        name="regla_rezago_con_accion",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("dias_minimos__isnull", True),
                            ("dias_minimos__gte", 1),
                            _connector="OR",
                        ),
                        name="regla_rezago_dias_positivos",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("importe_minimo__isnull", True),
                            ("importe_minimo__gte", 1),
                            _connector="OR",
                        ),
                        name="regla_rezago_importe_positivo",
                    ),
                ],
            },
        ),
    ]
