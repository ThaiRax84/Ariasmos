import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from actualizaciones import aviso
from actualizaciones.canales import Canal, Excedido, Recurso, SinConexion

INSTALADA = "0.8.0"
INSTALADOR = b"MZ" + bytes(range(256)) * 40


def par():
    privada = Ed25519PrivateKey.generate()
    publica = privada.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return privada, aviso.texto_de_llave(publica)


def objeto_version(version="0.9.0", contador=1, instalador=INSTALADOR, minimo="0.7.0", cambios=None, nombre="Ariasmos-0.9.0-instalador.exe"):
    return {
        "producto": "ariasmos",
        "version": version,
        "contador": contador,
        "fecha": "2026-11-20",
        "instalador": {"nombre": nombre, "tamano": len(instalador), "sha256": hashlib.sha256(instalador).hexdigest()},
        "minimo": minimo,
        "cambios": cambios if cambios is not None else ["Topes del banco por día", "Aviso de versiones nuevas"],
    }


def firmado(privada, objeto, crudo=None):
    datos = crudo if crudo is not None else aviso.serializar(objeto)
    return datos, privada.sign(datos)


class CanalFalso(Canal):
    def __init__(self, archivos=None, sin_conexion=False, entregar=None):
        self.archivos = dict(archivos or {})
        self.sin_conexion = sin_conexion
        self.entregar = entregar or {}
        self.pedidos = []

    def publicacion(self):
        if self.sin_conexion:
            raise SinConexion("sin conexión")
        return {nombre: Recurso(nombre=nombre, tamano=len(contenido), ident=str(numero + 1)) for numero, (nombre, contenido) in enumerate(self.archivos.items())}

    def descargar(self, recurso, escribir, limite, plazo):
        self.pedidos.append(recurso.nombre)
        if self.sin_conexion:
            raise SinConexion("sin conexión")
        contenido = self.entregar.get(recurso.nombre, self.archivos[recurso.nombre])
        if len(contenido) > limite:
            raise Excedido("más grande que el límite")
        for inicio in range(0, len(contenido), 1000):
            escribir(contenido[inicio:inicio + 1000])
        return len(contenido)


def publicar(canal, privada, objeto=None, instalador=INSTALADOR, crudo=None):
    objeto = objeto or objeto_version()
    datos, firma = firmado(privada, objeto, crudo)
    canal.archivos["version.json"] = datos
    canal.archivos["version.json.firma"] = firma
    canal.archivos[objeto["instalador"]["nombre"]] = instalador
    return datos, firma


def cambio(privada_recuperacion, nueva_publica, contador=1, crudo=None):
    datos = crudo if crudo is not None else aviso.serializar({"producto": "ariasmos", "contador": contador, "llave_uso": nueva_publica})
    return datos, privada_recuperacion.sign(datos)


def escribir_llaves(ruta, uso, recuperacion):
    ruta.write_text(json.dumps({"uso": uso, "recuperacion": recuperacion}), encoding="utf-8")
    return ruta
