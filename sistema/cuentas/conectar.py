from pathlib import Path

from django.conf import settings

from proyecto import certificado as modulo_certificado

INICIO_PEM = "-----BEGIN CERTIFICATE-----"
FIN_PEM = "-----END CERTIFICATE-----"
TAMANO_MAXIMO = 64 * 1024
NOMBRE = "ariasmos-servidor.crt"


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
        "vence": modulo_certificado.vence(objeto),
        "dias": modulo_certificado.dias_restantes(objeto),
        "nombres": dns + ips,
        "por_vencer": modulo_certificado.dias_restantes(objeto) <= modulo_certificado.DIAS_AVISO,
    }


def instalador(pem):
    renglones = [
        "@echo off",
        "setlocal",
        "net session >nul 2>&1",
        "if errorlevel 1 (",
        "  echo Este archivo debe ejecutarse como administrador: clic derecho, Ejecutar como administrador.",
        "  pause",
        "  exit /b 1",
        ")",
        'set "CERT=%TEMP%\\ariasmos-servidor-%RANDOM%%RANDOM%.crt"',
    ]
    for numero, linea in enumerate(pem.strip().splitlines()):
        renglones.append(f'{">" if numero == 0 else ">>"}"%CERT%" echo {linea}')
    renglones += [
        'certutil -addstore -f Root "%CERT%"',
        "set RESULTADO=%ERRORLEVEL%",
        'del "%CERT%" >nul 2>&1',
        "if not %RESULTADO%==0 (",
        "  echo No se pudo instalar el certificado. Codigo %RESULTADO%.",
        "  pause",
        "  exit /b %RESULTADO%",
        ")",
        "echo Listo: esta computadora ya confia en el sistema. Cierra y vuelve a abrir el navegador.",
        "pause",
        "exit /b 0",
    ]
    return "\r\n".join(renglones) + "\r\n"
