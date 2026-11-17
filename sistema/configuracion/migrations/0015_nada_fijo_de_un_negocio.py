from django.db import migrations, models


CONSERVADOS = {"descuento": "Beca", "padron": "Padrón", "publico": "Público en general"}


def conservar(apps, schema_editor):
    Negocio = apps.get_model("configuracion", "Negocio")
    Vocabulario = apps.get_model("configuracion", "Vocabulario")
    if not Negocio.objects.exists():
        return
    for clave, texto in CONSERVADOS.items():
        Vocabulario.objects.get_or_create(clave=clave, defaults={"texto": texto})


class Migration(migrations.Migration):

    dependencies = [
        ("configuracion", "0014_marca_y_existencia_baja"),
    ]

    operations = [
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
                    ("tope_aplicado_sin_respaldo", "tope_aplicado_sin_respaldo"),
                    ("tope_pago_carpeta", "tope_pago_carpeta"),
                    ("dias_sin_respaldo_alerta", "dias_sin_respaldo_alerta"),
                    ("modulo_inventario", "modulo_inventario"),
                    ("devoluciones_inventario", "devoluciones_inventario"),
                    ("dias_devolucion", "dias_devolucion"),
                    ("dias_conteo_sin_aprobar", "dias_conteo_sin_aprobar"),
                    ("serie_devoluciones", "serie_devoluciones"),
                    ("tramos_cartera", "tramos_cartera"),
                    ("tamano_hoja", "tamano_hoja"),
                    ("pedir_consentimiento", "pedir_consentimiento"),
                    ("texto_consentimiento", "texto_consentimiento"),
                    ("apellidos_obligatorios", "apellidos_obligatorios"),
                    ("respaldos_diarios", "respaldos_diarios"),
                    ("respaldos_mensuales", "respaldos_mensuales"),
                    ("horas_alerta_respaldo", "horas_alerta_respaldo"),
                    ("dias_prueba_restauracion", "dias_prueba_restauracion"),
                    ("rechazos_antes_de_autorizar", "rechazos_antes_de_autorizar"),
                    ("porcentaje_aviso_tope", "porcentaje_aviso_tope"),
                    ("porcentaje_existencia_baja", "porcentaje_existencia_baja"),
                ],
                max_length=60,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="vocabulario",
            name="clave",
            field=models.CharField(
                choices=[
                    ("titular", "titular"),
                    ("titulares", "titulares"),
                    ("matricula", "matricula"),
                    ("agrupacion", "agrupacion"),
                    ("agrupaciones", "agrupaciones"),
                    ("familia", "familia"),
                    ("familias", "familias"),
                    ("padron", "padron"),
                    ("descuento", "descuento"),
                    ("publico", "publico"),
                ],
                max_length=30,
                unique=True,
            ),
        ),
        migrations.RunPython(conservar, migrations.RunPython.noop),
    ]
