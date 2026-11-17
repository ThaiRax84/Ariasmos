import datetime
import io
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Evento
from cuentas import conectar
from proyecto import certificado, equipo, instancia
from proyecto.version import actual

from .conftest import cliente

RAIZ = Path(__file__).resolve().parents[1]
INSTALACION = RAIZ / "instalacion"
DOMINIOS = {"www.python.org", "github.com"}
def manage(*argumentos, entorno=None):
    variables = {**os.environ, **(entorno or {})}
    variables.pop("DJANGO_SETTINGS_MODULE", None)
    return subprocess.run([sys.executable, str(RAIZ / "sistema" / "manage.py"), *argumentos], capture_output=True, text=True, env=variables, timeout=120)


def test_version_en_archivo_pie_y_comando(personas):
    texto = (RAIZ / "VERSION").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", texto) and actual() == texto
    assert f"Ariasmos {texto}" in cliente(personas["op"]).get(reverse("inicio")).content.decode()
    resultado = manage("version", entorno={"COBRO_INSTANCIA": str(RAIZ / "no-existe-esta-instancia")})
    assert resultado.returncode == 0 and resultado.stdout.strip() == f"Ariasmos {texto}"


def test_inicializar_con_nombres_de_equipo(tmp_path):
    carpeta = tmp_path / "instancia"
    entorno = {"COBRO_INSTANCIA": str(carpeta)}
    resultado = manage("inicializar", "--host", "Equipo-Caja_01", "--host", "x;calc&", "--certificado-servidor", str(tmp_path / "servidor.crt"), entorno=entorno)
    assert resultado.returncode == 0, resultado.stderr
    assert re.search(r"^Token del asistente: \S+$", resultado.stdout, re.M)
    datos = json.loads((carpeta / "configuracion.json").read_text(encoding="utf-8"))
    assert datos["https"] is True
    assert "equipo-caja01" in datos["hosts"] and "xcalc" in datos["hosts"]
    assert {"https://equipo-caja01", "https://xcalc", "https://localhost"} <= set(datos["origenes_confiables"])
    assert not any(c in "".join(datos["hosts"]) for c in ";&_ ")
    assert datos["certificado_servidor"] == str(tmp_path / "servidor.crt") and len(bytes.fromhex(datos["clave_respaldo"])) == 32 and datos["clave_secretos"]
    antes = dict(datos)
    otra = manage("inicializar", "--host", "Equipo-Caja_01", entorno=entorno)
    assert "no se cambió nada" in otra.stdout and json.loads((carpeta / "configuracion.json").read_text(encoding="utf-8")) == antes
    nueva = manage("inicializar", "--host", "segundo", entorno=entorno)
    despues = json.loads((carpeta / "configuracion.json").read_text(encoding="utf-8"))
    assert "Token" not in nueva.stdout and "segundo" in despues["hosts"] and all(despues[k] == v for k, v in antes.items() if k not in ("hosts", "origenes_confiables"))
    assert manage("inicializar", "--host", ";;;", entorno=entorno).returncode != 0
    assert manage("inicializar", "--certificado-servidor", "relativo.crt", entorno={"COBRO_INSTANCIA": str(tmp_path / "otra")}).returncode != 0
    assert "puerto" not in despues
    puerto = manage("inicializar", "--puerto", "8443", entorno=entorno)
    assert "puerto" in puerto.stdout and json.loads((carpeta / "configuracion.json").read_text(encoding="utf-8"))["puerto"] == 8443
    for malo in ("80", "8000", "0", "70000", "abc", "-1"):
        assert manage("inicializar", "--puerto", malo, entorno=entorno).returncode != 0, malo


def test_instancia_existente_recibe_claves_nuevas(tmp_path):
    carpeta = tmp_path / "vieja"
    carpeta.mkdir()
    vieja = {"clave_django": "x" * 50, "clave_matricula": "00" * 32, "clave_auditoria": "11" * 32, "base_datos": str(carpeta / "cobro.sqlite3"), "https": True, "hosts": ["localhost"], "origenes_confiables": []}
    (carpeta / instancia.ARCHIVO).write_text(json.dumps(vieja), encoding="utf-8")
    resultado = manage("inicializar", entorno={"COBRO_INSTANCIA": str(carpeta)})
    assert resultado.returncode == 0 and "clave_respaldo" in resultado.stdout and "clave_secretos" in resultado.stdout
    datos = json.loads((carpeta / instancia.ARCHIVO).read_text(encoding="utf-8"))
    assert all(datos[k] == v for k, v in vieja.items() if k != "origenes_confiables") and "https://localhost" in datos["origenes_confiables"]


