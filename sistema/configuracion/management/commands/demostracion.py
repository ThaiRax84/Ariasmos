import secrets

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from auditoria.servicios import registrar
from caja.models import Caja
from caja.servicios import abrir_turno
from cobros import generacion
from cobros.models import ConceptoCobro, ReglaRecargo
from configuracion import plantillas
from configuracion.models import Negocio, hoy_negocio
from cuentas.models import Rol, Usuario
from nucleo import totp
from nucleo.recargos import sumar_meses
from solicitudes import motor
from titulares.models import Familia, Titular
from titulares.servicios import crear_titular

USUARIOS = [("operacion", "Usuario de operación", 1), ("supervision", "Usuario de supervisión", 2), ("direccion", "Usuario de dirección", 3)]


class Command(BaseCommand):
    help = "Configura una instalación vacía con datos de demostración (sin datos de ningún negocio real)"

    def add_arguments(self, parser):
        parser.add_argument("--plantilla", default="escuela")
        parser.add_argument("--contrasena", default="")

    def _datos_de_cobro(self):
        hoy = hoy_negocio()
        inicio = sumar_meses(hoy.replace(day=1), -2)
        Negocio.objects.filter(pk=1).update(cobro_desde=inicio)
        regla = ReglaRecargo.objects.create(nombre="Recargo de demostración", tipo=ReglaRecargo.FIJO, valor=10000, dias_gracia=5)
        importes = {ConceptoCobro.UNICO: 80000, ConceptoCobro.RECURRENTE: 150000, ConceptoCobro.POR_EVENTO: 30000}
        for concepto in ConceptoCobro.objects.all():
            concepto.importe_centavos = importes[concepto.tipo]
            if concepto.tipo == ConceptoCobro.RECURRENTE:
                concepto.dia_vencimiento = 10
                concepto.regla_recargo = regla
            concepto.save()
        direccion = Usuario.objects.get(usuario="direccion")
        iniciales = list(ConceptoCobro.objects.filter(aplica_a=ConceptoCobro.NUEVOS, tipo=ConceptoCobro.UNICO))
        familia = Familia.objects.create(nombre="Familia de demostración")
        for nombre, apellidos, con_familia in (("Ana", "Ejemplo Uno", True), ("Beto", "Ejemplo Uno", True), ("Carla", "Ejemplo Dos", False), ("Diego", "Ejemplo Tres", False)):
            titular = crear_titular(direccion, {"nombre": nombre, "apellidos": apellidos, "familia": familia if con_familia else None, "constancia_consentimiento": True}, contacto={"nombre": f"Responsable de {nombre}", "valores": {}}, conceptos=iniciales)
            motor.ejecutar("alta", direccion, titular)
            Titular.objects.filter(pk=titular.pk).update(activo_desde=inicio)
        generacion.generar_recurrentes(hoy)
        generacion.generar_recargos(hoy)
        caja = Caja.objects.filter(activa=True).first() or Caja.objects.create(nombre="Caja 1")
        abrir_turno(Usuario.objects.get(usuario="operacion"), caja, 50000)
        self.stdout.write("Datos de cobro: 4 titulares (2 en una familia), cargos de los últimos 3 meses con recargos y un turno abierto para operacion.")

    def handle(self, *args, **opciones):
        negocio = Negocio.actual()
        if negocio and negocio.configurado:
            raise CommandError("La instalación ya está configurada.")
        contrasena = opciones["contrasena"] or secrets.token_urlsafe(12)
        with transaction.atomic():
            Negocio.objects.update_or_create(
                pk=1,
                defaults={"nombre": "Negocio de demostración", "plantilla": opciones["plantilla"], "configurado": True},
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
        self._datos_de_cobro()
        self.stdout.write(f"Contraseña de los tres usuarios: {contrasena}")
        self.stdout.write("Aprueba tu navegador con: python manage.py aprobar_dispositivo CODIGO")
