from dataclasses import dataclass


class ErrorCanal(Exception):
    pass


class SinConexion(ErrorCanal):
    pass


class RespuestaInvalida(ErrorCanal):
    pass


class ClaveRechazada(ErrorCanal):
    pass


class SinPublicacion(ErrorCanal):
    pass


class Excedido(ErrorCanal):
    pass


@dataclass(frozen=True)
class Recurso:
    nombre: str
    tamano: int
    ident: str


class Canal:
    def publicacion(self):
        raise NotImplementedError

    def descargar(self, recurso, escribir, limite, plazo):
        raise NotImplementedError

    def leer(self, recurso, limite, plazo=60):
        partes = []
        self.descargar(recurso, partes.append, limite, plazo)
        return b"".join(partes)
