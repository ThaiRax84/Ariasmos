from ipaddress import ip_address

from django.conf import settings

LARGO_MAXIMO = 64


def _direccion(texto):
    try:
        return str(ip_address(texto.strip()))
    except ValueError:
        return None


def de(request):
    remoto = request.META.get("REMOTE_ADDR", "")[:LARGO_MAXIMO]
    if remoto not in settings.PROXIES_CONFIABLES:
        return remoto
    for salto in reversed(request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")):
        direccion = _direccion(salto)
        if direccion is not None and direccion not in settings.PROXIES_CONFIABLES:
            return direccion
    return remoto
