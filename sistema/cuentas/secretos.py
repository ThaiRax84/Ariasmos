from django.conf import settings

from nucleo import sobre


CONTEXTO_ASISTENTE = "totp|asistente"


def _clave():
    return sobre.derivar(bytes(settings.CLAVE_SECRETOS), "totp")


def _contexto(usuario):
    return f"totp|{usuario.pk}"


def _sellar(contexto, secreto):
    return sobre.cifrar_texto(_clave(), secreto, contexto) if secreto else ""


def cifrar(usuario, secreto):
    return _sellar(_contexto(usuario), secreto)


def cifrar_del_asistente(secreto):
    return _sellar(CONTEXTO_ASISTENTE, secreto)


def leer_del_asistente(ficha):
    return sobre.descifrar_texto(_clave(), ficha, CONTEXTO_ASISTENTE) if ficha else ""


def guardar(usuario, secreto):
    if usuario.pk is None:
        raise ValueError("el usuario debe existir antes de guardar su secreto")
    usuario.totp_cifrado = cifrar(usuario, secreto)


def leer(usuario):
    valor = usuario.totp_cifrado
    if not valor:
        return ""
    if sobre.esta_cifrado(valor):
        return sobre.descifrar_texto(_clave(), valor, _contexto(usuario))
    type(usuario).objects.filter(pk=usuario.pk, totp_cifrado=valor).update(totp_cifrado=cifrar(usuario, valor))
    return valor


def cifrar_pendientes():
    from .models import Usuario

    cambiados = 0
    for usuario in Usuario.objects.exclude(totp_cifrado="").only("pk", "totp_cifrado"):
        if not sobre.esta_cifrado(usuario.totp_cifrado):
            cambiados += Usuario.objects.filter(pk=usuario.pk, totp_cifrado=usuario.totp_cifrado).update(totp_cifrado=cifrar(usuario, usuario.totp_cifrado))
    return cambiados


def en_claro():
    from .models import Usuario

    return sum(1 for valor in Usuario.objects.exclude(totp_cifrado="").values_list("totp_cifrado", flat=True) if not sobre.esta_cifrado(valor))