@pytest.mark.parametrize(
    "crudo,esperado",
    [
        ("EQUIPO-01", "equipo-01"),
        ("caja 2", "caja2"),
        ("a;rm -rf /", "arm-rf"),
        ("$(calc)`&|<>\"'", "calc"),
        ("--equipo--", "equipo"),
        ("ñandú", "and"),
        ("x" * 80, "x" * 63),
        ("", ""),
        ("...", ""),
    ],
    ids=["normal", "espacio", "punto-y-coma", "metacaracteres", "guiones", "acentos", "largo", "vacio", "solo-puntos"],
)
def test_saneado_del_nombre_del_equipo(crudo, esperado):
    assert equipo.sanear(crudo) == esperado
    assert re.fullmatch(r"[a-z0-9-]*", equipo.sanear(crudo))


def test_configuracion_de_caddy_sin_autoridad_local():
    configuracion = equipo.configuracion_caddy("EQUIPO;01 {\n respond hola }", "C:\\Datos\\caddy\\servidor.crt", "C:\\Datos\\caddy\\servidor.key")
    texto = json.dumps(configuracion)
    assert configuracion["admin"]["disabled"] is True
    assert "tls internal" not in texto and "internal" not in texto and "pki" not in texto and "authorities" not in texto and "automation" not in texto
    https = configuracion["apps"]["http"]["servers"]["ariasmos"]
    assert https["listen"] == [":443"] and https["automatic_https"] == {"disable": True}
    assert "match" not in https["routes"][0] and https["tls_connection_policies"][0]["default_sni"] == "equipo01respondhola"
    assert https["routes"][0]["handle"][0] == {"handler": "reverse_proxy", "upstreams": [{"dial": "127.0.0.1:8000"}]}
    archivos = configuracion["apps"]["tls"]["certificates"]["load_files"]
    assert archivos == [{"certificate": "C:/Datos/caddy/servidor.crt", "key": "C:/Datos/caddy/servidor.key", "tags": ["ariasmos"]}]
    assert https["tls_connection_policies"] == [{"certificate_selection": {"any_tag": ["ariasmos"]}, "default_sni": "equipo01respondhola"}]
    redireccion = configuracion["apps"]["http"]["servers"]["redireccion"]
    assert redireccion["listen"] == [":80"] and redireccion["routes"][0]["handle"][0]["status_code"] == 308
    sin = equipo.configuracion_caddy("caja", "/c/s.crt", "/c/s.key", redirigir_http=False)
    assert set(sin["apps"]["http"]["servers"]) == {"ariasmos"}
    assert equipo.configuracion_caddy(";;;", "/c/s.crt", "/c/s.key")["apps"]["http"]["servers"]["ariasmos"]["tls_connection_policies"][0]["default_sni"] == "localhost"
    assert equipo.configuracion_caddy("localhost", "/c/s.crt", "/c/s.key")["apps"]["http"]["servers"]["redireccion"]["routes"][0]["match"] == [{"host": ["localhost"]}]
    otro = equipo.configuracion_caddy("caja", "/c/s.crt", "/c/s.key", puerto=8443)["apps"]["http"]["servers"]
    assert otro["ariasmos"]["listen"] == [":8443"] and otro["redireccion"]["routes"][0]["handle"][0]["headers"]["Location"] == ["https://{http.request.host}:8443{http.request.uri}"]
    for malo in (0, 80, 8000, 65536, "443x", "", None, -1):
        with pytest.raises(ValueError):
            equipo.configuracion_caddy("caja", "/c/s.crt", "/c/s.key", puerto=malo)
    with pytest.raises(ValueError):
        equipo.configuracion_caddy("caja", "/c/s.crt\n", "/c/s.key")


