from .models import vocabulario


def general(request):
    usuario = getattr(request, "user", None)
    permisos = usuario.permisos_efectivos() if usuario is not None and usuario.is_authenticated else set()
    return {
        "negocio": getattr(request, "negocio", None),
        "voc": vocabulario(),
        "permisos": permisos,
    }
