import colorsys
from collections import Counter
from io import BytesIO

from . import marca

LADO_ANALISIS = 96
ALFA_MINIMO = 128
FRACCION_FONDO = 0.6
TOLERANCIA_FONDO = 24
CUANTO_BORDE = 16
SATURACION_NEUTRA = 0.15
LUZ_MAXIMA = 0.93
LUZ_MINIMA = 0.07
GRUPOS = 8
DIFERENCIA_TONO = 25
LUZ_ACENTO = 0.55
SATURACION_ACENTO = 0.6
PASO_OSCURECER = 0.03
PASOS_MAXIMOS = 40
CONTRASTE_DISTINGUIBLE = 3.0
ACENTO_FABRICA = "#C4662E"


def _hls(rgb):
    return colorsys.rgb_to_hls(*(c / 255 for c in rgb))


def _rgb(tono, luz, saturacion):
    return tuple(round(c * 255) for c in colorsys.hls_to_rgb(tono, luz, saturacion))


def _hex(rgb):
    return marca.hexadecimal(*rgb)


def pixeles(contenido):
    from PIL import Image

    with Image.open(BytesIO(contenido)) as imagen:
        imagen.load()
        imagen = imagen.convert("RGBA")
        imagen.thumbnail((LADO_ANALISIS, LADO_ANALISIS), Image.LANCZOS)
        ancho, alto = imagen.size
        crudo = imagen.tobytes()
        datos = [tuple(crudo[i:i + 4]) for i in range(0, len(crudo), 4)]
    return ancho, alto, datos


def _borde(ancho, alto, datos):
    indices = set()
    for x in range(ancho):
        indices.update((x, (alto - 1) * ancho + x))
    for y in range(alto):
        indices.update((y * ancho, y * ancho + ancho - 1))
    return [datos[i] for i in sorted(indices)]


def _cuantizado(rgb):
    return tuple(min(255, (c // CUANTO_BORDE) * CUANTO_BORDE + CUANTO_BORDE // 2) for c in rgb)


def _cercano(rgb, otro):
    return max(abs(a - b) for a, b in zip(rgb, otro)) <= TOLERANCIA_FONDO


def sin_fondo(ancho, alto, datos):
    if any(p[3] < ALFA_MINIMO for p in datos):
        return [p[:3] for p in datos if p[3] >= ALFA_MINIMO]
    colores = [p[:3] for p in datos]
    borde = [p[:3] for p in _borde(ancho, alto, datos)]
    if not borde:
        return colores
    conteo = Counter(_cuantizado(p) for p in borde)
    dominante, veces = min(conteo.items(), key=lambda par: (-par[1], par[0]))
    if veces / len(borde) <= FRACCION_FONDO:
        return colores
    miembros = [p for p in borde if _cuantizado(p) == dominante]
    fondo = tuple(round(sum(p[i] for p in miembros) / len(miembros)) for i in range(3))
    restantes = [p for p in colores if not _cercano(p, fondo)]
    return restantes or colores


def es_neutro(rgb):
    _, luz, saturacion = _hls(rgb)
    return saturacion < SATURACION_NEUTRA or luz > LUZ_MAXIMA or luz < LUZ_MINIMA


def _rango(caja):
    return max((max(p[i] for p in caja) - min(p[i] for p in caja), -i) for i in range(3))


def corte_mediana(colores, maximo=GRUPOS):
    cajas = [sorted(colores)]
    while len(cajas) < maximo:
        candidatas = [(_rango(c), i) for i, c in enumerate(cajas) if len(set(c)) > 1]
        if not candidatas:
            break
        (_, canal), indice = max(candidatas)
        canal = -canal
        caja = sorted(cajas.pop(indice), key=lambda p: (p[canal], p))
        mitad = len(caja) // 2
        cajas[indice:indice] = [caja[:mitad], caja[mitad:]]
    return cajas


def _promedio(caja):
    return tuple(round(sum(p[i] for p in caja) / len(caja)) for i in range(3))


def grupos(colores):
    total = len(colores)
    resultado = []
    for caja in corte_mediana(colores):
        promedio = _promedio(caja)
        tono, _, saturacion = _hls(promedio)
        resultado.append({"color": promedio, "tono": tono * 360, "saturacion": saturacion, "peso": len(caja) / total * (0.5 + saturacion)})
    return sorted(resultado, key=lambda g: (-g["peso"], g["color"]))


def _diferencia_tono(uno, otro):
    diferencia = abs(uno - otro) % 360
    return min(diferencia, 360 - diferencia)


def _oscurecer(rgb, cumple):
    tono, luz, saturacion = _hls(rgb)
    for _ in range(PASOS_MAXIMOS):
        color = _hex(_rgb(tono, luz, saturacion))
        if cumple(color):
            return color
        luz = max(0.0, luz - PASO_OSCURECER)
    return _hex(_rgb(tono, luz, saturacion))


def ajustar(principal_rgb, acento_rgb):
    def acento_cumple(color):
        return marca.contraste(color, marca.mezclar(color, marca.PROPORCION_FONDO)) >= CONTRASTE_DISTINGUIBLE

    acento = _oscurecer(acento_rgb, acento_cumple) if acento_rgb is not None else ACENTO_FABRICA
    fondo = marca.mezclar(acento, marca.PROPORCION_FONDO)

    def principal_cumple(color):
        return marca.contraste(color, fondo) >= marca.CONTRASTE_TEXTO and marca.contraste(marca.BLANCO, color) >= marca.CONTRASTE_TEXTO

    return _oscurecer(principal_rgb, principal_cumple), acento


def proponer(contenido):
    ancho, alto, datos = pixeles(contenido)
    colores = sin_fondo(ancho, alto, datos)
    neutros = [p for p in colores if es_neutro(p)]
    vivos = [p for p in colores if not es_neutro(p)]
    if not vivos:
        if not neutros:
            principal, acento = ajustar(marca.componentes(marca.TINTA_ARIASMOS), None)
            return {"principal": principal, "acento": acento, "origen": "fabrica"}
        oscuro = min(neutros, key=lambda p: (marca.luminancia(_hex(p)), p))
        principal, acento = ajustar(oscuro, None)
        return {"principal": principal, "acento": acento, "origen": "neutro"}
    lista = grupos(vivos)
    primero = lista[0]
    segundo = next((g for g in lista[1:] if _diferencia_tono(g["tono"], primero["tono"]) >= DIFERENCIA_TONO), None)
    principal_rgb = primero["color"]
    if segundo is not None:
        acento_rgb = segundo["color"]
        if marca.luminancia(_hex(acento_rgb)) < marca.luminancia(_hex(principal_rgb)):
            principal_rgb, acento_rgb = acento_rgb, principal_rgb
    else:
        acento_rgb = _rgb(primero["tono"] / 360, LUZ_ACENTO, max(primero["saturacion"], SATURACION_ACENTO))
    principal, acento = ajustar(principal_rgb, acento_rgb)
    return {"principal": principal, "acento": acento, "origen": "logo"}
