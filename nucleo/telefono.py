class TelefonoInvalido(ValueError):
    pass


def normalizar(texto, prefijo="52", digitos_nacionales=10):
    prefijo = "".join(c for c in str(prefijo) if c.isascii() and c.isdigit())
    if not prefijo:
        raise TelefonoInvalido("prefijo de pais vacio")
    crudo = str(texto or "").strip()
    permitidos = set("0123456789 +-().")
    if not crudo or any(c not in permitidos for c in crudo):
        raise TelefonoInvalido("el telefono solo admite digitos, espacios, guiones, parentesis y +")
    digitos = "".join(c for c in crudo if c.isdigit())
    if crudo.startswith("+"):
        internacional = True
    elif digitos.startswith("00"):
        digitos = digitos[2:]
        internacional = True
    else:
        internacional = len(digitos) != digitos_nacionales
    if not internacional:
        return prefijo + digitos
    if digitos.startswith(prefijo) and len(digitos) == len(prefijo) + digitos_nacionales:
        return digitos
    raise TelefonoInvalido(f"se esperan {digitos_nacionales} digitos nacionales")


def formatear(normalizado, prefijo="52"):
    prefijo = str(prefijo)
    if normalizado.startswith(prefijo):
        nacional = normalizado[len(prefijo):]
        if len(nacional) == 10:
            return f"+{prefijo} {nacional[:2]} {nacional[2:6]} {nacional[6:]}"
        return f"+{prefijo} {nacional}"
    return f"+{normalizado}"
