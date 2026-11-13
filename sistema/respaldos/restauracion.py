import json
import os
import shutil
import tempfile
from pathlib import Path

from django.utils import timezone

from nucleo import sobre
from proyecto import instancia

from . import servicios


def restaurar(archivo, texto_clave, reemplazar=False, destino=None):
    clave = sobre.texto_a_clave(texto_clave)
    archivo = Path(archivo)
    if not archivo.is_file():
        raise servicios.ErrorRespaldo("No existe el archivo de respaldo.")
    destino = Path(destino) if destino else instancia.carpeta()
    temporal = tempfile.mkdtemp(prefix="ariasmos-restaurar-")
    try:
        extraidos = servicios.abrir(archivo, clave, temporal)
        revision = servicios.verificar_paquete(extraidos)
        configuracion = revision["configuracion"]
        if configuracion.get("clave_respaldo") != clave.hex():
            raise servicios.ErrorRespaldo("La configuración del respaldo no corresponde a esta clave.")
        existente = destino / instancia.ARCHIVO
        copia = None
        if existente.exists():
            if not reemplazar:
                raise servicios.ErrorRespaldo(f"Ya hay una instalación en {destino}. Usa --reemplazar para sustituirla (se guarda una copia antes).")
            copia = destino.parent / f"{destino.name}-anterior-{timezone.now():%Y%m%d-%H%M%S}"
            shutil.copytree(destino, copia)
        destino.mkdir(parents=True, exist_ok=True)
        base = destino / "cobro.sqlite3"
        for sufijo in ("", "-wal", "-shm"):
            viejo = Path(str(base) + sufijo)
            if viejo.exists():
                viejo.unlink()
        shutil.copyfile(extraidos[servicios.BASE], base)
        os.chmod(base, 0o600)
        configuracion["base_datos"] = str(base)
        temporal_config = destino / f".{instancia.ARCHIVO}.tmp"
        descriptor = os.open(temporal_config, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as salida:
            json.dump(configuracion, salida, indent=2, ensure_ascii=False)
        os.replace(temporal_config, existente)
        if servicios.ANCLA in extraidos:
            shutil.copyfile(extraidos[servicios.ANCLA], destino / instancia.ANCLA)
            os.chmod(destino / instancia.ANCLA, 0o600)
        return {"destino": str(destino), "copia_anterior": str(copia) if copia else "", "conteos": revision["conteos"], "eventos": revision["eventos"]}
    finally:
        shutil.rmtree(temporal, ignore_errors=True)
