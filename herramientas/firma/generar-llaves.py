import argparse
import getpass
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comun import EXTENSION_PRIVADA, ErrorFirma, escribir_nuevo, pedir_contrasena_nueva, principal, privada_cifrada, publica_texto


def generar(argv=None, pedir=getpass.getpass):
    lector = argparse.ArgumentParser(description="Genera la llave de uso y la llave de recuperación de las actualizaciones de Ariasmos.")
    lector.add_argument("carpeta", help="Carpeta donde se guardan las llaves privadas cifradas (fuera del repositorio)")
    opciones = lector.parse_args(argv)
    carpeta = Path(opciones.carpeta).resolve()
    if not carpeta.is_dir():
        raise ErrorFirma("La carpeta no existe.")
    destinos = {nombre: carpeta / f"{nombre}{EXTENSION_PRIVADA}" for nombre in ("uso", "recuperacion")}
    if any(ruta.exists() for ruta in destinos.values()) or (carpeta / "llaves.json").exists():
        raise ErrorFirma("La carpeta ya tiene llaves; no se sobrescribe nada.")
    contrasenas = {"uso": pedir_contrasena_nueva("uso", pedir), "recuperacion": pedir_contrasena_nueva("recuperación", pedir)}
    if contrasenas["uso"] == contrasenas["recuperacion"]:
        raise ErrorFirma("Usa una contraseña distinta para cada llave.")
    llaves = {nombre: Ed25519PrivateKey.generate() for nombre in destinos}
    publicas = {nombre: publica_texto(llave) for nombre, llave in llaves.items()}
    for nombre, llave in llaves.items():
        escribir_nuevo(destinos[nombre], privada_cifrada(llave, contrasenas[nombre]), privado=True)
    contenido = (json.dumps({"uso": publicas["uso"], "recuperacion": publicas["recuperacion"]}, indent=2) + "\n").encode("ascii")
    escribir_nuevo(carpeta / "llaves.json", contenido)
    print(f"Llaves privadas cifradas: {destinos['uso']} y {destinos['recuperacion']}")
    print(f"Llaves públicas en {carpeta / 'llaves.json'}; copia ese archivo a sistema/actualizaciones/llaves.json:")
    print(contenido.decode("ascii"))
    return publicas


if __name__ == "__main__":
    sys.exit(principal(generar))
