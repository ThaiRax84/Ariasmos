import hashlib
from dataclasses import dataclass, field
from datetime import date

from django.conf import settings
from django.utils.module_loading import import_string

from . import lectura
from .models import CuentaBancaria, Importacion, MovimientoBancario


class ErrorLlegada(ValueError):
    pass


@dataclass(frozen=True)
class Aviso:
    folio: str
    fecha: date
    importe: int
    referencia: str = ""
    concepto: str = ""
    hora: str = ""
    cuenta_pagador: str = ""
    nombre_pagador: str = ""
    banco_origen: str = ""
    rastreo: str = ""


@dataclass
class Origen:
    clave: str
    nombre: str
    cuenta: object = None
    extra: dict = field(default_factory=dict)

    def consultar(self):
        return []

    def leer_aviso(self, cuerpo, cabeceras):
        raise ErrorLlegada("Este origen no recibe avisos entrantes.")


def registrados():
    origenes = []
    for ruta in getattr(settings, "ORIGENES_TRANSFERENCIA", ()):
        clase = import_string(ruta)
        origen = clase()
        if not isinstance(origen, Origen):
            raise ErrorLlegada(f"{ruta} no es un origen de transferencias.")
        origenes.append(origen)
    return origenes


def _texto(valor, maximo):
    return str(valor or "").strip()[:maximo]


def _movimiento(cuenta, origen, aviso):
    if not isinstance(aviso, Aviso):
        raise ErrorLlegada("Aviso no válido.")
    if type(aviso.importe) is not int or aviso.importe <= 0:
        raise ErrorLlegada("El importe del aviso no es válido.")
    if not isinstance(aviso.fecha, date) or not _texto(aviso.folio, 80):
        raise ErrorLlegada("El aviso no trae fecha o folio.")
    fecha = aviso.fecha.isoformat()
    huella = "|".join([cuenta.identificador, "aviso", origen.clave, _texto(aviso.folio, 80)])
    return {
        "fecha": fecha,
        "folio": _texto(aviso.folio, 40),
        "descripcion": _texto(aviso.concepto, 300),
        "importe": aviso.importe,
        "saldo": None,
        "sentido": MovimientoBancario.ABONO,
        "clase": MovimientoBancario.ARCHIVO,
        "hora": _texto(aviso.hora, 8),
        "banco_origen": _texto(aviso.banco_origen, 80),
        "cuenta_pagador": _texto(aviso.cuenta_pagador, 18),
        "nombre_pagador": _texto(aviso.nombre_pagador, 150),
        "rastreo": _texto(aviso.rastreo, 40),
        "referencia": _texto(aviso.referencia, 40),
        "concepto": _texto(aviso.concepto, 200),
        "huella": huella[:255],
    }


def recibir(origen, avisos, cuenta=None):
    from . import conciliacion

    cuenta = cuenta or origen.cuenta or CuentaBancaria.principal_activa()
    if cuenta is None:
        raise ErrorLlegada("No hay una cuenta del negocio para recibir transferencias.")
    movimientos = [_movimiento(cuenta, origen, aviso) for aviso in avisos]
    if not movimientos:
        return None
    nombre = lectura.nombre_saneado(f"aviso-{origen.clave}")
    sha256 = hashlib.sha256("\n".join(m["huella"] for m in movimientos).encode()).hexdigest()
    return conciliacion.importar(cuenta, movimientos, Importacion.ARCHIVO, nombre, sha256, None, None, origen=Importacion.AVISO)


def consultar_todos():
    resultados = []
    for origen in registrados():
        avisos = list(origen.consultar())
        if avisos:
            resultados.append(recibir(origen, avisos))
    return resultados


def transferencia_aplicada(pago):
    from vivo import pulso

    pulso.subir("transferencias")
