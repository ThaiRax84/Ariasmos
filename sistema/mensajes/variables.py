import re

from configuracion.models import vocabulario

PATRON = re.compile(r"\[([^\[\]]*)\]")
LARGO_MAXIMO_TEXTO = 900
LARGO_MAXIMO_NOMBRE = 80
LARGO_MAXIMO_VALOR = 200
EJEMPLOS = {
    "nombre": "María",
    "alumno": "Luis",
    "concepto": "Colegiatura de noviembre",
    "importe": "$1,200.00",
    "adeudo": "$800.00",
    "fecha": "05/12/2026",
    "dias": "8",
    "folio": "A-123",
    "negocio": "Tu negocio",
}
ETIQUETAS = {
    "nombre": "Nombre",
    "concepto": "Concepto",
    "importe": "Importe",
    "adeudo": "Adeudo",
    "fecha": "Fecha",
    "dias": "Días de atraso",
    "folio": "Folio",
    "negocio": "Negocio",
}


def botones():
    voc = vocabulario()
    return [
        (clave, voc["titular"] if clave == "alumno" else ETIQUETAS[clave])
        for clave in EJEMPLOS
    ]


def para_mostrar(texto):
    etiquetas = {clave: etiqueta.lower() for clave, etiqueta in botones()}
    return PATRON.sub(
        lambda hallada: f"[{etiquetas.get(hallada.group(1), hallada.group(1))}]", texto
    )


def usadas(texto):
    return list(dict.fromkeys(PATRON.findall(texto)))


def validar(texto):
    for nombre in usadas(texto):
        if nombre not in EJEMPLOS:
            raise ValueError(
                f"«[{nombre}]» no es un dato que Ariasmos conozca. Toca un botón de datos para ponerlo bien."
            )
    sin_datos = PATRON.sub("", texto)
    if "[" in sin_datos or "]" in sin_datos:
        raise ValueError(
            "Hay un corchete suelto. Los datos van completos, por ejemplo [nombre]."
        )
    if "{" in texto or "}" in texto:
        raise ValueError("El mensaje no puede llevar llaves.")
    if texto.startswith("[") or texto.endswith("]"):
        raise ValueError(
            "El mensaje no puede empezar ni terminar con un dato. Agrega alguna palabra antes o después."
        )
    if "][" in texto:
        raise ValueError(
            "Dos datos no pueden ir pegados. Pon una palabra o un espacio entre ellos."
        )


def limpiar_valor(valor):
    limpio = " ".join(str(valor).replace("{", "").replace("}", "").split())
    return (limpio or "-")[:LARGO_MAXIMO_VALOR]


def rellenar(texto, valores):
    return PATRON.sub(
        lambda hallada: valores.get(hallada.group(1), hallada.group(0)), texto
    )
