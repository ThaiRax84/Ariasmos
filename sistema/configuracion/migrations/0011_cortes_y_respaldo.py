from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("configuracion", "0010_periodo_cerrado"),
    ]

    operations = [
        migrations.AddField(
            model_name="negocio",
            name="carpeta_respaldo",
            field=models.CharField(blank=True, max_length=400),
        ),
        migrations.AddField(
            model_name="negocio",
            name="clave_recuperacion_pendiente",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="parametro",
            name="clave",
            field=models.CharField(
                choices=[
                    ("intentos_antes_de_bloqueo", "intentos_antes_de_bloqueo"),
                    ("minutos_bloqueo_inicial", "minutos_bloqueo_inicial"),
                    ("minutos_bloqueo_maximo", "minutos_bloqueo_maximo"),
                    ("minutos_validez_reingreso", "minutos_validez_reingreso"),
                    ("ventana_codigo_pasos", "ventana_codigo_pasos"),
                    ("dias_maximos_delegacion", "dias_maximos_delegacion"),
                    (
                        "intentos_por_equipo_cada_5_minutos",
                        "intentos_por_equipo_cada_5_minutos",
                    ),
                    ("intentos_codigo_por_solicitud", "intentos_codigo_por_solicitud"),
                    ("intentos_codigo_por_hora", "intentos_codigo_por_hora"),
                    ("maximo_equipos_pendientes", "maximo_equipos_pendientes"),
                    ("dia_generacion_cargos", "dia_generacion_cargos"),
                    ("orden_reparto", "orden_reparto"),
                    ("tope_pago_individual", "tope_pago_individual"),
                    ("umbral_diferencia_arqueo", "umbral_diferencia_arqueo"),
                    (
                        "dias_maximos_efectivo_sin_trasladar",
                        "dias_maximos_efectivo_sin_trasladar",
                    ),
                    (
                        "dias_maximos_deposito_sin_conciliar",
                        "dias_maximos_deposito_sin_conciliar",
                    ),
                    (
                        "confirmaciones_pagador_confiable",
                        "confirmaciones_pagador_confiable",
                    ),
                    ("aplicar_solo_por_pagador", "aplicar_solo_por_pagador"),
                    ("dias_tolerancia_deposito", "dias_tolerancia_deposito"),
                    ("serie_recibos_banco", "serie_recibos_banco"),
                    ("serie_recibos_saldo_inicial", "serie_recibos_saldo_inicial"),
                    (
                        "dias_alerta_recibos_cancelados",
                        "dias_alerta_recibos_cancelados",
                    ),
                    ("segundos_ciclo_trabajador", "segundos_ciclo_trabajador"),
                    (
                        "horas_validez_codigo_activacion",
                        "horas_validez_codigo_activacion",
                    ),
                    (
                        "maximo_altas_pendientes_por_capturista",
                        "maximo_altas_pendientes_por_capturista",
                    ),
                    ("prefijo_pais_telefono", "prefijo_pais_telefono"),
                    ("digitos_telefono_nacional", "digitos_telefono_nacional"),
                    ("hora_limite_corte_diario", "hora_limite_corte_diario"),
                    ("dia_corte_mayor", "dia_corte_mayor"),
                    ("dias_plazo_corte_mayor", "dias_plazo_corte_mayor"),
                    ("dia_semana_cobranza", "dia_semana_cobranza"),
                    ("hora_respaldo", "hora_respaldo"),
                ],
                max_length=60,
                unique=True,
            ),
        ),
    ]
