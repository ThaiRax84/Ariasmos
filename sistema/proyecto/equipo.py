import re

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


def configuracion_caddy(nombre, certificado, clave, redirigir_http=True, puerto_aplicacion=8000):
    limpio = sanear(nombre)
    sitios = ["localhost"]
    if limpio and limpio not in RESERVADOS:
        sitios.insert(0, limpio)
    servidores = {
        "ariasmos": {
            "listen": [":443"],
            "routes": [
                {
                    "match": [{"host": sitios}],
                    "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": f"127.0.0.1:{int(puerto_aplicacion)}"}]}],
                    "terminal": True,
                }
            ],
            "tls_connection_policies": [{"certificate_selection": {"any_tag": ["ariasmos"]}}],
            "automatic_https": {"disable": True},
        }
    }
    if redirigir_http:
        servidores["redireccion"] = {
            "listen": [":80"],
            "routes": [
                {
                    "match": [{"host": sitios}],
                    "handle": [{"handler": "static_response", "status_code": 308, "headers": {"Location": ["https://{http.request.host}{http.request.uri}"]}}],
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
