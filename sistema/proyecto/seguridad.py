from django.conf import settings

POLITICA_CONTENIDO = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


CABECERAS_DE_PROXY = ("HTTP_X_FORWARDED_FOR", "HTTP_X_FORWARDED_PROTO", "HTTP_X_FORWARDED_HOST", "HTTP_X_FORWARDED_PORT", "HTTP_FORWARDED")


class CabecerasProxy:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.META.get("REMOTE_ADDR", "") not in getattr(settings, "PROXIES_CONFIABLES", ()):
            for cabecera in CABECERAS_DE_PROXY:
                request.META.pop(cabecera, None)
        return self.get_response(request)


class CabecerasSeguridad:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        respuesta.headers.setdefault("Content-Security-Policy", POLITICA_CONTENIDO)
        respuesta.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        respuesta.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if not request.path.startswith("/static/"):
            respuesta.headers.setdefault("Cache-Control", "no-store")
        return respuesta
