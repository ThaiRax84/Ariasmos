from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from proyecto import certificado, equipo


class Command(BaseCommand):
    help = "Genera el certificado único del servidor (sin autoridad de certificados) para el nombre del equipo"

    def add_arguments(self, parser):
        parser.add_argument("--nombre", required=True, help="Nombre del equipo; se sanea a letras, dígitos y guion")
        parser.add_argument("--cert", required=True, help="Ruta absoluta del certificado público")
        parser.add_argument("--clave", required=True, help="Ruta absoluta de la clave privada")
        parser.add_argument("--si-hace-falta", action="store_true", help="Conserva el certificado existente salvo que no incluya el nombre o venza en menos de 60 días")

    def handle(self, *args, **opciones):
        cert, clave = Path(opciones["cert"]), Path(opciones["clave"])
        if not cert.is_absolute() or not clave.is_absolute():
            raise CommandError("Las rutas del certificado y de la clave deben ser absolutas.")
        if opciones["nombre"] and not equipo.sanear(opciones["nombre"]):
            raise CommandError("El nombre del equipo no tiene letras ni dígitos válidos.")
        motivo = certificado.motivo_para_regenerar(cert, opciones["nombre"])
        if opciones["si_hace_falta"] and not motivo and clave.is_file():
            actual = certificado.cargar(cert.read_bytes())
            self.stdout.write(f"CERTIFICADO: conservado {certificado.huella(actual)} vence {certificado.vence(actual):%Y-%m-%d}")
            return
        nuevo = certificado.generar(opciones["nombre"], cert, clave)
        razon = motivo if opciones["si_hace_falta"] else "pedido"
        self.stdout.write(f"CERTIFICADO: nuevo {certificado.huella(nuevo)} vence {certificado.vence(nuevo):%Y-%m-%d} ({razon or 'falta la clave'})")
