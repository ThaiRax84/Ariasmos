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


def _llave_nueva(base):
    ruta = base / instancia.LLAVE
    if ruta.exists():
        return load_pem_private_key(ruta.read_bytes(), password=None), False
    llave = Ed25519PrivateKey.generate()
    instancia.escribir_privado(ruta, llave.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    return llave, True


def _llave_existente(datos):
    ruta = Path(datos["llave_licencias"])
    if not ruta.exists():
        raise CommandError(f"Central ya tiene configuración, pero falta el archivo de la llave ({ruta}). No se creó ninguna llave nueva para no invalidar las licencias ya entregadas: recupera el archivo desde tu respaldo.")
    return load_pem_private_key(ruta.read_bytes(), password=None)


def _publica(llave):
    return base64.b64encode(llave.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode("ascii")


class Command(BaseCommand):
    help = "Prepara Central: crea su carpeta, su configuración, su base de datos y el par de llaves de las licencias"

    def add_arguments(self, parser):
        parser.add_argument("--carpeta", help="Carpeta donde vivirá Central; por omisión la de la variable CENTRAL_INSTANCIA")
        parser.add_argument("--host", action="append", default=[], help="Nombre con el que se llegará a Central (se puede repetir)")

    def _preparar(self, base, hosts):
        datos = instancia.leer(base)
        if datos is not None:
            self.stdout.write("Central ya estaba preparada en esa carpeta; no se cambió su configuración ni sus llaves.")
            return _llave_existente(datos)
        base.mkdir(parents=True, exist_ok=True)
        llave, nueva = _llave_nueva(base)
        instancia.escribir(base, instancia.nueva(base, hosts))
        self.stdout.write(f"Central quedó preparada en {base}")
        self.stdout.write("Se creó la llave de las licencias." if nueva else "Se usó la llave que ya estaba en esa carpeta.")
        return llave

    def handle(self, *args, **opciones):
        base = Path(opciones["carpeta"]).resolve() if opciones["carpeta"] else instancia.carpeta()
        llave = self._preparar(base, opciones["host"])
        entorno = {**os.environ, "CENTRAL_INSTANCIA": str(base)}
        resultado = subprocess.run([sys.executable, str(MANAGE), "migrate", "--noinput", "-v", "0"], env=entorno, capture_output=True, text=True)
        if resultado.returncode != 0:
            raise CommandError(f"No se pudo preparar la base de datos de Central: {resultado.stderr.strip()[-300:]}")
        self.stdout.write("Esta es la llave pública. Cópiala dentro de \"licencias\" en sistema/licencias/llaves.json del programa:")
        self.stdout.write(_publica(llave))
        self.stdout.write("La llave privada se queda en esa carpeta. No la copies ni la compartas.")