def test_comando_generar_config_caddy(tmp_path):
    salida = tmp_path / "caddy" / "caddy.json"
    call_command("generar_config_caddy", "--nombre", "Caja$1", "--cert", str(tmp_path / "s.crt"), "--clave", str(tmp_path / "s.key"), "--salida", str(salida), "--sin-redireccion", "--puerto", "9443")
    datos = json.loads(salida.read_text(encoding="utf-8"))
    servidor = datos["apps"]["http"]["servers"]["ariasmos"]
    assert servidor["tls_connection_policies"][0]["default_sni"] == "caja1" and servidor["listen"] == [":9443"] and "redireccion" not in datos["apps"]["http"]["servers"]
    with pytest.raises(CommandError):
        call_command("generar_config_caddy", "--nombre", "x", "--cert", str(tmp_path / "s.crt"), "--clave", str(tmp_path / "s.key"), "--salida", str(salida), "--puerto", "80")
    with pytest.raises(CommandError):
        call_command("generar_config_caddy", "--nombre", "x", "--cert", str(tmp_path / "s.crt"), "--clave", str(tmp_path / "s.key"), "--salida", "relativo/caddy.json")
    with pytest.raises(CommandError):
        call_command("generar_config_caddy", "--nombre", "x", "--cert", "s.crt", "--clave", str(tmp_path / "s.key"), "--salida", str(salida))


def test_certificado_del_servidor_tiene_exactamente_las_propiedades(tmp_path):
    cert, clave = tmp_path / "caddy" / "servidor.crt", tmp_path / "caddy" / "servidor.key"
    call_command("generar_certificado", "--nombre", "Equipo_Caja;01", "--cert", str(cert), "--clave", str(clave))
    c = x509.load_pem_x509_certificate(cert.read_bytes())
    assert b"PRIVATE KEY" not in cert.read_bytes() and cert.read_bytes().count(b"BEGIN CERTIFICATE") == 1
    privada = serialization.load_pem_private_key(clave.read_bytes(), password=None)
    assert isinstance(privada, ec.EllipticCurvePrivateKey) and privada.curve.name == "secp256r1"
    assert c.public_key().public_numbers() == privada.public_key().public_numbers()
    assert c.subject.rfc4514_string() == c.issuer.rfc4514_string() == "CN=Ariasmos equipocaja01"
    assert (c.not_valid_after_utc - c.not_valid_before_utc) == datetime.timedelta(days=3650, minutes=5)
    assert abs((c.not_valid_before_utc - datetime.datetime.now(datetime.timezone.utc)).total_seconds() + 300) < 120
    assert c.serial_number > 2**64 and c.version == x509.Version.v3
    extensiones = {e.oid: e for e in c.extensions}
    san = extensiones[ExtensionOID.SUBJECT_ALTERNATIVE_NAME].value
    assert san.get_values_for_type(x509.DNSName) == ["equipocaja01", "localhost"] and [str(i) for i in san.get_values_for_type(x509.IPAddress)] == ["127.0.0.1"]
    restricciones = extensiones[ExtensionOID.BASIC_CONSTRAINTS]
    assert restricciones.critical and restricciones.value.ca is False and restricciones.value.path_length is None
    uso = extensiones[ExtensionOID.KEY_USAGE].value
    assert uso.digital_signature and not (uso.key_cert_sign or uso.crl_sign or uso.key_encipherment or uso.content_commitment or uso.data_encipherment or uso.key_agreement)
    assert list(extensiones[ExtensionOID.EXTENDED_KEY_USAGE].value) == [ExtendedKeyUsageOID.SERVER_AUTH]
    assert ExtensionOID.NAME_CONSTRAINTS not in extensiones and ExtensionOID.AUTHORITY_INFORMATION_ACCESS not in extensiones
    otro = certificado.construir("Equipo_Caja;01")[0]
    assert otro.serial_number != c.serial_number
    if os.name == "posix":
        assert clave.stat().st_mode & 0o777 == 0o600
    assert not list((tmp_path / "caddy").glob(".*tmp"))
    with pytest.raises(CommandError):
        call_command("generar_certificado", "--nombre", ";;;", "--cert", str(cert), "--clave", str(clave))
    with pytest.raises(CommandError):
        call_command("generar_certificado", "--nombre", "caja", "--cert", "relativo.crt", "--clave", str(clave))
    solo_local = certificado.construir("localhost")[0]
    assert solo_local.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName) == ["localhost"]


