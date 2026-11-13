import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from auditoria.models import Evento
from configuracion.models import Negocio
from nucleo import sobre
from nucleo.cadena import canonico
from proyecto import instancia

from . import salida
from .models import Destino

MANIFIESTO = "manifiesto.json"


class ErrorEntrega(ValueError):
    pass


def _protegidas():
    rutas = [Path(settings.RAIZ).resolve(), instancia.carpeta()]
    if getattr(settings, "RUTA_INSTANCIA", ""):
        rutas.append(Path(settings.RUTA_INSTANCIA).resolve())
    return rutas


def _dentro(ruta, base):
    try:
        ruta.relative_to(base)
        return True
    except ValueError:
        return False


def validar_ruta(texto, crear=True):
    texto = str(texto or "").strip()
    if not texto or "\x00" in texto:
        raise ErrorEntrega("Escribe la ruta de una carpeta.")
    ruta = Path(texto)
    if not ruta.is_absolute():
        raise ErrorEntrega("La ruta debe ser absoluta (por ejemplo D:\\Respaldos o /srv/cortes).")
    ruta = ruta.resolve()
    for base in _protegidas():
        if _dentro(ruta, base) or _dentro(base, ruta):
            raise ErrorEntrega("La carpeta no puede estar dentro de la carpeta del programa ni de la instancia, ni contenerlas.")
    if ruta.exists() and not ruta.is_dir():
        raise ErrorEntrega("La ruta existe y no es una carpeta.")
    if crear:
        try:
            ruta.mkdir(parents=True, exist_ok=True)
            prueba = ruta / f".prueba-escritura-{secrets.token_hex(6)}"
            prueba.write_bytes(b"ok")
            prueba.unlink()
        except PermissionError:
            raise ErrorEntrega(
                "El servicio no tiene permiso para escribir en esa carpeta. En el equipo donde está instalado, abre «Dar permiso a una carpeta» "
                "desde el menú Inicio (Ariasmos), escribe esta ruta y vuelve a intentarlo."
            )
        except OSError as error:
            raise ErrorEntrega(f"No se puede escribir en la carpeta: {error.strerror or error}")
    return str(ruta)


def escribir_atomico(carpeta, nombre, contenido):
    destino = Path(carpeta) / nombre
    temporal = Path(carpeta) / f".{nombre}.{secrets.token_hex(6)}.tmp"
    try:
        with open(temporal, "wb") as archivo:
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, destino)
    finally:
        if temporal.exists():
            temporal.unlink()
    return destino


def _clave():
    return sobre.derivar(bytes(settings.CLAVE_AUDITORIA), "manifiesto")


def firmar(datos):
    contenido = {k: v for k, v in datos.items() if k != "firma"}
    return hmac.new(_clave(), canonico(contenido).encode("utf-8"), hashlib.sha256).hexdigest()


def firma_valida(datos):
    return isinstance(datos, dict) and hmac.compare_digest(firmar(datos), str(datos.get("firma", "")))


def ancla_actual():
    ultimo = Evento.objects.order_by("-numero").values_list("numero", "sello").first()
    return {"numero": ultimo[0], "sello": ultimo[1]} if ultimo else {"numero": 0, "sello": ""}


def leer_manifiesto(carpeta):
    ruta = Path(carpeta) / MANIFIESTO
    if not ruta.exists():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def actualizar_manifiesto(destino, nuevos):
    with transaction.atomic():
        Destino.objects.filter(pk=destino.pk).update(actualizado=timezone.now())
        anterior = leer_manifiesto(destino.ruta)
        archivos = {}
        if anterior and firma_valida(anterior):
            archivos = {a["nombre"]: a for a in anterior.get("archivos", []) if isinstance(a, dict) and "nombre" in a}
        for entrada in nuevos:
            archivos[entrada["nombre"]] = entrada
        datos = {"version": 1, "actualizado": timezone.now().isoformat(), "archivos": sorted(archivos.values(), key=lambda a: a["nombre"]), "ancla": ancla_actual()}
        datos["firma"] = firmar(datos)
        escribir_atomico(destino.ruta, MANIFIESTO, (json.dumps(datos, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return datos


def archivos_de(corte, nivel):
    datos = salida.vista(corte.cifras, nivel)
    negocio = Negocio.actual()
    base = salida.nombre_base(corte)
    return {
        f"{base}.pdf": salida.a_pdf(datos, negocio.nombre if negocio else ""),
        f"{base}.csv": salida.a_csv(datos),
        f"{base}.json": salida.a_json(datos),
    }


def entregar(entrega):
    destino = entrega.destino
    carpeta = validar_ruta(destino.ruta)
    escritos = []
    momento = timezone.now().isoformat()
    for nombre, contenido in archivos_de(entrega.corte, entrega.nivel).items():
        escribir_atomico(carpeta, nombre, contenido)
        escritos.append(
            {
                "nombre": nombre,
                "sha256": hashlib.sha256(contenido).hexdigest(),
                "bytes": len(contenido),
                "fecha": momento,
                "tipo": entrega.corte.tipo,
                "nivel": entrega.nivel,
                "corte": entrega.corte_id,
                "hash_corte": entrega.corte.hash,
            }
        )
    actualizar_manifiesto(destino, escritos)
    return escritos


def verificar(carpeta):
    problemas = []
    datos = leer_manifiesto(carpeta)
    if datos is None:
        return ["No hay manifiesto en la carpeta."]
    if not firma_valida(datos):
        return ["La firma del manifiesto no es válida: fue alterado o no es de esta instalación."]
    for entrada in datos.get("archivos", []):
        nombre = str(entrada.get("nombre", ""))
        if not nombre or "/" in nombre or "\\" in nombre or nombre.startswith("."):
            problemas.append(f"Nombre de archivo no válido en el manifiesto: {nombre!r}")
            continue
        ruta = Path(carpeta) / nombre
        if not ruta.exists():
            problemas.append(f"Falta {nombre}.")
            continue
        if hashlib.sha256(ruta.read_bytes()).hexdigest() != entrada.get("sha256"):
            problemas.append(f"{nombre} no coincide con su huella: fue modificado.")
    return problemas
