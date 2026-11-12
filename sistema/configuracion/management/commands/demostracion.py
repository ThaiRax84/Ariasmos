import secrets

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from auditoria.servicios import registrar
from configuracion import plantillas
from configuracion.models import Negocio
from cuentas.models import Rol, Usuario
from nucleo import totp

USUARIOS = [("operacion", "Usuario de operación", 1), ("supervision", "Usuario de supervisión", 2), ("direccion", "Usuario de dirección", 3)]


class Command(BaseCommand):
    help = "Configura una instalación vacía con datos de demostración (sin datos de ningún negocio real)"

    def add_arguments(self, parser):
        parser.add_argument("--plantilla", default="escuela")
        parser.add_argument("--contrasena", default="")

    def handle(self, *args, **opciones):
        negocio = Negocio.actual()
        if negocio and negocio.configurado:
            raise CommandError("La instalación ya está configurada.")
        contrasena = opciones["contrasena"] or secrets.token_urlsafe(12)
        with transaction.atomic():
            Negocio.objects.update_or_create(
                pk=1,
                defaults={"nombre": "Negocio de demostración", "instrucciones_pago": "Instrucciones de pago de ejemplo.", "plantilla": opciones["plantilla"], "configurado": True},
            )
            plantillas.cargar(opciones["plantilla"])
            roles = {rol.nivel: rol for rol in Rol.objects.all()}
            for usuario, nombre, nivel in USUARIOS:
                secreto = totp.generar_secreto()
                creado = Usuario.objects.create_user(usuario, contrasena, nombre=nombre, rol=roles[nivel])
                if roles[nivel].requiere_totp:
                    creado.totp_secreto = secreto
                    creado.totp_confirmado = True
                    creado.save()
                    self.stdout.write(f"{usuario}: secreto del autenticador {secreto}")
                else:
                    self.stdout.write(f"{usuario}: sin autenticador")
            registrar("demostracion_creada", datos={"plantilla": opciones["plantilla"]})
        self.stdout.write(f"Contraseña de los tres usuarios: {contrasena}")
        self.stdout.write("Aprueba tu navegador con: python manage.py aprobar_dispositivo CODIGO")
