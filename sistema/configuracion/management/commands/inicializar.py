import hashlib
import secrets
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from proyecto import equipo, instancia


def agregar_hosts(datos, nombres):
    hosts = list(datos.get("hosts", []))
    origenes = list(datos.get("origenes_confiables", []))
    for nombre in equipo.nombres_validos(nombres):
        if nombre not in hosts:
            hosts.append(nombre)
        origen = f"https://{nombre}"
        if origen not in origenes:
            origenes.append(origen)
    if datos.get("https", True) and "https://localhost" not in origenes:
        origenes.append("https://localhost")
    datos["hosts"] = hosts
    datos["origenes_confiables"] = origenes
    return datos


class Command(BaseCommand):
    help = "Crea la carpeta de la instancia con claves aleatorias y un token para el asistente, o completa una existente"

    def add_arguments(self, parser):
        parser.add_argument("--sin-https", action="store_true", help="Cookies sin marca Secure (solo para pruebas locales sin TLS)")
        parser.add_argument("--nuevo-token", action="store_true", help="Genera otro token para el asistente si se perdió")
        parser.add_argument("--host", action="append", default=[], help="Nombre del equipo para hosts y orígenes de confianza (repetible; se sanea)")
        parser.add_argument("--certificado-servidor", default="", help="Ruta absoluta del certificado público del servidor que se ofrece a otras computadoras")

    def _certificado(self, datos, ruta):
        if not ruta:
            return datos
        if not Path(ruta).is_absolute():
            raise CommandError("La ruta del certificado del servidor debe ser absoluta.")
        datos["certificado_servidor"] = str(Path(ruta))
        return datos

    def handle(self, *args, **opciones):
        nombres_crudos = opciones["host"]
        if any(n and not equipo.sanear(n) for n in nombres_crudos):
            raise CommandError("Un nombre de equipo no tiene letras ni dígitos válidos.")
        datos = instancia.leer()
        token = secrets.token_urlsafe(18)
        if datos is None:
            datos = instancia.nueva(https=not opciones["sin_https"])
            datos = self._certificado(agregar_hosts(datos, nombres_crudos), opciones["certificado_servidor"])
            datos["token_asistente_hash"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
            ruta = instancia.escribir(datos)
            self.stdout.write(self.style.SUCCESS(f"Instancia creada en {ruta.parent}"))
        elif opciones["nuevo_token"]:
            datos["token_asistente_hash"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
            instancia.reemplazar(datos)
            self.stdout.write(self.style.SUCCESS("Token del asistente renovado."))
        else:
            antes = dict(datos)
            nuevas = instancia.faltantes(datos)
            datos = self._certificado(agregar_hosts({**datos, **nuevas}, nombres_crudos), opciones["certificado_servidor"])
            if datos != antes:
                instancia.reemplazar(datos)
                cambios = sorted(set(nuevas) | {k for k in ("hosts", "origenes_confiables", "certificado_servidor") if datos.get(k) != antes.get(k)})
                self.stdout.write(self.style.SUCCESS(f"Instancia existente completada con: {', '.join(cambios)}"))
            else:
                self.stdout.write(f"La instancia ya existe en {instancia.carpeta()}; no se cambió nada.")
            return
        self.stdout.write(f"Token del asistente: {token}")
        self.stdout.write("Guárdalo: se pide en el primer paso del asistente y no se vuelve a mostrar.")
        self.stdout.write("Siguiente paso: python manage.py migrate")
