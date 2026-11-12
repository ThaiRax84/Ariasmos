import hashlib
import json

GENESIS = "0" * 64


def canonico(contenido):
    return json.dumps(contenido, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def encadenar(anterior, contenido):
    return hashlib.sha256((anterior + "|" + canonico(contenido)).encode("utf-8")).hexdigest()


def verificar(eslabones):
    anterior = GENESIS
    for posicion, (hash_anterior, contenido, hash_propio) in enumerate(eslabones):
        if hash_anterior != anterior or encadenar(anterior, contenido) != hash_propio:
            return posicion
        anterior = hash_propio
    return None
