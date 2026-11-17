
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LlaveDeUso",
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
                ("llave", models.CharField(max_length=44)),
                ("recuperacion", models.CharField(max_length=44)),
                ("contador", models.BigIntegerField(unique=True)),
                ("aviso", models.BinaryField()),
                ("firma", models.BinaryField()),
                ("aceptada_en", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-contador"],
            },
        ),
        migrations.CreateModel(
            name="RechazoReciente",
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
                ("motivo", models.CharField(max_length=60, unique=True)),
                ("ultimo", models.DateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name="VersionPublicada",
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
                ("version", models.CharField(max_length=20)),
                ("contador", models.BigIntegerField(unique=True)),
                ("aviso", models.BinaryField()),
                ("firma", models.BinaryField()),
                ("llave", models.CharField(max_length=44)),
                ("datos", models.JSONField(default=dict)),
                ("recibida_en", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-contador"],
            },
        ),
        migrations.CreateModel(
            name="Configuracion",
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
                ("activa", models.BooleanField(default=False)),
                ("canal", models.CharField(default="github", max_length=20)),
                ("repositorio", models.CharField(blank=True, max_length=140)),
                ("clave_cifrada", models.TextField(blank=True)),
                ("cambiada_en", models.DateTimeField(blank=True, null=True)),
                ("ultima_busqueda", models.DateTimeField(blank=True, null=True)),
                ("proxima_busqueda", models.DateTimeField(blank=True, null=True)),
                ("busqueda_pedida", models.BooleanField(default=False)),
                ("busqueda_pedida_en", models.DateTimeField(blank=True, null=True)),
                ("ultimo_resultado", models.CharField(blank=True, max_length=200)),
                ("contador_version", models.BigIntegerField(default=0)),
                ("contador_llave", models.BigIntegerField(default=0)),
                (
                    "cambiada_por",
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
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("id", 1)),
                        name="actualizaciones_configuracion_unica",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Descarga",
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
                ("pedida_en", models.DateTimeField(auto_now_add=True)),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("pendiente", "Pendiente"),
                            ("en_curso", "Descargando"),
                            ("lista", "Lista para instalar"),
                            ("fallida", "Fallida"),
                        ],
                        default="pendiente",
                        max_length=10,
                    ),
                ),
                ("en_proceso", models.BooleanField(default=True, null=True)),
                ("iniciada_en", models.DateTimeField(blank=True, null=True)),
                ("terminada_en", models.DateTimeField(blank=True, null=True)),
                ("motivo", models.CharField(blank=True, max_length=200)),
                ("archivo", models.CharField(blank=True, max_length=120)),
                ("sha256", models.CharField(blank=True, max_length=64)),
                (
                    "pedida_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="descargas",
                        to="actualizaciones.versionpublicada",
                    ),
                ),
            ],
            options={
                "ordering": ["-pedida_en", "-id"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("en_proceso", True)),
                        fields=("en_proceso",),
                        name="una_descarga_a_la_vez",
                    )
                ],
            },
        ),
    ]
