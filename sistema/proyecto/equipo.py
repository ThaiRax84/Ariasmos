import ipaddress
import re
import socket

LARGO_MAXIMO = 63
PERMITIDOS = re.compile(r"[^A-Za-z0-9-]")
RESERVADOS = {"localhost"}


def sanear(texto):
    limpio = PERMITIDOS.sub("", str(texto or "")).strip("-").lower()
    limpio = re.sub(r"-{2,}", "-", limpio)[:LARGO_MAXIMO].strip("-")
    return limpio


def nombres_validos(nombres):
    vistos = []
    for nombre in nombres:
        limpio = sanear(nombre)
        if limpio and limpio not in vistos:
            vistos.append(limpio)
    return vistos


def ruta_caddy(ruta):
    texto = str(ruta).replace("\\", "/")
    if not texto or any(ord(c) < 32 for c in texto):
        raise ValueError("ruta no válida para la configuración de Caddy")
    return texto


PUERTO_PREDETERMINADO = 443
PUERTOS_RESERVADOS = {80, 8000}


def puerto_valido(valor):
    try:
        puerto = int(str(valor).strip())
    except (TypeError, ValueError):
        return None
    if str(puerto) != str(valor).strip() or not 1 <= puerto <= 65535 or puerto in PUERTOS_RESERVADOS:
        return None
    return puerto


def direcciones_locales():
    encontradas = []
    try:
        informacion = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return encontradas
    for *_, direccion in informacion:
        try:
            ip = ipaddress.IPv4Address(direccion[0])
        except ValueError:
            continue
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
            continue
        if str(ip) not in encontradas:
            encontradas.append(str(ip))
    return encontradas


def configuracion_caddy(nombre, certificado, clave, redirigir_http=True, puerto_aplicacion=8000, puerto=PUERTO_PREDETERMINADO):
    limpio = sanear(nombre)
    sitios = ["localhost"]
    if limpio and limpio not in RESERVADOS:
        sitios.insert(0, limpio)
    puerto = puerto_valido(puerto)
    if puerto is None:
        raise ValueError("puerto no válido para el servicio TLS")
    servidores = {
        "ariasmos": {
            "listen": [f":{puerto}"],
            "routes": [
                {
                    "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": f"127.0.0.1:{int(puerto_aplicacion)}"}]}],
                    "terminal": True,
                }
            ],
            "tls_connection_policies": [{"certificate_selection": {"any_tag": ["ariasmos"]}, "default_sni": sitios[0]}],
            "automatic_https": {"disable": True},
        }
    }
    destino = "https://{http.request.host}{http.request.uri}" if puerto == PUERTO_PREDETERMINADO else f"https://{{http.request.host}}:{puerto}{{http.request.uri}}"
    if redirigir_http:
        servidores["redireccion"] = {
            "listen": [":80"],
            "routes": [
                {
                    "match": [{"host": sitios}],
                    "handle": [{"handler": "static_response", "status_code": 308, "headers": {"Location": [destino]}}],
                }
            ],
            "automatic_https": {"disable": True},
        }
    return {
        "admin": {"disabled": True, "config": {"persist": False}},
        "apps": {
            "http": {"servers": servidores},
            "tls": {"certificates": {"load_files": [{"certificate": ruta_caddy(certificado), "key": ruta_caddy(clave), "tags": ["ariasmos"]}]}},
        },
    }
