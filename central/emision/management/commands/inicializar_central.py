import base64
import os
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat, load_pem_private_key
from django.core.management.base import BaseCommand, CommandError

from proyecto_central import instancia

MANAGE = Path(__file__).resolve().parents[3] / "manage.py"


def _llave(base):
    ruta = base / instancia.LLAVE
    if ruta.exists():
        return load_pem_private_key(ruta.read_bytes(), password=None)
    llave = Ed25519PrivateKey.generate()
    instancia.escribir_privado(ruta, llave.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    return llave


def _publica(llave):
    return base64.b64encode(llave.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode("ascii")


class Command(BaseCommand):
    help = "Prepara Central: crea su carpeta, su configuración, su base de datos y el par de llaves de las licencias"

    def add_arguments(self, parser):
        parser.add_argument("--carpeta", help="Carpeta donde vivirá Central; por omisión la de la variable CENTRAL_INSTANCIA")
        parser.add_argument("--host", action="append", default=[], help="Nombre con el que se llegará a Central (se puede repetir)")

    def handle(self, *args, **opciones):
        base = Path(opciones["carpeta"]).resolve() if opciones["carpeta"] else instancia.carpeta()
        if instancia.ruta_archivo(base).exists():
            self.stdout.write("Central ya estaba preparada en esa carpeta; no se cambió nada.")
        else:
            base.mkdir(parents=True, exist_ok=True)
            _llave(base)
            instancia.escribir(base, instancia.nueva(base, opciones["host"]))
            self.stdout.write(f"Central quedó preparada en {base}")
        llave = _llave(base)
        entorno = {**os.environ, "CENTRAL_INSTANCIA": str(base)}
        resultado = subprocess.run([sys.executable, str(MANAGE), "migrate", "--noinput", "-v", "0"], env=entorno, capture_output=True, text=True)
        if resultado.returncode != 0:
            raise CommandError(f"No se pudo preparar la base de datos de Central: {resultado.stderr.strip()[-300:]}")
        self.stdout.write("Esta es la llave pública. Cópiala dentro de \"licencias\" en sistema/licencias/llaves.json del programa:")
        self.stdout.write(_publica(llave))
        self.stdout.write("La llave privada se queda en esa carpeta. No la copies ni la compartas.")
