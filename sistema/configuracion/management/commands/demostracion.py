import secrets
import tempfile
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from auditoria.servicios import registrar
from banco import conciliacion
from banco.models import Banco, CuentaBancaria, Importacion
from caja.models import Caja
from caja.servicios import abrir_turno, cerrar_turno
from cobros import generacion, libro
from cobros.models import ConceptoCobro, Pago, ReglaRecargo
from configuracion import plantillas
from configuracion.models import Negocio, Parametro, hoy_negocio
from cortes import servicios as cortes
from cortes.models import TIPOS as TIPOS_CORTE
from cortes.models import DefinicionCorte, Destino, ReglaDestino
from cuentas import secretos
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
        self._banco(Usuario.objects.get(usuario="supervision"))
        self._cortes()
        self.stdout.write("Datos de cobro: 4 titulares (2 en una familia), cargos de los últimos 3 meses con recargos y un turno abierto para operacion.")

    def _banco(self, importador):
        cuenta = CuentaBancaria.principal_activa() or CuentaBancaria.objects.create(
            banco=Banco.objects.get(clave="002"), clabe="002010077777777771", beneficiario="Negocio de demostración", contacto_dudas="5500000000", principal=True
        )
        titulares = list(Titular.objects.order_by("pk"))
        ayer = hoy_negocio() - timedelta(days=1)
        mala = titulares[2].matricula[:3] + str((int(titulares[2].matricula[3]) + 1) % 10) + titulares[2].matricula[4:]
        movimientos = []
        for numero, (referencia, concepto, importe, nombre) in enumerate(
            ((titulares[0].matricula, "colegiatura", 150000, "PERSONA DE DEMOSTRACION UNO"), (mala, "pago", 80000, "PERSONA DE DEMOSTRACION DOS"), ("", "pago de mi hijo", 30000, "PERSONA DE DEMOSTRACION TRES"))
        ):
            movimientos.append(
                {
                    "fecha": ayer.isoformat(), "folio": "", "descripcion": "ABONO DE DEMOSTRACION", "importe": importe, "saldo": None,
                    "sentido": "abono", "clase": "archivo", "hora": "", "banco_origen": "", "cuenta_pagador": "", "nombre_pagador": nombre,
                    "rastreo": "", "referencia": referencia, "concepto": concepto, "huella": f"{cuenta.clabe}|demostracion|{numero}",
                }
            )
        importacion = conciliacion.importar(cuenta, movimientos, Importacion.ARCHIVO, "demostracion.csv", "0" * 64, importador)
        self.stdout.write(f"Banco: cuenta ficticia {cuenta.clabe}; {importacion.aplicados} abono aplicado solo y {importacion.sugeridos + importacion.sin_pista} en la cola por identificar; la importación queda pendiente de revisión para direccion.")

    def _cortes(self):
        carpeta = tempfile.mkdtemp(prefix="ariasmos-demo-cortes-")
        destino = Destino.objects.create(nombre="Carpeta de demostración", ruta=carpeta)
        for tipo, _ in TIPOS_CORTE:
            definicion = DefinicionCorte.objects.filter(tipo=tipo).first()
            ReglaDestino.objects.create(destino=destino, tipo=tipo, nivel=definicion.nivel if definicion else "solo_nombres")
        supervision = Usuario.objects.get(usuario="supervision")
        caja = Caja.objects.filter(activa=True).exclude(turnos__estado="abierto").first() or Caja.objects.create(nombre="Caja 2")
        turno = abrir_turno(supervision, caja, 0)
        titular = Titular.objects.order_by("pk").last()
        libro.registrar_pago(titular, 50000, Pago.EFECTIVO, supervision, turno=turno)
        cerrar_turno(turno, supervision, {"50000": 1})
        Parametro.objects.update_or_create(clave="dias_plazo_corte_mayor", defaults={"valor": "31"})
        mayores = cortes.generar_mayores()
        hechas, _ = cortes.ejecutar_entregas()
        self.stdout.write(f"Cortes: un corte diario de supervision, {len(mayores)} corte(s) mayor(es) en borrador (plazo de cierre de 31 días para la demostración) y {hechas} entrega(s) en la carpeta temporal {carpeta}.")

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
                    secretos.guardar(creado, secreto)
                    creado.totp_confirmado = True
                    creado.save()
                    self.stdout.write(f"{usuario}: secreto del autenticador {secreto}")
                else:
                    self.stdout.write(f"{usuario}: sin autenticador")
            registrar("demostracion_creada", datos={"plantilla": opciones["plantilla"]})
        self._datos_de_cobro()
        self.stdout.write(f"Contraseña de los tres usuarios: {contrasena}")
        self.stdout.write("Aprueba tu navegador con: python manage.py aprobar_dispositivo CODIGO")
