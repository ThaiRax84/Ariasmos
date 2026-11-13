from .base import Canal, ClaveRechazada, ErrorCanal, Excedido, Recurso, RespuestaInvalida, SinConexion, SinPublicacion
from .github import CanalGithub

ADAPTADORES = {"github": CanalGithub}
NOMBRES = {"github": "Publicaciones de un repositorio privado de GitHub"}


def obtener(canal, repositorio, clave):
    adaptador = ADAPTADORES.get(canal)
    if adaptador is None:
        raise ErrorCanal("canal desconocido")
    return adaptador(repositorio, clave)


__all__ = ["ADAPTADORES", "NOMBRES", "Canal", "ClaveRechazada", "ErrorCanal", "Excedido", "Recurso", "RespuestaInvalida", "SinConexion", "SinPublicacion", "obtener"]
