import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse

from cuentas import conectar
from proyecto import equipo, instancia
from proyecto.version import actual

from .conftest import cliente

RAIZ = Path(__file__).resolve().parents[1]
INSTALACION = RAIZ / "instalacion"
DOMINIOS = {"www.python.org", "github.com"}
PEM = (
    "-----BEGIN CERTIFICATE-----\n"
    "MIIBozCCAUmgAwIBAgIQZmFsc29mYWxzb2ZhbHNvMAoGCCqGSM49BAMCMDAxLjAs\n"
    "BgNVBAMTJUNhZGR5IExvY2FsIEF1dGhvcml0eSAtIDIwMjYgRUNDIFJvb3QwHhcN\n"
    "-----END CERTIFICATE-----\n"
)


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
    resultado = manage("inicializar", "--host", "Equipo-Caja_01", "--host", "x;calc&", "--certificado-raiz", str(tmp_path / "raiz.crt"), entorno=entorno)
    assert resultado.returncode == 0, resultado.stderr
    assert re.search(r"^Token del asistente: \S+$", resultado.stdout, re.M)
    datos = json.loads((carpeta / "configuracion.json").read_text(encoding="utf-8"))
    assert datos["https"] is True
    assert "equipo-caja01" in datos["hosts"] and "xcalc" in datos["hosts"]
    assert {"https://equipo-caja01", "https://xcalc", "https://localhost"} <= set(datos["origenes_confiables"])
    assert not any(c in "".join(datos["hosts"]) for c in ";&_ ")
    assert datos["certificado_raiz"] == str(tmp_path / "raiz.crt") and len(bytes.fromhex(datos["clave_respaldo"])) == 32 and datos["clave_secretos"]
    antes = dict(datos)
    otra = manage("inicializar", "--host", "Equipo-Caja_01", entorno=entorno)
    assert "no se cambió nada" in otra.stdout and json.loads((carpeta / "configuracion.json").read_text(encoding="utf-8")) == antes
    nueva = manage("inicializar", "--host", "segundo", entorno=entorno)
    despues = json.loads((carpeta / "configuracion.json").read_text(encoding="utf-8"))
    assert "Token" not in nueva.stdout and "segundo" in despues["hosts"] and all(despues[k] == v for k, v in antes.items() if k not in ("hosts", "origenes_confiables"))
    assert manage("inicializar", "--host", ";;;", entorno=entorno).returncode != 0
    assert manage("inicializar", "--certificado-raiz", "relativo.crt", entorno={"COBRO_INSTANCIA": str(tmp_path / "otra")}).returncode != 0


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


def test_caddyfile_generado():
    texto = equipo.caddyfile("EQUIPO;01 {\n respond hola }", redirigir_http=True)
    assert "admin off" in texto and "skip_install_trust" in texto and "auto_https disable_redirects" not in texto
    sitios = [l for l in texto.splitlines() if l.endswith("{") and not l.startswith("{")]
    assert sitios == ["https://equipo01respondhola, https://localhost {"]
    assert "reverse_proxy 127.0.0.1:8000" in texto and "tls internal" in texto and "respond" not in texto.split("{", 2)[2].replace("respondhola", "")
    assert texto.count("{") == texto.count("}") == 2
    sin = equipo.caddyfile("caja", redirigir_http=False)
    assert "auto_https disable_redirects" in sin
    solo_local = equipo.caddyfile(";;;")
    assert [l for l in solo_local.splitlines() if l.endswith("{") and not l.startswith("{")] == ["https://localhost {"]
    assert "https://localhost, https://localhost" not in equipo.caddyfile("localhost")


def test_comando_generar_caddyfile(tmp_path, settings):
    salida = tmp_path / "caddy" / "Caddyfile"
    call_command("generar_caddyfile", "--nombre", "Caja$1", "--salida", str(salida), "--sin-redireccion")
    texto = salida.read_text(encoding="utf-8")
    assert "https://caja1, https://localhost {" in texto and "disable_redirects" in texto
    with pytest.raises(CommandError):
        call_command("generar_caddyfile", "--nombre", "x", "--salida", "relativo/Caddyfile")


def test_servir_se_niega_a_escuchar_en_la_red_con_https(settings):
    settings.HTTPS_ACTIVO = True
    for host in ("0.0.0.0", "192.168.1.10", "::"):
        with pytest.raises(CommandError, match="127.0.0.1"):
            call_command("servir", "--host", host)


