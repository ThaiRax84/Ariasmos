from dataclasses import dataclass

from nucleo.lectores import santander_pyme


@dataclass(frozen=True)
class AdaptadorPdf:
    clave: str
    nombre: str
    bancos: tuple
    lector: object

    def leer(self, lineas):
        return self.lector.leer(lineas)

    def huella(self, clabe, movimiento, ordinal):
        return self.lector.huella(clabe, movimiento, ordinal)

    @property
    def error(self):
        return self.lector.ErrorEstado


REGISTRO = (AdaptadorPdf("santander_pyme", "Santander PyME", ("014",), santander_pyme),)
MAXIMO_LINEAS = max(adaptador.lector.MAXIMO_LINEAS for adaptador in REGISTRO)


def para_banco(banco):
    clave = getattr(banco, "clave", banco) or ""
    return next((adaptador for adaptador in REGISTRO if clave in adaptador.bancos), None)


def para_cuenta(cuenta):
    if cuenta is None or not cuenta.es_clabe:
        return None
    return para_banco(cuenta.banco)


def nombres():
    return ", ".join(adaptador.nombre for adaptador in REGISTRO)


def sin_lector(cuenta):
    return (
        f"Todavía no hay lector de estados de cuenta en PDF para {cuenta.nombre_banco}. "
        f"Hoy se leen en PDF: {nombres()}. Descarga los movimientos de la banca en línea en Excel o CSV e impórtalos: "
        "el programa propone qué es cada columna y recuerda la correspondencia para la próxima vez."
    )


def formato_desconocido():
    return (
        f"El PDF no tiene el formato de ningún lector disponible ({nombres()}). "
        "Descarga los movimientos de la banca en línea en Excel o CSV e impórtalos: sirve para cualquier banco."
    )
