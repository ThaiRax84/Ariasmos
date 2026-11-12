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
    numero = models.PositiveBigIntegerField(unique=True)
    momento = models.DateTimeField()
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    usuario_texto = models.CharField(max_length=150, blank=True)
    equipo = models.BigIntegerField(null=True, blank=True)
    accion = models.CharField(max_length=60, db_index=True)
    objeto_tipo = models.CharField(max_length=60, blank=True)
    objeto_id = models.CharField(max_length=40, blank=True)
    titular = models.BigIntegerField(null=True, blank=True, db_index=True)
    datos = models.JSONField(default=dict, blank=True)
    ip = models.CharField(max_length=45, blank=True)
    sello_anterior = models.CharField(max_length=64, unique=True, default=GENESIS)
    sello = models.CharField(max_length=64, unique=True)

    objects = ConsultaEventos.as_manager()

    class Meta:
        ordering = ["-numero"]

    def contenido(self):
        return {
            "numero": self.numero,
            "momento": self.momento.astimezone(tz.utc).isoformat(),
            "usuario": self.usuario_id,
            "usuario_texto": self.usuario_texto,
            "equipo": self.equipo,
            "accion": self.accion,
            "objeto_tipo": self.objeto_tipo,
            "objeto_id": self.objeto_id,
            "titular": self.titular,
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


class Verificacion(models.Model):
    momento = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    valida = models.BooleanField()
    numero = models.PositiveBigIntegerField(null=True, blank=True)
    motivo = models.CharField(max_length=40, blank=True)
    eventos = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["-momento", "-id"]
