import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Usuario",
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
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="last login"
                    ),
                ),
                ("usuario", models.CharField(max_length=60, unique=True)),
                ("nombre", models.CharField(max_length=150)),
                ("activo", models.BooleanField(default=True)),
                ("totp_secreto", models.CharField(blank=True, max_length=64)),
                ("totp_confirmado", models.BooleanField(default=False)),
                ("intentos_fallidos", models.PositiveIntegerField(default=0)),
                ("bloqueado_hasta", models.DateTimeField(blank=True, null=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["nombre"],
            },
        ),
        migrations.CreateModel(
            name="Delegacion",
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
                    "permiso",
                    models.CharField(
                        choices=[
                            ("ver_titulares", "Ver padrón y saldos"),
                            (
                                "solicitar_alta_baja",
                                "Solicitar alta, baja o reactivación",
                            ),
                            ("alta_baja_directa", "Alta, baja o reactivación directa"),
                            ("aprobar_solicitudes", "Aprobar solicitudes"),
                            ("otorgar_delegaciones", "Otorgar delegaciones"),
                            ("registrar_pago_efectivo", "Registrar pago en efectivo"),
                            ("turno_caja", "Abrir y cerrar su turno de caja"),
                            (
                                "solicitar_ajustes",
                                "Solicitar cancelación de recibo, condonación o descuento",
                            ),
                            (
                                "aplicar_ajustes",
                                "Cancelar recibo, condonar recargo o aplicar descuento",
                            ),
                            ("cargo_manual", "Cargo manual"),
                            ("recibir_efectivo", "Recibir efectivo y revisar arqueos"),
                            (
                                "sugerir_conciliacion",
                                "Sugerir identificación de movimientos bancarios",
                            ),
                            ("conciliar_banco", "Importar banco y conciliar"),
                            ("administrar_conceptos", "Administrar conceptos de cobro"),
                            ("ver_cortes", "Ver cortes"),
                            ("cerrar_cortes", "Cerrar cortes"),
                            ("aprobar_dispositivos", "Aprobar dispositivos"),
                            ("administrar_usuarios", "Administrar usuarios"),
                            ("administrar_roles", "Administrar roles y permisos"),
                            (
                                "administrar_politicas",
                                "Administrar políticas de aprobación",
                            ),
                            ("administrar_configuracion", "Administrar configuración"),
                            ("ver_auditoria", "Ver auditoría"),
                            ("administrar_respaldos", "Administrar respaldos"),
                        ],
                        max_length=40,
                    ),
                ),
                ("vence", models.DateTimeField(blank=True, null=True)),
                ("usos_maximos", models.PositiveIntegerField(blank=True, null=True)),
                ("usos", models.PositiveIntegerField(default=0)),
                ("motivo", models.CharField(blank=True, max_length=200)),
                ("revocada", models.BooleanField(default=False)),
                ("creada", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-creada"],
            },
        ),
        migrations.CreateModel(
            name="Dispositivo",
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
                ("hash_credencial", models.CharField(max_length=64, unique=True)),
                ("codigo", models.CharField(db_index=True, max_length=8)),
                ("nombre", models.CharField(blank=True, max_length=100)),
                ("agente", models.CharField(blank=True, max_length=300)),
                ("ip", models.CharField(blank=True, max_length=45)),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("pendiente", "Pendiente"),
                            ("aprobado", "Aprobado"),
                            ("revocado", "Revocado"),
                        ],
                        default="pendiente",
                        max_length=10,
                    ),
                ),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("aprobado_en", models.DateTimeField(blank=True, null=True)),
                ("revocado_en", models.DateTimeField(blank=True, null=True)),
                ("ultimo_uso", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-creado"],
            },
        ),
        migrations.CreateModel(
            name="PermisoRol",
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
                    "permiso",
                    models.CharField(
                        choices=[
                            ("ver_titulares", "Ver padrón y saldos"),
                            (
                                "solicitar_alta_baja",
                                "Solicitar alta, baja o reactivación",
                            ),
                            ("alta_baja_directa", "Alta, baja o reactivación directa"),
                            ("aprobar_solicitudes", "Aprobar solicitudes"),
                            ("otorgar_delegaciones", "Otorgar delegaciones"),
                            ("registrar_pago_efectivo", "Registrar pago en efectivo"),
                            ("turno_caja", "Abrir y cerrar su turno de caja"),
                            (
                                "solicitar_ajustes",
                                "Solicitar cancelación de recibo, condonación o descuento",
                            ),
                            (
                                "aplicar_ajustes",
                                "Cancelar recibo, condonar recargo o aplicar descuento",
                            ),
                            ("cargo_manual", "Cargo manual"),
                            ("recibir_efectivo", "Recibir efectivo y revisar arqueos"),
                            (
                                "sugerir_conciliacion",
                                "Sugerir identificación de movimientos bancarios",
                            ),
                            ("conciliar_banco", "Importar banco y conciliar"),
                            ("administrar_conceptos", "Administrar conceptos de cobro"),
                            ("ver_cortes", "Ver cortes"),
                            ("cerrar_cortes", "Cerrar cortes"),
                            ("aprobar_dispositivos", "Aprobar dispositivos"),
                            ("administrar_usuarios", "Administrar usuarios"),
                            ("administrar_roles", "Administrar roles y permisos"),
                            (
                                "administrar_politicas",
                                "Administrar políticas de aprobación",
                            ),
                            ("administrar_configuracion", "Administrar configuración"),
                            ("ver_auditoria", "Ver auditoría"),
                            ("administrar_respaldos", "Administrar respaldos"),
                        ],
                        max_length=40,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Rol",
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
                ("nivel", models.PositiveSmallIntegerField(default=1)),
                ("minutos_inactividad", models.PositiveIntegerField(default=30)),
                ("requiere_totp", models.BooleanField(default=False)),
            ],
            options={
                "ordering": ["nivel", "nombre"],
            },
        ),
        migrations.CreateModel(
            name="CodigoUsado",
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
                ("paso", models.BigIntegerField()),
                (
                    "proposito",
                    models.CharField(
                        choices=[
                            ("inicio_sesion", "Inicio de sesión"),
                            ("autorizacion", "Autorización por teléfono"),
                            ("alta", "Alta del autenticador"),
                        ],
                        max_length=20,
                    ),
                ),
                ("usado_en", models.DateTimeField(auto_now_add=True)),
                (
                    "revision",
                    models.CharField(
                        choices=[
                            ("no_aplica", "No aplica"),
                            ("por_revisar", "Por revisar"),
                            ("confirmado", "Confirmado"),
                            ("reportado", "Reportado"),
                        ],
                        default="no_aplica",
                        max_length=12,
                    ),
                ),
                ("revisado_en", models.DateTimeField(blank=True, null=True)),
                (
                    "autorizador",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="codigos_usados",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-usado_en"],
            },
        ),
    ]
