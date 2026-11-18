import json
from pathlib import Path

from django.conf import settings

from proyecto import certificado as modulo_certificado
from proyecto import equipo

INICIO_PEM = "-----BEGIN CERTIFICATE-----"
FIN_PEM = "-----END CERTIFICATE-----"
TAMANO_MAXIMO = 64 * 1024
NOMBRE_ARCHIVO = "ariasmos-conexion.json"
LOCALES = ("localhost", "127.0.0.1", "[::1]", "::1", "testserver")


def certificado():
    ruta = str(getattr(settings, "CERTIFICADO_SERVIDOR", "") or "")
    if not ruta:
        return None
    archivo = Path(ruta)
    if not archivo.is_absolute() or archivo.suffix.lower() not in (".crt", ".pem", ".cer") or not archivo.is_file():
        return None
    if archivo.stat().st_size > TAMANO_MAXIMO:
        return None
    try:
        texto = archivo.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError):
        return None
    if "PRIVATE KEY" in texto or texto.count(INICIO_PEM) != 1 or FIN_PEM not in texto:
        return None
    inicio = texto.index(INICIO_PEM)
    fin = texto.index(FIN_PEM) + len(FIN_PEM)
    lineas = [l.strip() for l in texto[inicio:fin].splitlines() if l.strip()]
    base64 = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    if any(not set(l) <= base64 for l in lineas[1:-1]):
        return None
    pem = "\n".join(lineas) + "\n"
    try:
        objeto = modulo_certificado.cargar(pem)
    except modulo_certificado.ErrorCertificado:
        return None
    if modulo_certificado.es_autoridad(objeto):
        return None
    return pem


def datos():
    pem = certificado()
    if pem is None:
        return None
    objeto = modulo_certificado.cargar(pem)
    dns, ips = modulo_certificado.nombres_de(objeto)
    return {
        "pem": pem,
        "huella": modulo_certificado.huella_legible(objeto),
        "huella_hex": modulo_certificado.huella(objeto),
        "puerto": puerto(),
        "vence": modulo_certificado.vence(objeto),
        "dias": modulo_certificado.dias_restantes(objeto),
        "nombres": dns + ips,
        "por_vencer": modulo_certificado.dias_restantes(objeto) <= modulo_certificado.DIAS_AVISO,
    }


def puerto():
    return equipo.puerto_valido(getattr(settings, "PUERTO_HTTPS", equipo.PUERTO_PREDETERMINADO)) or equipo.PUERTO_PREDETERMINADO


def direcciones():
    nombres, ips = [], []
    for host in settings.ALLOWED_HOSTS:
        texto = str(host).strip().lower()
        if not texto or texto in LOCALES or texto.startswith("."):
            continue
        if _es_ipv4(texto):
            ips.append(texto)
        elif equipo.sanear(texto) == texto and texto not in nombres:
            nombres.append(texto)
    for ip in equipo.direcciones_locales():
        if ip not in ips:
            ips.append(ip)
    return nombres + ips


def _es_ipv4(texto):
    partes = texto.split(".")
    return len(partes) == 4 and all(p.isdigit() and len(p) <= 3 and (p == "0" or not p.startswith("0")) and int(p) <= 255 for p in partes)


def archivo(direccion):
    informacion = datos()
    if informacion is None or direccion not in direcciones():
        return None
    contenido = {"producto": "ariasmos", "formato": 1, "direccion": direccion, "puerto": informacion["puerto"], "huella": informacion["huella_hex"]}
    return (json.dumps(contenido, ensure_ascii=True) + "\n").encode("ascii")
