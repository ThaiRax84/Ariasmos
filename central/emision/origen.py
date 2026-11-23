from ipaddress import IPv6Address, ip_address, ip_network

from django.conf import settings

LARGO_MAXIMO = 64
PREFIJO_IPV6 = 64


def _normalizada(texto):
    try:
        direccion = ip_address(texto.strip())
    except ValueError:
        return None
    if isinstance(direccion, IPv6Address):
        if direccion.ipv4_mapped is not None:
            return str(direccion.ipv4_mapped)
        return str(ip_network(f"{direccion}/{PREFIJO_IPV6}", strict=False))
    return str(direccion)


def _salto_externo(request):
    for salto in reversed(request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")):
        if salto.strip() not in settings.PROXIES_CONFIABLES:
            return salto
    return None


def de(request):
    remoto = request.META.get("REMOTE_ADDR", "")
    candidato = _salto_externo(request) if remoto in settings.PROXIES_CONFIABLES else None
    return (candidato is not None and _normalizada(candidato)) or _normalizada(remoto) or remoto[:LARGO_MAXIMO]
