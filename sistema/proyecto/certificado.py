import datetime
import ipaddress
import os
import secrets
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from . import equipo

DIAS_VALIDEZ = 3650
DIAS_AVISO = 60


class ErrorCertificado(ValueError):
    pass


def nombres(nombre):
    limpio = equipo.sanear(nombre)
    dns = [limpio] if limpio and limpio not in equipo.RESERVADOS else []
    return dns + ["localhost"]


def construir(nombre, ahora=None):
    ahora = ahora or datetime.datetime.now(datetime.timezone.utc)
    dns = nombres(nombre)
    clave = ec.generate_private_key(ec.SECP256R1())
    titulo = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Ariasmos {dns[0]}")])
    certificado = (
        x509.CertificateBuilder()
        .subject_name(titulo)
        .issuer_name(titulo)
        .public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - datetime.timedelta(minutes=5))
        .not_valid_after(ahora + datetime.timedelta(days=DIAS_VALIDEZ))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in dns] + [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False,
                key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(clave.public_key()), critical=False)
        .sign(clave, hashes.SHA256())
    )
    return certificado, clave


def _escribir(ruta, contenido, privado=False):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f".{ruta.name}.{secrets.token_hex(6)}.tmp")
    descriptor = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600 if privado else 0o644)
    try:
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, ruta)
    finally:
        if temporal.exists():
            temporal.unlink()


def generar(nombre, ruta_certificado, ruta_clave):
    certificado, clave = construir(nombre)
    privada = clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    _escribir(ruta_clave, privada, privado=True)
    _escribir(ruta_certificado, certificado.public_bytes(serialization.Encoding.PEM))
    return certificado


def cargar(pem):
    if isinstance(pem, str):
        pem = pem.encode("ascii")
    if b"PRIVATE KEY" in pem or pem.count(b"-----BEGIN CERTIFICATE-----") != 1:
        raise ErrorCertificado("No es un único certificado público.")
    try:
        return x509.load_pem_x509_certificate(pem)
    except ValueError:
        raise ErrorCertificado("El certificado no se puede leer.")


def es_autoridad(certificado):
    try:
        return certificado.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        return True


def nombres_de(certificado):
    try:
        san = certificado.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return [], []
    return san.get_values_for_type(x509.DNSName), [str(i) for i in san.get_values_for_type(x509.IPAddress)]


def huella(certificado):
    return certificado.fingerprint(hashes.SHA256()).hex().upper()


def huella_legible(certificado):
    texto = huella(certificado)
    return ":".join(texto[i:i + 2] for i in range(0, len(texto), 2))


def vence(certificado):
    return certificado.not_valid_after_utc


def dias_restantes(certificado, ahora=None):
    ahora = ahora or datetime.datetime.now(datetime.timezone.utc)
    return (vence(certificado) - ahora).days


def motivo_para_regenerar(ruta_certificado, nombre, ahora=None):
    ruta = Path(ruta_certificado)
    if not ruta.is_file():
        return "no existe"
    try:
        certificado = cargar(ruta.read_bytes())
    except ErrorCertificado:
        return "no se puede leer"
    if es_autoridad(certificado):
        return "es de autoridad"
    dns, _ = nombres_de(certificado)
    faltan = [n for n in nombres(nombre) if n not in dns]
    if faltan:
        return f"no incluye {', '.join(faltan)}"
    if dias_restantes(certificado, ahora) < DIAS_AVISO:
        return f"vence en menos de {DIAS_AVISO} días"
    return ""
