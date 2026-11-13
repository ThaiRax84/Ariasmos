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


def caddyfile(nombre, redirigir_http=True, puerto_aplicacion=8000):
    limpio = sanear(nombre)
    sitios = ["https://localhost"]
    if limpio and limpio not in RESERVADOS:
        sitios.insert(0, f"https://{limpio}")
    globales = ["\tadmin off", "\tskip_install_trust", "\tpersist_config off"]
    if not redirigir_http:
        globales.append("\tauto_https disable_redirects")
    lineas = ["{", *globales, "}", "", ", ".join(sitios) + " {", "\ttls internal", f"\treverse_proxy 127.0.0.1:{int(puerto_aplicacion)}", "}", ""]
    return "\n".join(lineas)
