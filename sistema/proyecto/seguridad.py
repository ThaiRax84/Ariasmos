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
