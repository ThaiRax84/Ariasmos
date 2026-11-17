import re

from .version import actual

AGENTE = re.compile(r"\bAriasmos/(\d{1,5})\.(\d{1,5})\.(\d{1,5}) (principal|adicional)\b")


def _numeros(texto):
    try:
        return tuple(int(parte) for parte in texto.split("."))
    except ValueError:
        return None


def programa(request):
    encontrado = AGENTE.search(request.META.get("HTTP_USER_AGENT", "")[:1024])
    if encontrado is None:
        return {"programa": None}
    version = tuple(int(n) for n in encontrado.groups()[:3])
    servidor = _numeros(actual())
    return {
        "programa": {
            "version": ".".join(str(n) for n in version),
            "modo": encontrado.group(4),
            "viejo": servidor is not None and version < servidor,
        }
    }
