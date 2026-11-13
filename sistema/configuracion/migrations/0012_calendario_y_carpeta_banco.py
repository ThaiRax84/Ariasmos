import json
import re

from django.db import migrations, models

HORA = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


def a_calendario(apps, schema_editor):
    Parametro = apps.get_model("configuracion", "Parametro")
    anterior = Parametro.objects.filter(clave="hora_limite_corte_diario").first()
    if anterior is None:
        return
    hora = anterior.valor.strip() if HORA.match(anterior.valor.strip()) else "18:00"
    calendario = {str(dia): hora for dia in range(7)}
    Parametro.objects.update_or_create(clave="calendario_corte", defaults={"valor": json.dumps(calendario, separators=(",", ":"), sort_keys=True)})
    anterior.delete()


def a_hora(apps, schema_editor):
    Parametro = apps.get_model("configuracion", "Parametro")
    actual = Parametro.objects.filter(clave="calendario_corte").first()
    if actual is None:
        return
    try:
        horas = sorted(set(json.loads(actual.valor).values()))
    except ValueError:
        horas = []
    Parametro.objects.update_or_create(clave="hora_limite_corte_diario", defaults={"valor": horas[0] if horas else "18:00"})
    actual.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("configuracion", "0011_cortes_y_respaldo"),
    ]

    operations = [
        migrations.AddField(
            model_name="negocio",
            name="carpeta_banco",
            field=models.CharField(blank=True, max_length=400),
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
                    ("calendario_corte", "calendario_corte"),
                    ("dia_corte_mayor", "dia_corte_mayor"),
                    ("dias_plazo_corte_mayor", "dias_plazo_corte_mayor"),
                    ("dia_semana_cobranza", "dia_semana_cobranza"),
                    ("hora_respaldo", "hora_respaldo"),
                    ("control_denominaciones", "control_denominaciones"),
                    ("periodo_retiros", "periodo_retiros"),
                    ("tope_retiro_individual", "tope_retiro_individual"),
                    ("tope_retiros_periodo", "tope_retiros_periodo"),
                    ("maximo_retiros_periodo", "maximo_retiros_periodo"),
                    ("maximo_efectivo_caja", "maximo_efectivo_caja"),
                    ("dias_retiro_sin_revisar", "dias_retiro_sin_revisar"),
                    ("serie_retiros", "serie_retiros"),
                    (
                        "intentos_verificar_recibo_por_hora",
                        "intentos_verificar_recibo_por_hora",
                    ),
                    ("propuestas_cambio_sin_cobro", "propuestas_cambio_sin_cobro"),
                ],
                max_length=60,
                unique=True,
            ),
        ),
        migrations.RunPython(a_calendario, a_hora),
    ]
