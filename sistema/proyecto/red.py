import ipaddress

from django.conf import settings


def _valida(texto):
    try:
        return str(ipaddress.ip_address(texto.strip()))
    except ValueError:
        return None


def ip_cliente(request):
    if request is None:
        return ""
    directa = request.META.get("REMOTE_ADDR", "")
    if directa in getattr(settings, "PROXIES_CONFIABLES", ()):
        reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if reenviada:
            ultima = _valida(reenviada.split(",")[-1])
            if ultima:
                return ultima
    return directa[:45]