def test_conectar_otra_computadora_y_certificado(personas, tmp_path, settings):
    url = reverse("conectar")
    assert cliente(personas["op"]).get(url).status_code == 403
    assert cliente(personas["op"]).get(reverse("conectar_certificado")).status_code == 403
    c = cliente(personas["sup"])
    settings.CERTIFICADO_RAIZ = ""
    assert "todavía no tiene un certificado" in c.get(url).content.decode()
    assert c.get(reverse("conectar_certificado")).status_code == 404 and c.get(reverse("conectar_instalador")).status_code == 404
    carpeta = tmp_path / "caddy" / "pki" / "authorities" / "local"
    carpeta.mkdir(parents=True)
    (carpeta / "root.key").write_text("-----BEGIN EC PRIVATE KEY-----\nSECRETO\n-----END EC PRIVATE KEY-----\n", encoding="ascii")
    raiz = tmp_path / "ariasmos-raiz.crt"
    raiz.write_text(PEM, encoding="ascii")
    settings.CERTIFICADO_RAIZ = str(raiz)
    assert "instalar-certificado.cmd" in c.get(url).content.decode()
    respuesta = c.get(reverse("conectar_certificado"))
    assert respuesta.status_code == 200 and respuesta.content.decode() == PEM and "ariasmos-raiz.crt" in respuesta["Content-Disposition"]
    for manipulada in ("?ruta=../caddy/pki/authorities/local/root.key", "?archivo=root.key"):
        assert c.get(reverse("conectar_certificado") + manipulada).content.decode() == PEM
    assert c.get("/cuentas/conectar/root.key").status_code == 404
    assert c.get("/cuentas/conectar/..%2Fcaddy%2Fpki%2Fauthorities%2Flocal%2Froot.key").status_code == 404
    instalador = c.get(reverse("conectar_instalador")).content.decode("ascii")
    assert "certutil -addstore -f Root" in instalador and "\r\n" in instalador and "SECRETO" not in instalador
    assert all(l.split(" echo ", 1)[1] in PEM for l in instalador.splitlines() if " echo -" in l or (" echo " in l and '"%CERT%"' in l))
    assert personas["sup"].usuario not in instalador and "Negocio de prueba" not in instalador
    for falso in ("-----BEGIN EC PRIVATE KEY-----\nX\n-----END EC PRIVATE KEY-----\n", PEM + PEM, "no soy un certificado", PEM.replace("MIIB", "MI&B")):
        raiz.write_text(falso, encoding="ascii")
        assert c.get(reverse("conectar_certificado")).status_code == 404
    settings.CERTIFICADO_RAIZ = str(carpeta / "root.key")
    assert c.get(reverse("conectar_certificado")).status_code == 404
    settings.CERTIFICADO_RAIZ = "relativo.crt"
    assert conectar.certificado() is None


def test_destino_sin_permiso_menciona_la_utilidad(personas, tmp_path, monkeypatch):
    from cortes import entrega

    def sin_permiso(*args, **kwargs):
        raise PermissionError(13, "Acceso denegado")

    monkeypatch.setattr(Path, "write_bytes", sin_permiso)
    with pytest.raises(entrega.ErrorEntrega, match="Dar permiso a una carpeta"):
        entrega.validar_ruta(str(tmp_path / "carpeta"))


def test_dependencias_json():
    datos = json.loads((INSTALACION / "dependencias.json").read_text(encoding="utf-8"))
    assert set(datos) == {"python", "winsw", "caddy"}
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
    assert "caddy.exe" in tls.findtext("executable") and "run --config" in tls.findtext("arguments") and "--adapter caddyfile" in tls.findtext("arguments")
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
    instalar = (INSTALACION / "herramientas" / "instalar.ps1").read_text(encoding="utf-8-sig")
    assert "TOKEN-ASISTENTE" in instalar and "Escribir-Registro \"    $renglon\"" in instalar
    comun = (INSTALACION / "herramientas" / "comun.ps1").read_text(encoding="utf-8-sig")
    for necesario in ("S-1-5-19", "/inheritance:r", "LocalSubnet", "-LocalPort 443", "'Root', 'LocalMachine'", "PRIVATE KEY", "NT AUTHORITY\\LocalService"):
        assert necesario in comun, necesario
    assert "Start-Transcript" not in comun + instalar


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
