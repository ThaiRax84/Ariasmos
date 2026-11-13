import argparse
import getpass
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comun import EXTENSION_PRIVADA, ErrorFirma, escribir_nuevo, leer_privada, modulo_aviso, pedir_contrasena_nueva, principal, privada_cifrada, publica_texto


def cambiar(argv=None, pedir=getpass.getpass):
    aviso = modulo_aviso()
    lector = argparse.ArgumentParser(description="Crea una llave de uso nueva y firma el cambio con la llave de recuperación.")
    lector.add_argument("--recuperacion", required=True, help="Llave de recuperación privada (.llave-privada)")
    lector.add_argument("--contador", required=True, type=int, help="Número que siempre sube: mayor que el del cambio de llave anterior")
    lector.add_argument("--carpeta-llave", required=True, help="Carpeta donde se guarda la llave de uso nueva, cifrada")
    lector.add_argument("--salida", required=True, help="Carpeta donde se escriben cambio-de-llave.json y su firma")
    opciones = lector.parse_args(argv)
    destino = Path(opciones.carpeta_llave) / f"uso-{opciones.contador}{EXTENSION_PRIVADA}"
    salida = Path(opciones.salida)
    if not destino.parent.is_dir() or not salida.is_dir():
        raise ErrorFirma("Las carpetas deben existir.")
    if destino.exists() or (salida / "cambio-de-llave.json").exists():
        raise ErrorFirma("Ya existe un archivo con ese nombre; no se sobrescribe nada.")
    recuperacion = leer_privada(opciones.recuperacion, pedir, "la llave de recuperación")
    contrasena = pedir_contrasena_nueva("uso nueva", pedir)
    nueva = Ed25519PrivateKey.generate()
    objeto = {"producto": aviso.PRODUCTO, "contador": opciones.contador, "llave_uso": publica_texto(nueva)}
    datos = aviso.serializar(objeto)
    firma = recuperacion.sign(datos)
    try:
        aviso.leer_cambio_de_llave(datos, firma, publica_texto(recuperacion))
    except aviso.AvisoInvalido as error:
        raise ErrorFirma(f"El cambio de llave no es válido: {error}")
    escribir_nuevo(destino, privada_cifrada(nueva, contrasena), privado=True)
    escribir_nuevo(salida / "cambio-de-llave.json", datos)
    escribir_nuevo(salida / "cambio-de-llave.json.firma", firma)
    print(f"Llave de uso nueva, cifrada: {destino}")
    print(f"Cambio de llave firmado: {salida / 'cambio-de-llave.json'} (contador {opciones.contador})")
    return objeto["llave_uso"]


if __name__ == "__main__":
    sys.exit(principal(cambiar))
