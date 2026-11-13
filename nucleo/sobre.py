import base64
import hashlib
import secrets
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIA = b"ARIASMOS-SOBRE\x01"
TROZO = 1024 * 1024
LARGO_CLAVE = 32
ALFABETO = "ABCDEFGHJKMNPQRSTVWXYZ0123456789"
GRUPO = 4
MARCA_TEXTO = "v1"


class ErrorSobre(ValueError):
    pass


def nueva_clave():
    return secrets.token_bytes(LARGO_CLAVE)


def _validar_clave(clave):
    if not isinstance(clave, (bytes, bytearray)) or len(clave) != LARGO_CLAVE:
        raise ErrorSobre("La clave debe tener 32 bytes.")


def _a_base32(datos):
    numero = int.from_bytes(datos, "big")
    letras = []
    for _ in range((len(datos) * 8 + 4) // 5):
        numero, resto = divmod(numero, 32)
        letras.append(ALFABETO[resto])
    return "".join(reversed(letras))


def _de_base32(texto, largo):
    numero = 0
    for letra in texto:
        numero = numero * 32 + ALFABETO.index(letra)
    if numero >= 1 << (largo * 8):
        raise ErrorSobre("La clave de recuperación no es válida.")
    return numero.to_bytes(largo, "big")


def clave_a_texto(clave):
    _validar_clave(clave)
    cuerpo = bytes(clave) + hashlib.sha256(b"clave-recuperacion|" + bytes(clave)).digest()[:3]
    letras = _a_base32(cuerpo)
    return "-".join(letras[i:i + GRUPO] for i in range(0, len(letras), GRUPO))


def texto_a_clave(texto):
    limpio = "".join(c for c in str(texto).upper() if not c.isspace() and c != "-")
    limpio = limpio.replace("O", "0").replace("U", "V")
    esperado = ((LARGO_CLAVE + 3) * 8 + 4) // 5
    if len(limpio) != esperado or any(c not in ALFABETO for c in limpio):
        raise ErrorSobre("La clave de recuperación no tiene el formato esperado.")
    cuerpo = _de_base32(limpio, LARGO_CLAVE + 3)
    clave, verificador = cuerpo[:LARGO_CLAVE], cuerpo[LARGO_CLAVE:]
    if hashlib.sha256(b"clave-recuperacion|" + clave).digest()[:3] != verificador:
        raise ErrorSobre("La clave de recuperación tiene un error de captura.")
    return clave


def _nonce(prefijo, indice):
    return prefijo + struct.pack(">I", indice)


def _asociado(indice, final):
    return MAGIA + struct.pack(">I", indice) + (b"F" if final else b"M")


def cifrar(origen, destino, clave, trozo=TROZO):
    _validar_clave(clave)
    cifrador = AESGCM(bytes(clave))
    prefijo = secrets.token_bytes(8)
    destino.write(MAGIA + prefijo)
    indice = 0
    actual = origen.read(trozo)
    while True:
        siguiente = origen.read(trozo)
        final = not siguiente
        sellado = cifrador.encrypt(_nonce(prefijo, indice), actual, _asociado(indice, final))
        destino.write(struct.pack(">I", len(sellado)) + sellado)
        indice += 1
        if final:
            return indice
        if indice >= 2 ** 32 - 1:
            raise ErrorSobre("El contenido es demasiado grande.")
        actual = siguiente


def descifrar(origen, destino, clave, trozo_maximo=TROZO + 16):
    _validar_clave(clave)
    cabecera = origen.read(len(MAGIA) + 8)
    if len(cabecera) != len(MAGIA) + 8 or cabecera[: len(MAGIA)] != MAGIA:
        raise ErrorSobre("El archivo no es un respaldo de este sistema.")
    prefijo = cabecera[len(MAGIA):]
    cifrador = AESGCM(bytes(clave))
    indice = 0
    pendiente = origen.read(4)
    if len(pendiente) != 4:
        raise ErrorSobre("El respaldo está incompleto.")
    while True:
        (largo,) = struct.unpack(">I", pendiente)
        if largo < 16 or largo > trozo_maximo:
            raise ErrorSobre("El respaldo está dañado.")
        sellado = origen.read(largo)
        if len(sellado) != largo:
            raise ErrorSobre("El respaldo está incompleto.")
        pendiente = origen.read(4)
        final = len(pendiente) == 0
        if not final and len(pendiente) != 4:
            raise ErrorSobre("El respaldo está incompleto.")
        try:
            claro = cifrador.decrypt(_nonce(prefijo, indice), sellado, _asociado(indice, final))
        except InvalidTag:
            raise ErrorSobre("La clave no corresponde a este respaldo, o el respaldo fue alterado o está incompleto.")
        destino.write(claro)
        indice += 1
        if final:
            return indice


def cifrar_texto(clave, texto, contexto):
    _validar_clave(clave)
    nonce = secrets.token_bytes(12)
    sellado = AESGCM(bytes(clave)).encrypt(nonce, texto.encode("utf-8"), b"texto|" + contexto.encode("utf-8"))
    return MARCA_TEXTO + "." + base64.urlsafe_b64encode(nonce + sellado).decode("ascii")


def descifrar_texto(clave, ficha, contexto):
    _validar_clave(clave)
    if not isinstance(ficha, str) or not ficha.startswith(MARCA_TEXTO + "."):
        raise ErrorSobre("El dato no está cifrado con este sistema.")
    try:
        crudo = base64.urlsafe_b64decode(ficha[len(MARCA_TEXTO) + 1:].encode("ascii"))
        claro = AESGCM(bytes(clave)).decrypt(crudo[:12], crudo[12:], b"texto|" + contexto.encode("utf-8"))
    except (InvalidTag, ValueError):
        raise ErrorSobre("El dato cifrado no se pudo abrir.")
    return claro.decode("utf-8")


def esta_cifrado(valor):
    return isinstance(valor, str) and valor.startswith(MARCA_TEXTO + ".")


def derivar(clave, etiqueta):
    _validar_clave(clave)
    return hashlib.blake2b(etiqueta.encode("utf-8"), key=bytes(clave), digest_size=LARGO_CLAVE).digest()
