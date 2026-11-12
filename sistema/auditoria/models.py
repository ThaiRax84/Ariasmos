from datetime import timezone as tz

from django.conf import settings
from django.db import models

from nucleo.cadena import GENESIS


class EventoInmutable(Exception):
    pass


class ConsultaEventos(models.QuerySet):
    def update(self, **kwargs):
        raise EventoInmutable("los eventos de auditoria no se modifican")

    def delete(self):
        raise EventoInmutable("los eventos de auditoria no se borran")


class Evento(models.Model):
    momento = models.DateTimeField()
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    usuario_texto = models.CharField(max_length=150, blank=True)
    accion = models.CharField(max_length=60, db_index=True)
    objeto_tipo = models.CharField(max_length=60, blank=True)
    objeto_id = models.CharField(max_length=40, blank=True)
    datos = models.JSONField(default=dict, blank=True)
    ip = models.CharField(max_length=45, blank=True)
    hash_anterior = models.CharField(max_length=64, unique=True, default=GENESIS)
    hash = models.CharField(max_length=64, unique=True)

    objects = ConsultaEventos.as_manager()

    class Meta:
        ordering = ["-id"]

    def contenido(self):
        return {
            "momento": self.momento.astimezone(tz.utc).isoformat(),
            "usuario": self.usuario_id,
            "usuario_texto": self.usuario_texto,
            "accion": self.accion,
            "objeto_tipo": self.objeto_tipo,
            "objeto_id": self.objeto_id,
            "datos": self.datos,
            "ip": self.ip,
        }

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise EventoInmutable("los eventos de auditoria no se modifican")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise EventoInmutable("los eventos de auditoria no se borran")
