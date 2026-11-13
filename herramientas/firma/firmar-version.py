import argparse
import getpass
import hashlib
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comun import ErrorFirma, escribir_nuevo, leer_privada, modulo_aviso, principal, publica_texto


def firmar(argv=None, pedir=getpass.getpass):
    aviso = modulo_aviso()
    lector = argparse.ArgumentParser(description="Escribe y firma el aviso de versión (version.json y version.json.firma).")
    lector.add_argument("--instalador", required=True, help="Instalador .exe que se va a publicar")
    lector.add_argument("--version", required=True, help="Versión X.Y.Z")
    lector.add_argument("--contador", required=True, type=int, help="Número que siempre sube: mayor que el de la versión publicada antes")
    lector.add_argument("--cambios", required=True, help="Archivo de texto con una línea por cambio (hasta 20 líneas de 200 caracteres)")
    lector.add_argument("--minimo", required=True, help="Versión mínima desde la que se puede actualizar")
    lector.add_argument("--llave", required=True, help="Llave de uso privada (.llave-privada)")
    lector.add_argument("--salida", required=True, help="Carpeta donde se escriben version.json y version.json.firma")
    lector.add_argument("--fecha", default=date.today().isoformat(), help="Fecha de publicación AAAA-MM-DD (por omisión, hoy)")
    opciones = lector.parse_args(argv)
    instalador = Path(opciones.instalador)
    if not instalador.is_file():
        raise ErrorFirma("No existe el instalador.")
    lineas = [linea.strip() for linea in Path(opciones.cambios).read_text(encoding="utf-8").splitlines() if linea.strip()]
    huella = hashlib.sha256()
    tamano = 0
    with instalador.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            huella.update(bloque)
            tamano += len(bloque)
    objeto = {
        "producto": aviso.PRODUCTO,
        "version": opciones.version,
        "contador": opciones.contador,
        "fecha": opciones.fecha,
        "instalador": {"nombre": instalador.name, "tamano": tamano, "sha256": huella.hexdigest()},
        "minimo": opciones.minimo,
        "cambios": lineas,
    }
    datos = aviso.serializar(objeto)
    llave = leer_privada(opciones.llave, pedir, "la llave de uso")
    firma = llave.sign(datos)
    try:
        aviso.leer_version(datos, firma, publica_texto(llave))
    except aviso.AvisoInvalido as error:
        raise ErrorFirma(f"El aviso no es válido: {error}")
    salida = Path(opciones.salida)
    if not salida.is_dir():
        raise ErrorFirma("La carpeta de salida no existe.")
    if (salida / "version.json").exists() or (salida / "version.json.firma").exists():
        raise ErrorFirma("La carpeta de salida ya tiene un aviso; usa una carpeta vacía.")
    escribir_nuevo(salida / "version.json", datos)
    escribir_nuevo(salida / "version.json.firma", firma)
    print(f"Aviso firmado: {salida / 'version.json'} (versión {opciones.version}, contador {opciones.contador}, SHA-256 {huella.hexdigest()})")
    return datos, firma


if __name__ == "__main__":
    sys.exit(principal(firmar))
