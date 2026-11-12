import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("titulares", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PoliticaAccion",
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
                    "accion",
                    models.CharField(
                        choices=[
                            ("alta", "Alta"),
                            ("baja", "Baja"),
                            ("reactivacion", "Reactivación"),
                        ],
                        max_length=30,
                        unique=True,
                    ),
                ),
                (
                    "permiso_directo",
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
                (
                    "permiso_solicitar",
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
                (
                    "permiso_aprobar",
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
                ("horas_caducidad", models.PositiveIntegerField(default=72)),
                ("horas_resaltar", models.PositiveIntegerField(default=24)),
                ("permite_delegacion", models.BooleanField(default=True)),
                ("permite_codigo", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["accion"],
            },
        ),
        migrations.CreateModel(
            name="Solicitud",
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
                    "accion",
                    models.CharField(
                        choices=[
                            ("alta", "Alta"),
                            ("baja", "Baja"),
                            ("reactivacion", "Reactivación"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("pendiente", "Pendiente"),
                            ("aprobada", "Aprobada"),
                            ("rechazada", "Rechazada"),
                            ("caducada", "Caducada"),
                        ],
                        default="pendiente",
                        max_length=10,
                    ),
                ),
                ("datos", models.JSONField(blank=True, default=dict)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                ("caduca_en", models.DateTimeField()),
                ("resuelta_en", models.DateTimeField(blank=True, null=True)),
                (
                    "via",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("bandeja", "Bandeja"),
                            ("codigo", "Código por teléfono"),
                            ("delegacion", "Delegación temporal"),
                        ],
                        max_length=12,
                    ),
                ),
                ("nota_resolucion", models.CharField(blank=True, max_length=300)),
                (
                    "resuelta_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "solicitante",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="solicitudes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "titular",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="solicitudes",
                        to="titulares.titular",
                    ),
                ),
            ],
            options={
                "ordering": ["-creada"],
            },
        ),
    ]
