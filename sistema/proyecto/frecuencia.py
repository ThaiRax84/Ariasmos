import time

from django.core.cache import cache


def excedida(request, clave, maximo, segundos):
    usuario = getattr(request, "user", None)
    quien = usuario.pk if usuario is not None and usuario.is_authenticated else request.META.get("REMOTE_ADDR", "")
    ventana = int(time.time() // segundos)
    llave = f"frecuencia:{clave}:{quien}:{ventana}"
    if cache.add(llave, 1, segundos + 1):
        return False
    try:
        cuenta = cache.incr(llave)
    except ValueError:
        cache.set(llave, 1, segundos + 1)
        return False
    return cuenta > maximo
