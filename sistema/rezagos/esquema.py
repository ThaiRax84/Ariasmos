from .models import LARGO_TEXTO, TOPE_DIAS, ReglaRezago

MAXIMO_REGLAS = 20
CLAVES = ("nombre", "texto", "dias_minimos", "al_rebasar_limite", "acciones")


def _texto(valor, ruta, maximo, falla):
    if not isinstance(valor, str) or not 1 <= len(valor.strip()) <= maximo or any(ord(c) < 32 for c in valor):
        falla(ruta, f"debe ser texto de 1 a {maximo} caracteres")
    return valor.strip()


def validar_reglas(valor, falla):
    if not isinstance(valor, list):
        falla("rezagos", "debe ser una lista")
    if len(valor) > MAXIMO_REGLAS:
        falla("rezagos", f"tiene más de {MAXIMO_REGLAS} elementos")
    limpias = []
    for i, regla in enumerate(valor):
        ruta = f"rezagos[{i}]"
        if not isinstance(regla, dict):
            falla(ruta, "debe ser un objeto")
        sobrantes = set(regla) - set(CLAVES)
        if sobrantes:
            falla(ruta, f"claves no permitidas: {', '.join(sorted(map(str, sobrantes)))}")
        if "nombre" not in regla or "texto" not in regla or "acciones" not in regla:
            falla(ruta, "faltan claves: nombre, texto y acciones")
        limpia = {"nombre": _texto(regla["nombre"], f"{ruta}.nombre", 100, falla), "texto": _texto(regla["texto"], f"{ruta}.texto", LARGO_TEXTO, falla)}
        dias = regla.get("dias_minimos")
        if dias is not None:
            if type(dias) is not int or not 1 <= dias <= TOPE_DIAS:
                falla(f"{ruta}.dias_minimos", f"debe ser un número entero entre 1 y {TOPE_DIAS}")
            limpia["dias_minimos"] = dias
        rebasar = regla.get("al_rebasar_limite", False)
        if type(rebasar) is not bool:
            falla(f"{ruta}.al_rebasar_limite", "debe ser verdadero o falso")
        limpia["al_rebasar_limite"] = rebasar
        if dias is None and not rebasar:
            falla(ruta, "necesita una condición: días de atraso o rebasar el límite")
        acciones = regla["acciones"]
        if not isinstance(acciones, list) or not acciones or any(a not in ReglaRezago.ACCIONES for a in acciones) or len(set(acciones)) != len(acciones):
            falla(f"{ruta}.acciones", f"debe ser una lista sin repetir de: {', '.join(ReglaRezago.ACCIONES)}")
        limpia["acciones"] = list(acciones)
        limpias.append(limpia)
    nombres = [r["nombre"].casefold() for r in limpias]
    if len(set(nombres)) != len(nombres):
        falla("rezagos", "nombre repetido")
    return limpias