def test_el_certificado_solo_se_regenera_cuando_hace_falta(tmp_path):
    cert, clave = tmp_path / "servidor.crt", tmp_path / "servidor.key"
    argumentos = ["generar_certificado", "--nombre", "caja", "--cert", str(cert), "--clave", str(clave), "--si-hace-falta"]
    salida = io.StringIO()
    call_command(*argumentos, stdout=salida)
    assert salida.getvalue().startswith("CERTIFICADO: nuevo ") and "(no existe)" in salida.getvalue()
    original = cert.read_bytes()
    salida = io.StringIO()
    call_command(*argumentos, stdout=salida)
    assert salida.getvalue().startswith("CERTIFICADO: conservado ") and cert.read_bytes() == original
    huella = certificado.huella(x509.load_pem_x509_certificate(original))
    assert huella in salida.getvalue() and re.fullmatch(r"[0-9A-F]{64}", huella)
    assert certificado.motivo_para_regenerar(cert, "CAJA") == ""
    assert certificado.motivo_para_regenerar(cert, "otra") == "no incluye otra"
    ahora = datetime.datetime.now(datetime.timezone.utc)
    assert certificado.motivo_para_regenerar(cert, "caja", ahora + datetime.timedelta(days=3650 - 61)) == ""
    assert "vence" in certificado.motivo_para_regenerar(cert, "caja", ahora + datetime.timedelta(days=3650 - 59))
    salida = io.StringIO()
    call_command("generar_certificado", "--nombre", "otra", "--cert", str(cert), "--clave", str(clave), "--si-hace-falta", stdout=salida)
    assert "nuevo" in salida.getvalue() and "no incluye otra" in salida.getvalue() and cert.read_bytes() != original
    clave.unlink()
    salida = io.StringIO()
    call_command("generar_certificado", "--nombre", "otra", "--cert", str(cert), "--clave", str(clave), "--si-hace-falta", stdout=salida)
    assert "nuevo" in salida.getvalue() and clave.is_file()
    cert.write_bytes(pem_de(autoridad()))
    assert certificado.motivo_para_regenerar(cert, "otra") == "es de autoridad"
    cert.write_text("basura", encoding="ascii")
    assert certificado.motivo_para_regenerar(cert, "otra") == "no se puede leer"


def pem_de(objeto):
    return objeto.public_bytes(serialization.Encoding.PEM)


