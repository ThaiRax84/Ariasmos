import hashlib
import json
from datetime import timezone as tz

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

GENESIS = "0" * 64


def _canonico(contenido):
    return json.dumps(contenido, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def resellar(apps, schema_editor):
    from auditoria import ancla
    from nucleo import cadena

    Evento = apps.get_model("auditoria", "Evento")
    eventos = list(Evento.objects.order_by("id"))
    anterior_viejo = GENESIS
    for evento in eventos:
        evento.contenido_viejo = {
            "momento": evento.momento.astimezone(tz.utc).isoformat(),
            "usuario": evento.usuario_id,
            "usuario_texto": evento.usuario_texto,
            "accion": evento.accion,
            "objeto_tipo": evento.objeto_tipo,
            "objeto_id": evento.objeto_id,
            "datos": evento.datos,
            "ip": evento.ip,
        }
        esperado = hashlib.sha256((anterior_viejo + "|" + _canonico(evento.contenido_viejo)).encode("utf-8")).hexdigest()
        if evento.sello_anterior != anterior_viejo or evento.sello != esperado:
            raise RuntimeError(f"La cadena anterior no es integra en el evento {evento.pk}; no se puede sellar")
        anterior_viejo = evento.sello
    for evento in eventos:
        Evento.objects.filter(pk=evento.pk).update(sello_anterior="a" + str(evento.pk).rjust(63, "0"), sello="b" + str(evento.pk).rjust(63, "0"))
    anterior = GENESIS
    for numero, evento in enumerate(eventos, start=1):
        contenido = dict(evento.contenido_viejo, numero=numero, equipo=None, titular=None)
        sello = cadena.sellar(settings.CLAVE_AUDITORIA, anterior, contenido)
        Evento.objects.filter(pk=evento.pk).update(numero=numero, sello_anterior=anterior, sello=sello)
        anterior = sello
    if eventos:
        ancla.escribir(len(eventos), anterior, eventos[-1].momento.isoformat())


class Migration(migrations.Migration):
    dependencies = [
        ("auditoria", "0002_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField("evento", "hash", "sello"),
        migrations.RenameField("evento", "hash_anterior", "sello_anterior"),
        migrations.AddField("evento", "numero", models.PositiveBigIntegerField(null=True)),
        migrations.AddField("evento", "equipo", models.BigIntegerField(blank=True, null=True)),
        migrations.AddField("evento", "titular", models.BigIntegerField(blank=True, db_index=True, null=True)),
        migrations.RunPython(resellar, migrations.RunPython.noop),
        migrations.AlterField("evento", "numero", models.PositiveBigIntegerField(unique=True)),
        migrations.AlterModelOptions("evento", {"ordering": ["-numero"]}),
        migrations.CreateModel(
            name="Verificacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("momento", models.DateTimeField(auto_now_add=True)),
                ("valida", models.BooleanField()),
                ("numero", models.PositiveBigIntegerField(blank=True, null=True)),
                ("motivo", models.CharField(blank=True, max_length=40)),
                ("eventos", models.PositiveBigIntegerField(default=0)),
                ("usuario", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-momento", "-id"]},
        ),
    ]
