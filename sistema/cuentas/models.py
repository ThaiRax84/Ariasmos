from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .permisos import OPCIONES


class Rol(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    nivel = models.PositiveSmallIntegerField(default=1)
    minutos_inactividad = models.PositiveIntegerField(default=30)
    requiere_totp = models.BooleanField(default=False)

    class Meta:
        ordering = ["nivel", "nombre"]

    def __str__(self):
        return self.nombre

    def permisos(self):
        return set(self.asignaciones.values_list("permiso", flat=True))


class PermisoRol(models.Model):
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name="asignaciones")
    permiso = models.CharField(max_length=40, choices=OPCIONES)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["rol", "permiso"], name="permiso_rol_unico")]


class GestorUsuarios(BaseUserManager):
    def create_user(self, usuario, password=None, **extra):
        nuevo = self.model(usuario=usuario, **extra)
        nuevo.set_password(password)
        nuevo.save(using=self._db)
        return nuevo


class Usuario(AbstractBaseUser):
    usuario = models.CharField(max_length=60, unique=True)
    nombre = models.CharField(max_length=150)
    rol = models.ForeignKey(Rol, null=True, blank=True, on_delete=models.PROTECT, related_name="usuarios")
    activo = models.BooleanField(default=True)
    totp_cifrado = models.CharField(max_length=255, blank=True)
    totp_confirmado = models.BooleanField(default=False)
    intentos_fallidos = models.PositiveIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "usuario"
    REQUIRED_FIELDS = ["nombre"]

    objects = GestorUsuarios()

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre or self.usuario

    @property
    def is_active(self):
        return self.activo

    def get_full_name(self):
        return self.nombre

    def get_short_name(self):
        return self.usuario

    def permisos_de_rol(self):
        if not hasattr(self, "_permisos_rol"):
            self._permisos_rol = self.rol.permisos() if self.rol_id else set()
        return self._permisos_rol

    def permisos_delegados(self):
        if not hasattr(self, "_permisos_delegados"):
            self._permisos_delegados = set(Delegacion.objects.vigentes().filter(receptor=self).values_list("permiso", flat=True))
        return self._permisos_delegados

    def permisos_efectivos(self):
        if not self.activo:
            return set()
        return self.permisos_de_rol() | self.permisos_delegados()

    def tiene_permiso_de_rol(self, permiso):
        return self.activo and permiso in self.permisos_de_rol()

    def tiene_permiso(self, permiso):
        return permiso in self.permisos_efectivos()

    def olvidar_permisos(self):
        for atributo in ("_permisos_rol", "_permisos_delegados"):
            if hasattr(self, atributo):
                delattr(self, atributo)

    def esta_bloqueado(self, ahora=None):
        return self.bloqueado_hasta is not None and self.bloqueado_hasta > (ahora or timezone.now())


class Dispositivo(models.Model):
    PENDIENTE = "pendiente"
    APROBADO = "aprobado"
    REVOCADO = "revocado"
    ESTADOS = [(PENDIENTE, "Pendiente"), (APROBADO, "Aprobado"), (REVOCADO, "Revocado")]

    hash_credencial = models.CharField(max_length=64, unique=True)
    codigo = models.CharField(max_length=8, db_index=True)
    nombre = models.CharField(max_length=100, blank=True)
    agente = models.CharField(max_length=300, blank=True)
    ip = models.CharField(max_length=45, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    creado = models.DateTimeField(auto_now_add=True)
    aprobado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    aprobado_en = models.DateTimeField(null=True, blank=True)
    revocado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    revocado_en = models.DateTimeField(null=True, blank=True)
    ultimo_uso = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return self.nombre or self.codigo

    @property
    def aprobado(self):
        return self.estado == self.APROBADO


class ConsultaDelegaciones(models.QuerySet):
    def vigentes(self, ahora=None):
        ahora = ahora or timezone.now()
        return (
            self.filter(revocada=False, receptor__activo=True)
            .filter(Q(vence__isnull=True) | Q(vence__gt=ahora))
            .filter(Q(usos_maximos__isnull=True) | Q(usos__lt=F("usos_maximos")))
        )


class Delegacion(models.Model):
    otorgante = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="delegaciones_otorgadas")
    receptor = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="delegaciones")
    permiso = models.CharField(max_length=40, choices=OPCIONES)
    vence = models.DateTimeField(null=True, blank=True)
    usos_maximos = models.PositiveIntegerField(null=True, blank=True)
    usos = models.PositiveIntegerField(default=0)
    motivo = models.CharField(max_length=200, blank=True)
    revocada = models.BooleanField(default=False)
    revocada_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    creada = models.DateTimeField(auto_now_add=True)

    objects = ConsultaDelegaciones.as_manager()

    class Meta:
        ordering = ["-creada"]
        constraints = [
            models.CheckConstraint(condition=Q(vence__isnull=False) | Q(usos_maximos__isnull=False), name="delegacion_con_limite"),
            models.CheckConstraint(condition=~Q(otorgante=F("receptor")), name="delegacion_a_otro"),
        ]

    def vigente(self, ahora=None):
        ahora = ahora or timezone.now()
        if self.revocada:
            return False
        if self.vence is not None and self.vence <= ahora:
            return False
        if self.usos_maximos is not None and self.usos >= self.usos_maximos:
            return False
        return True


class CodigoUsado(models.Model):
    INICIO_SESION = "inicio_sesion"
    AUTORIZACION = "autorizacion"
    ALTA = "alta"
    PROPOSITOS = [(INICIO_SESION, "Inicio de sesión"), (AUTORIZACION, "Autorización por teléfono"), (ALTA, "Alta del autenticador")]

    SIN_REVISION = "no_aplica"
    POR_REVISAR = "por_revisar"
    CONFIRMADO = "confirmado"
    REPORTADO = "reportado"
    REVISIONES = [(SIN_REVISION, "No aplica"), (POR_REVISAR, "Por revisar"), (CONFIRMADO, "Confirmado"), (REPORTADO, "Reportado")]

    autorizador = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="codigos_usados")
    paso = models.BigIntegerField()
    proposito = models.CharField(max_length=20, choices=PROPOSITOS)
    usado_en = models.DateTimeField(auto_now_add=True)
    usado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    solicitud = models.ForeignKey("solicitudes.Solicitud", null=True, blank=True, on_delete=models.PROTECT, related_name="codigos")
    revision = models.CharField(max_length=12, choices=REVISIONES, default=SIN_REVISION)
    revisado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-usado_en"]
        constraints = [models.UniqueConstraint(fields=["autorizador", "paso"], name="codigo_un_solo_uso")]


class CodigoActivacion(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="codigos_activacion")
    hash_codigo = models.CharField(max_length=64, unique=True)
    creado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    creado = models.DateTimeField(auto_now_add=True)
    caduca = models.DateTimeField()
    usado_en = models.DateTimeField(null=True, blank=True)
    invalidado = models.BooleanField(default=False)

    class Meta:
        ordering = ["-creado"]

    def vigente(self, ahora=None):
        return self.usado_en is None and not self.invalidado and self.caduca > (ahora or timezone.now())
