import http.client
import json
import re
import ssl
import time
import urllib.request
from urllib.parse import urlsplit

from .base import Canal, ClaveRechazada, Excedido, Recurso, RespuestaInvalida, SinConexion, SinPublicacion

SERVIDOR_API = "api.github.com"
SUFIJO_DESCARGA = ".githubusercontent.com"
PATRON_REPOSITORIO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100}")
PATRON_CLAVE = re.compile(r"(?:github_pat_[A-Za-z0-9_]{22,255}|gh[pousr]_[A-Za-z0-9]{36,255})")
PATRON_SERVIDOR = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+")
LIMITE_LISTADO = 1024 * 1024
MAXIMO_RECURSOS = 50
TIEMPO_CONEXION = 20
BLOQUE = 64 * 1024
REDIRECCIONES = (301, 302, 303, 307, 308)
AGENTE = "Ariasmos"


def repositorio_valido(texto):
    if not isinstance(texto, str) or PATRON_REPOSITORIO.fullmatch(texto) is None:
        return False
    nombre = texto.split("/", 1)[1]
    return nombre not in (".", "..") and not nombre.endswith(".git")


def clave_valida(texto):
    return isinstance(texto, str) and PATRON_CLAVE.fullmatch(texto) is not None


def _abridor():
    abridor = urllib.request.OpenerDirector()
    abridor.add_handler(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    return abridor


def abrir(peticion, tiempo):
    return _abridor().open(peticion, timeout=tiempo)


def servidor_permitido(url, redireccion):
    if not isinstance(url, str) or len(url) > 4096 or any(c.isspace() or c == "\\" for c in url):
        return False
    try:
        partes = urlsplit(url)
        puerto = partes.port
    except ValueError:
        return False
    if partes.scheme != "https" or partes.username is not None or partes.password is not None or puerto not in (None, 443):
        return False
    servidor = (partes.hostname or "").lower()
    if PATRON_SERVIDOR.fullmatch(servidor) is None:
        return False
    if redireccion:
        return servidor.endswith(SUFIJO_DESCARGA) and len(servidor) > len(SUFIJO_DESCARGA)
    return servidor == SERVIDOR_API


class CanalGithub(Canal):
    def __init__(self, repositorio, clave, abrir_url=None):
        if not repositorio_valido(repositorio):
            raise RespuestaInvalida("repositorio no válido")
        if not clave_valida(clave):
            raise ClaveRechazada("clave no válida")
        self._repositorio = repositorio
        self._clave = clave
        self._abrir = abrir_url or abrir

    def __repr__(self):
        return f"CanalGithub({self._repositorio})"

    def _pedir(self, url, con_clave, acepta):
        if not servidor_permitido(url, redireccion=not con_clave):
            raise RespuestaInvalida("servidor no permitido")
        cabeceras = {"User-Agent": AGENTE, "Accept": acepta}
        if con_clave:
            cabeceras["Authorization"] = "Bearer " + self._clave
            cabeceras["X-GitHub-Api-Version"] = "2022-11-28"
        peticion = urllib.request.Request(url, headers=cabeceras, method="GET")
        try:
            respuesta = self._abrir(peticion, TIEMPO_CONEXION)
        except (OSError, http.client.HTTPException, ValueError):
            raise SinConexion("sin conexión") from None
        if respuesta is None:
            raise RespuestaInvalida("sin respuesta")
        return respuesta

    def _leer(self, respuesta, escribir, limite, plazo):
        declarado = respuesta.headers.get("Content-Length")
        if declarado is not None:
            if not declarado.isdigit() or int(declarado) > limite:
                raise Excedido("tamaño declarado mayor que el límite")
        total = 0
        try:
            while True:
                if time.monotonic() > plazo:
                    raise SinConexion("tiempo agotado")
                bloque = respuesta.read(min(BLOQUE, limite + 1 - total))
                if not bloque:
                    break
                total += len(bloque)
                if total > limite:
                    raise Excedido("más grande que el límite")
                escribir(bloque)
        except (OSError, http.client.HTTPException):
            raise SinConexion("conexión interrumpida") from None
        finally:
            respuesta.close()
        return total

    def _estado(self, respuesta):
        estado = getattr(respuesta, "status", None)
        if estado in (401, 403):
            respuesta.close()
            raise ClaveRechazada("el canal rechazó la clave")
        if estado == 404:
            respuesta.close()
            raise SinPublicacion("sin publicaciones")
        return estado

    def publicacion(self):
        respuesta = self._pedir(f"https://{SERVIDOR_API}/repos/{self._repositorio}/releases/latest", True, "application/vnd.github+json")
        if self._estado(respuesta) != 200:
            respuesta.close()
            raise RespuestaInvalida("respuesta inesperada del canal")
        partes = []
        self._leer(respuesta, partes.append, LIMITE_LISTADO, time.monotonic() + 60)
        try:
            datos = json.loads(b"".join(partes).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise RespuestaInvalida("listado no válido") from None
        recursos = datos.get("assets") if isinstance(datos, dict) else None
        if not isinstance(recursos, list) or len(recursos) > MAXIMO_RECURSOS:
            raise RespuestaInvalida("listado no válido")
        resultado = {}
        for recurso in recursos:
            if not isinstance(recurso, dict):
                raise RespuestaInvalida("listado no válido")
            ident, nombre, tamano = recurso.get("id"), recurso.get("name"), recurso.get("size")
            if type(ident) is not int or ident <= 0 or not isinstance(nombre, str) or len(nombre) > 200 or type(tamano) is not int or tamano < 0:
                raise RespuestaInvalida("listado no válido")
            if nombre in resultado:
                raise RespuestaInvalida("recurso repetido")
            resultado[nombre] = Recurso(nombre=nombre, tamano=tamano, ident=str(ident))
        return resultado

    def descargar(self, recurso, escribir, limite, plazo):
        if not recurso.ident.isdigit():
            raise RespuestaInvalida("recurso no válido")
        if recurso.tamano > limite:
            raise Excedido("el recurso es más grande que el límite")
        fin = time.monotonic() + plazo
        respuesta = self._pedir(f"https://{SERVIDOR_API}/repos/{self._repositorio}/releases/assets/{recurso.ident}", True, "application/octet-stream")
        estado = self._estado(respuesta)
        if estado in REDIRECCIONES:
            destino = respuesta.headers.get("Location")
            respuesta.close()
            if not servidor_permitido(destino, redireccion=True):
                raise RespuestaInvalida("redirección a un servidor no permitido")
            respuesta = self._pedir(destino, False, "application/octet-stream")
            estado = getattr(respuesta, "status", None)
            if estado in REDIRECCIONES:
                respuesta.close()
                raise RespuestaInvalida("más de una redirección")
        if estado != 200:
            respuesta.close()
            raise RespuestaInvalida("respuesta inesperada del canal")
        return self._leer(respuesta, escribir, limite, fin)