def autoridad():
    clave = ec.generate_private_key(ec.SECP256R1())
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Autoridad cualquiera")])
    ahora = datetime.datetime.now(datetime.timezone.utc)
    return (
        x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre).public_key(clave.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(ahora).not_valid_after(ahora + datetime.timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(clave, hashes.SHA256())
    )


def test_servir_se_niega_a_escuchar_en_la_red_con_https(settings):
    settings.HTTPS_ACTIVO = True
    for host in ("0.0.0.0", "192.168.1.10", "::"):
        with pytest.raises(CommandError, match="127.0.0.1"):
            call_command("servir", "--host", host)


def test_conectar_otra_computadora_entrega_el_archivo_de_conexion(personas, tmp_path, settings, monkeypatch):
    monkeypatch.setattr(equipo, "direcciones_locales", lambda: ["192.168.10.5"])
    settings.ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1", "Caja-01", "caja-01"]
    url, archivo = reverse("conectar"), reverse("conectar_archivo")
    assert cliente(personas["op"]).get(url).status_code == 403
    assert cliente(personas["op"]).post(archivo, {"direccion": "caja-01"}).status_code == 403
    c = cliente(personas["sup"])
    settings.CERTIFICADO_SERVIDOR = ""
    assert "todavía no tiene el certificado" in c.get(url).content.decode()
    assert c.post(archivo, {"direccion": "caja-01"}).status_code == 302 and not Evento.objects.filter(accion="archivo_conexion_generado").exists()
    carpeta = tmp_path / "caddy"
    publico = tmp_path / "certificado" / "ariasmos-servidor.crt"
    objeto = certificado.generar("Caja-01", carpeta / "servidor.crt", carpeta / "servidor.key")
    publico.parent.mkdir()
    publico.write_bytes((carpeta / "servidor.crt").read_bytes())
    PEM = publico.read_text(encoding="ascii")
    settings.CERTIFICADO_SERVIDOR = str(publico)
    settings.PUERTO_HTTPS = 8443
    pagina = c.get(url).content.decode()
    assert certificado.huella_legible(objeto) in pagina and "8443" in pagina and "Computadora adicional" in pagina
    assert "caja-01" in pagina and "192.168.10.5" in pagina and "127.0.0.1" not in pagina and "testserver" not in pagina
    assert "navegador" not in pagina.lower() and "certutil" not in pagina and "instalar-certificado" not in pagina
    assert c.get(archivo).status_code == 405
    respuesta = c.post(archivo, {"direccion": "Caja-01"})
    assert respuesta.status_code == 200 and respuesta["Content-Type"] == "application/json" and "ariasmos-conexion.json" in respuesta["Content-Disposition"]
    assert respuesta["X-Content-Type-Options"] == "nosniff"
    datos = json.loads(respuesta.content)
    assert datos == {"producto": "ariasmos", "formato": 1, "direccion": "caja-01", "puerto": 8443, "huella": certificado.huella(objeto)}
    assert re.fullmatch(r"[0-9A-F]{64}", datos["huella"]) and len(respuesta.content) < 2048 and respuesta.content.isascii()
    evento = Evento.objects.get(accion="archivo_conexion_generado")
    assert evento.datos["direccion"] == "caja-01" and evento.datos["puerto"] == 8443
    assert json.loads(c.post(archivo, {"direccion": "192.168.10.5"}).content)["direccion"] == "192.168.10.5"
    secreto = (carpeta / "servidor.key").read_text(encoding="ascii")
    for malo in ("otro-servidor", "localhost", "127.0.0.1", "caja-01;x", "", "evil.example"):
        assert c.post(archivo, {"direccion": malo}).status_code == 302, malo
    assert Evento.objects.filter(accion="archivo_conexion_generado").count() == 2
    assert secreto.splitlines()[1] not in respuesta.content.decode() and "PRIVATE" not in respuesta.content.decode()
    for nombre, falso in {"clave": secreto, "dos": PEM + PEM, "autoridad": pem_de(autoridad()).decode("ascii"), "texto": "no"}.items():
        publico.write_text(falso, encoding="ascii")
        assert conectar.datos() is None and conectar.archivo("caja-01") is None, nombre
        assert c.post(archivo, {"direccion": "caja-01"}).status_code == 302, nombre
    for viejo in ("/cuentas/conectar/ariasmos-servidor.crt", "/cuentas/conectar/instalar-certificado.cmd"):
        assert c.get(viejo).status_code == 404


def test_aviso_en_inicio_cuando_el_certificado_esta_por_vencer(personas, tmp_path, settings):
    publico = tmp_path / "ariasmos-servidor.crt"
    settings.CERTIFICADO_SERVIDOR = str(publico)
    ahora = datetime.datetime.now(datetime.timezone.utc)
    viejo = certificado.construir("caja", ahora - datetime.timedelta(days=3650 - 30))[0]
    publico.write_bytes(pem_de(viejo))
    pagina = cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    assert "El certificado del servidor vence pronto" in pagina and timezone.localtime(certificado.vence(viejo)).strftime("%d/%m/%Y") in pagina
    assert "El certificado del servidor vence pronto" not in cliente(personas["op"]).get(reverse("inicio")).content.decode()
    assert "vence pronto" in cliente(personas["sup"]).get(reverse("conectar")).content.decode()
    limite = certificado.construir("caja", ahora - datetime.timedelta(days=3650 - 60, hours=-1))[0]
    publico.write_bytes(pem_de(limite))
    assert "El certificado del servidor vence pronto" in cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    publico.write_bytes(pem_de(certificado.construir("caja", ahora - datetime.timedelta(days=3650 - 62))[0]))
    assert "El certificado del servidor vence pronto" not in cliente(personas["sup"]).get(reverse("inicio")).content.decode()
    settings.CERTIFICADO_SERVIDOR = ""
    assert "El certificado del servidor vence pronto" not in cliente(personas["sup"]).get(reverse("inicio")).content.decode()


def test_nada_menciona_el_certificado_raiz_anterior():
    viejos = ("ariasmos-raiz.crt", "generar_caddyfile", "certificado_raiz", "certificado-raiz", "CERTIFICADO_RAIZ", "tls internal", "RaizCaddy", "Caddy Local Authority - ")
    excluidos = {RAIZ / "pruebas" / "test_instalacion.py"}
    carpetas = [RAIZ / "sistema", RAIZ / "instalacion", RAIZ / "docs", RAIZ / "pruebas", RAIZ / ".github"]
    archivos = [RAIZ / "README.md"] + [p for carpeta in carpetas for p in carpeta.rglob("*") if p.is_file() and p.suffix in (".py", ".html", ".ps1", ".iss", ".cmd", ".xml", ".json", ".md", ".yml", ".txt", ".js", ".css")]
    for archivo in archivos:
        if archivo in excluidos or "ARQUITECTURA" in archivo.name:
            continue
        texto = archivo.read_text(encoding="utf-8-sig", errors="replace")
        for viejo in viejos:
            assert viejo not in texto, (archivo, viejo)
    assert not (RAIZ / "sistema" / "configuracion" / "management" / "commands" / "generar_caddyfile.py").exists()


def test_destino_sin_permiso_menciona_la_utilidad(personas, tmp_path, monkeypatch):
    from cortes import entrega

    def sin_permiso(*args, **kwargs):
        raise PermissionError(13, "Acceso denegado")

    monkeypatch.setattr(Path, "write_bytes", sin_permiso)
    with pytest.raises(entrega.ErrorEntrega, match="Dar permiso a una carpeta"):
        entrega.validar_ruta(str(tmp_path / "carpeta"))


def test_dependencias_json():
    datos = json.loads((INSTALACION / "dependencias.json").read_text(encoding="utf-8"))
    assert set(datos) == {"python", "winsw", "caddy", "webview2"}
    webview2 = datos.pop("webview2")
    assert webview2["url"].startswith("https://go.microsoft.com/fwlink/") and webview2["firmante"] == "Microsoft Corporation" and webview2["archivo"] == "MicrosoftEdgeWebview2Setup.exe"
    for nombre, dependencia in datos.items():
        assert {"version", "url", "sha256"} <= set(dependencia), nombre
        partes = urlparse(dependencia["url"])
        assert partes.scheme == "https" and partes.hostname in DOMINIOS, nombre
        assert dependencia["sha256"] == "" or re.fullmatch(r"[0-9a-f]{64}", dependencia["sha256"]), nombre
        assert dependencia["version"] in dependencia["url"], nombre
    assert datos["python"]["version"].startswith("3.12.") and datos["python"]["url"].endswith("-embed-amd64.zip")
    assert datos["winsw"]["version"].startswith("2.") and "winsw/winsw/releases/download/" in datos["winsw"]["url"]
    assert datos["caddy"]["version"].startswith("2.") and datos["caddy"]["url"].endswith("_windows_amd64.zip") and "caddyserver/caddy/releases/download/" in datos["caddy"]["url"]
    vacios = [n for n, d in datos.items() if not d["sha256"]]
    assert all(re.fullmatch(r"[0-9a-f]{32}", datos[n].get("md5_oficial", "")) for n in vacios)
    construir = (INSTALACION / "construir.ps1").read_text(encoding="utf-8-sig")
    assert "no trae el SHA-256" in construir and "no coincide" in construir
    assert "Get-AuthenticodeSignature" in construir and "$firma.Status -ne 'Valid'" in construir and "CN=Microsoft Corporation" in construir


def test_requisitos_de_windows_coinciden_con_requirements():
    fijados = {}
    for linea in (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if linea.strip() and not linea.startswith("#"):
            nombre, version = linea.split("==")
            fijados[nombre.lower().replace("_", "-")] = version
    windows = {}
    texto = (INSTALACION / "requisitos-windows.txt").read_text(encoding="utf-8")
    for nombre, version, huella in re.findall(r"^([A-Za-z0-9.-]+)==(\S+) \\\n    --hash=sha256:([0-9a-f]{64})$", texto, re.M):
        windows[nombre.lower()] = version
    assert windows == fijados


def servicios():
    return sorted((INSTALACION / "servicios").glob("*.xml"))


def test_xml_de_servicios_winsw():
    archivos = servicios()
    assert [a.stem for a in archivos] == ["AriasmosTLS", "AriasmosTrabajador", "AriasmosWeb"]
    for archivo in archivos:
        raiz = ET.parse(archivo).getroot()
        assert raiz.tag == "service" and raiz.findtext("id") == archivo.stem
        cuenta = raiz.find("serviceaccount")
        assert cuenta is not None and cuenta.findtext("domain") == "NT AUTHORITY" and cuenta.findtext("user") == "LocalService" and cuenta.find("password") is None
        assert raiz.findtext("startmode") == "Automatic" and raiz.find("delayedAutoStart") is not None
        assert [f.get("action") for f in raiz.findall("onfailure")] == ["restart"] * 3
        assert raiz.find("log").get("mode") == "roll-by-size" and "Ariasmos\\registros" in raiz.findtext("logpath")
        texto = archivo.read_text(encoding="utf-8")
        assert not re.search(r"(?i)clave|password|secret|token|LocalSystem|[0-9a-f]{32}", texto.replace("<serviceaccount>", "").replace("</serviceaccount>", ""))
        assert not re.search(r"[A-Za-z]:\\", texto)
    web = ET.parse(INSTALACION / "servicios" / "AriasmosWeb.xml").getroot()
    assert "servir --host 127.0.0.1 --puerto 8000" in web.findtext("arguments")
    assert {e.get("name"): e.get("value") for e in web.findall("env")}["COBRO_INSTANCIA"] == "%ProgramData%\\Ariasmos\\instancia"
    tls = ET.parse(INSTALACION / "servicios" / "AriasmosTLS.xml").getroot()
    assert "caddy.exe" in tls.findtext("executable") and tls.findtext("arguments") == 'run --config "%ProgramData%\\Ariasmos\\caddy\\caddy.json"' and "adapter" not in tls.findtext("arguments")
    assert {e.get("name") for e in tls.findall("env")} == {"XDG_DATA_HOME", "XDG_CONFIG_HOME"}


def scripts():
    return [p for p in INSTALACION.rglob("*") if p.suffix in (".ps1", ".iss", ".cmd", ".xml", ".json", ".txt", "._pth") or p.name.endswith("._pth")] + [RAIZ / ".github" / "workflows" / "instalador.yml"]


def test_scripts_sin_rutas_de_un_equipo_ni_secretos_ni_ejecucion_de_texto():
    prohibidos = [
        r"(?i)\b[A-Z]:\\Users\\",
        r"(?i)C:\\(Program Files|ProgramData|Windows)",
        r"(?i)/home/|/root/|/tmp/",
        r"(?i)\b(Invoke-Expression|iex)\b",
        r"(?i)DownloadString|Invoke-RestMethod.*\|\s*(iex|Invoke-Expression)",
        r"(?i)-EncodedCommand",
        r"(?i)LocalSystem",
        r"(?i)(password|contrasena)\s*[:=]\s*\S",
    ]
    for archivo in scripts():
        texto = archivo.read_text(encoding="utf-8-sig")
        for patron in prohibidos:
            assert not re.search(patron, texto), (archivo.name, patron)
        if archivo.suffix in (".ps1", ".iss", ".cmd", ".yml"):
            for linea in texto.splitlines():
                limpia = linea.strip()
                assert not (limpia.startswith("#") and archivo.suffix in (".ps1", ".yml") and not limpia.startswith("#Requires")), (archivo.name, linea)
                assert not limpia.startswith(";") or archivo.suffix != ".iss", (archivo.name, linea)
                assert not limpia.startswith("//"), (archivo.name, linea)
                assert not re.match(r"(?i)^(rem\b|::)", limpia), (archivo.name, linea)
    for archivo in INSTALACION.rglob("*.ps1"):
        texto = archivo.read_text(encoding="utf-8-sig")
        assert archivo.read_bytes().startswith(b"\xef\xbb\xbf"), archivo.name
        assert "COMPUTERNAME" not in texto or archivo.name == "comun.ps1"
    assert "-replace '[^A-Za-z0-9-]', ''" in (INSTALACION / "herramientas" / "comun.ps1").read_text(encoding="utf-8-sig")


def test_scripts_con_fin_de_linea_de_windows():
    for archivo in list(INSTALACION.rglob("*.cmd")) + list(INSTALACION.rglob("*.ps1")) + [INSTALACION / "ariasmos.iss"]:
        crudo = archivo.read_bytes()
        assert b"\r\n" in crudo and b"\n" not in crudo.replace(b"\r\n", b""), archivo.name
    for archivo in INSTALACION.rglob("*.cmd"):
        assert archivo.read_bytes().isascii(), archivo.name


def test_instalador_inno():
    texto = (INSTALACION / "ariasmos.iss").read_text(encoding="utf-8-sig")
    for necesario in ("PrivilegesRequired=admin", "DefaultDirName={commonpf}\\Ariasmos", "ArchitecturesInstallIn64BitMode=x64compatible", "compiler:Languages\\Spanish.isl", "ExecAndCaptureOutput", "TOKEN-ASISTENTE:", "MB_DEFBUTTON2", "IDNO", "Generar token nuevo", "Dar permiso a una carpeta", "restaurar.ps1", "preparar-actualizacion.ps1", "desinstalar.ps1"):
        assert necesario in texto, necesario
    assert "SaveStringToFile(ArchivoClave" in texto and "DeleteFile(ArchivoClave)" in texto
    assert "Token" not in re.sub(r"(?s)\[Code\].*", "", texto)
    secciones = re.sub(r"(?s)\[Code\].*", "", texto)
    assert "https://" not in secciones and "shellexec" not in secciones and "navegador" not in texto.lower()
    assert re.search(r'Name: "\{commondesktop\}\\Ariasmos"; Filename: "\{app\}\\Ariasmos\.exe"', texto)
    assert re.search(r'Name: "\{group\}\\Ariasmos"; Filename: "\{app\}\\Ariasmos\.exe"', texto)
    assert re.search(r'Filename: "\{app\}\\Ariasmos\.exe";[^\n]*Flags: postinstall[^\n]*runasoriginaluser', texto)
    for necesario in ("{param:MODO|}", "{param:PUERTO|}", "{param:CONEXION|}", "CreateInputFilePage", "CreateInputOptionPage", "Check: EsPrincipal", "-Accion Validar", "-Accion Instalar", "WebView2Instalado", "MicrosoftEdgeWebview2Setup.exe", "F3017226-FE2A-4295-8BDF-00C3A9A7E4C5", "Ariasmos.url", "SOFTWARE\\Ariasmos", "no se puede instalar como adicional"):
        assert necesario in texto, necesario
    instalar = (INSTALACION / "herramientas" / "instalar.ps1").read_text(encoding="utf-8-sig")
    assert "TOKEN-ASISTENTE" in instalar and "Escribir-Registro \"    $renglon\"" in instalar
    comun = (INSTALACION / "herramientas" / "comun.ps1").read_text(encoding="utf-8-sig")
    for necesario in ("S-1-5-19", "/inheritance:r", "LocalSubnet", "-LocalPort $Puerto", "'Root', 'LocalMachine'", "PRIVATE KEY", "NT AUTHORITY\\LocalService"):
        assert necesario in comun, necesario
    assert "Start-Transcript" not in comun + instalar
    assert "$almacen.Add(" not in comun and "certutil" not in comun + instalar and "Quitar-De-Raices" in comun
    assert "'--puerto', \"$Puerto\"" in instalar and "-Accion', 'Generar'" in instalar and "Instalar-Firewall -Puerto $Puerto" in instalar
    conexion = (INSTALACION / "herramientas" / "conexion.ps1").read_text(encoding="utf-8-sig")
    for necesario in ("$TamanoMaximo = 2048", "'*S-1-5-32-545:R'", "/inheritance:r", "UTF8Encoding($false, $true)", '"huella"\\s*:\\s*"([0-9A-F]{64})"'):
        assert necesario in conexion, necesario
    permiso = (INSTALACION / "herramientas" / "permiso-carpeta.ps1").read_text(encoding="utf-8-sig")
    for necesario in ("[string]$Carpeta = ''", "ReparsePoint", "'Fixed', 'Removable'", "GetFullPath($Texto)", "'..'", "CON|PRN|AUX|NUL", "unidad completa", "${env:ProgramFiles}"):
        assert necesario in permiso, necesario


def pwsh():
    for candidato in (os.environ.get("PWSH", ""), "pwsh"):
        if not candidato:
            continue
        try:
            if subprocess.run([candidato, "-NoProfile", "-Command", "exit 0"], capture_output=True, timeout=60).returncode == 0:
                return candidato
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


def test_scripts_de_powershell_sin_errores_de_sintaxis(tmp_path):
    ejecutable = pwsh()
    if ejecutable is None:
        pytest.skip("PowerShell no está instalado en este equipo")
    script = tmp_path / "revisar.ps1"
    script.write_text(
        "$f=0; foreach ($a in (Get-ChildItem -Recurse -Filter *.ps1 -Path $args[0])) { $t=$null; $e=$null; "
        "[System.Management.Automation.Language.Parser]::ParseFile($a.FullName, [ref]$t, [ref]$e) | Out-Null; "
        "foreach ($x in $e) { $f++; Write-Output ('{0}:{1}: {2}' -f $a.Name, $x.Extent.StartLineNumber, $x.Message) } }; exit $f",
        encoding="utf-8",
    )
    resultado = subprocess.run([ejecutable, "-NoProfile", "-File", str(script), str(INSTALACION)], capture_output=True, text=True, timeout=120)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_nombre_del_equipo_en_powershell_igual_que_en_python(tmp_path):
    ejecutable = pwsh()
    if ejecutable is None:
        pytest.skip("PowerShell no está instalado en este equipo")
    script = tmp_path / "nombre.ps1"
    script.write_text(f". '{INSTALACION / 'herramientas' / 'comun.ps1'}'\n$env:COMPUTERNAME = $args[0]\nNombre-Equipo\n", encoding="utf-8")
    for crudo in ("EQUIPO-01", "caja 2;calc", "--x--", "ab&cd|ef", "x" * 80):
        resultado = subprocess.run([ejecutable, "-NoProfile", "-File", str(script), crudo], capture_output=True, text=True, timeout=60)
        assert resultado.stdout.strip() == (equipo.sanear(crudo) or "localhost"), crudo
