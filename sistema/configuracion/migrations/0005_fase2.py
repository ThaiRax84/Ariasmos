from datetime import date

from django.db import migrations, models


def inicio_de_cobro(apps, schema_editor):
    Negocio = apps.get_model("configuracion", "Negocio")
    Negocio.objects.filter(configurado=True, cobro_desde__isnull=True).update(cobro_desde=date.today())


class Migration(migrations.Migration):

    dependencies = [
        ("configuracion", "0004_nota_ficha"),
    ]

    operations = [
        migrations.AddField(
            model_name="negocio",
            name="cobro_desde",
            field=models.DateField(blank=True, null=True),
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
                ],
                max_length=30,
                unique=True,
            ),
        ),
        migrations.RunPython(inicio_de_cobro, migrations.RunPython.noop),
    ]
