from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Parametro",
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
                    "clave",
                    models.CharField(
                        choices=[
                            ("intentos_antes_de_bloqueo", "intentos_antes_de_bloqueo"),
                            ("minutos_bloqueo_inicial", "minutos_bloqueo_inicial"),
                            ("minutos_bloqueo_maximo", "minutos_bloqueo_maximo"),
                            ("minutos_validez_reingreso", "minutos_validez_reingreso"),
                            ("ventana_codigo_pasos", "ventana_codigo_pasos"),
                            ("dias_maximos_delegacion", "dias_maximos_delegacion"),
                            (
                                "intentos_por_ip_cada_5_minutos",
                                "intentos_por_ip_cada_5_minutos",
                            ),
                            (
                                "intentos_codigo_por_solicitud",
                                "intentos_codigo_por_solicitud",
                            ),
                            ("prefijo_pais_telefono", "prefijo_pais_telefono"),
                            ("digitos_telefono_nacional", "digitos_telefono_nacional"),
                        ],
                        max_length=60,
                        unique=True,
                    ),
                ),
                ("valor", models.CharField(max_length=200)),
            ],
        ),
        migrations.CreateModel(
            name="Vocabulario",
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
                    "clave",
                    models.CharField(
                        choices=[
                            ("titular", "titular"),
                            ("titulares", "titulares"),
                            ("matricula", "matricula"),
                            ("agrupacion", "agrupacion"),
                            ("agrupaciones", "agrupaciones"),
                        ],
                        max_length=30,
                        unique=True,
                    ),
                ),
                ("texto", models.CharField(max_length=60)),
            ],
        ),
        migrations.CreateModel(
            name="Negocio",
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
                ("nombre", models.CharField(max_length=150)),
                ("instrucciones_pago", models.TextField(blank=True)),
                (
                    "zona_horaria",
                    models.CharField(default="America/Mexico_City", max_length=64),
                ),
                ("sede", models.PositiveSmallIntegerField(default=0)),
                ("ranuras", models.PositiveSmallIntegerField(default=10)),
                ("longitud_matricula", models.PositiveSmallIntegerField(default=7)),
                ("contador_matricula", models.BigIntegerField(default=0)),
                ("plantilla", models.CharField(blank=True, max_length=40)),
                ("configurado", models.BooleanField(default=False)),
                ("creado", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("id", 1)), name="negocio_unico"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("longitud_matricula__gte", 5),
                            ("longitud_matricula__lte", 12),
                        ),
                        name="negocio_longitud",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("ranuras__gte", 1)), name="negocio_ranuras"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("sede__lt", models.F("ranuras"))),
                        name="negocio_sede",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("contador_matricula__gte", 0)),
                        name="negocio_contador",
                    ),
                ],
            },
        ),
    ]
