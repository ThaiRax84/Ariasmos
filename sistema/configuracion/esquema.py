import json

from cuentas.permisos import INDISPENSABLES, PERMISOS
from solicitudes.politicas import POR_DEFECTO, definicion

LIMITE_BYTES = 256 * 1024
MAXIMO_LISTA = {"roles": 20, "politicas": 20, "motivos_baja": 100, "relaciones_contacto": 50, "campos_contacto": 20, "conceptos": 100, "medios_pago": 30, "cajas": 20, "denominaciones": 30}
VOCABULARIO = ("titular", "titulares", "matricula", "agrupacion", "agrupaciones", "familia", "familias")
REQUERIDAS = ("alta", "baja", "reactivacion", "correccion_nombre")
ACCIONES = REQUERIDAS + tuple(a for a in POR_DEFECTO if a not in REQUERIDAS)
TIPOS_CAMPO = ("telefono", "correo", "texto")
TIPOS_CONCEPTO = ("unico", "recurrente", "por_evento")
PERIODICIDADES = ("semanal", "quincenal", "mensual", "bimestral", "trimestral", "semestral", "anual")
APLICA_A = ("nuevos", "todos", "manual")
TIPOS_RECARGO = ("fijo", "porcentaje")
RAIZ = {
    "nombre": True,
    "descripcion": False,
    "vocabulario": False,
    "roles": True,
    "rol_inicial": True,
    "politicas": True,
    "motivos_baja": False,
    "relaciones_contacto": False,
    "campos_contacto": False,
    "conceptos": False,
    "medios_pago": False,
    "cajas": False,
    "denominaciones": False,
}


class PlantillaInvalida(ValueError):
    pass


def _falla(ruta, mensaje):
    raise PlantillaInvalida(f"{ruta}: {mensaje}")


def _texto(valor, ruta, maximo, minimo=1):
    if not isinstance(valor, str):
        _falla(ruta, "debe ser texto")
    limpio = valor.strip()
    if len(limpio) < minimo or len(limpio) > maximo:
        _falla(ruta, f"debe tener entre {minimo} y {maximo} caracteres")
    if any(ord(c) < 32 for c in limpio):
        _falla(ruta, "contiene caracteres de control")
    return limpio


def _entero(valor, ruta, minimo, maximo):
    if type(valor) is not int or not minimo <= valor <= maximo:
        _falla(ruta, f"debe ser un número entero entre {minimo} y {maximo}")
    return valor


def _logico(valor, ruta):
    if type(valor) is not bool:
        _falla(ruta, "debe ser verdadero o falso")
    return valor


def _opcion(valor, ruta, opciones):
    if valor not in opciones:
        _falla(ruta, f"valor no permitido ({', '.join(opciones)})")
    return valor


def _objeto(valor, ruta, permitidas, obligatorias=()):
    if not isinstance(valor, dict):
        _falla(ruta, "debe ser un objeto")
    sobrantes = set(valor) - set(permitidas)
    if sobrantes:
        _falla(ruta, f"claves no permitidas: {', '.join(sorted(map(str, sobrantes)))}")
    faltantes = [c for c in obligatorias if c not in valor]
    if faltantes:
        _falla(ruta, f"faltan claves: {', '.join(faltantes)}")
    return valor


def _lista(valor, ruta, clave):
    if not isinstance(valor, list):
        _falla(ruta, "debe ser una lista")
    if len(valor) > MAXIMO_LISTA[clave]:
        _falla(ruta, f"tiene más de {MAXIMO_LISTA[clave]} elementos")
    return valor


def _sin_repetidos(nombres, ruta):
    vistos = set()
    for nombre in nombres:
        clave = nombre.casefold()
        if clave in vistos:
            _falla(ruta, f"nombre repetido: {nombre}")
        vistos.add(clave)


def _textos(datos, clave, maximo):
    lista = _lista(datos.get(clave, []), clave, clave)
    limpios = [_texto(v, f"{clave}[{i}]", maximo) for i, v in enumerate(lista)]
    _sin_repetidos(limpios, clave)
    return limpios


def _rol(valor, ruta):
    _objeto(valor, ruta, ("nombre", "nivel", "minutos_inactividad", "requiere_totp", "permisos"), ("nombre", "permisos"))
    permisos = valor["permisos"]
    if not isinstance(permisos, list) or len(permisos) > len(PERMISOS):
        _falla(f"{ruta}.permisos", "debe ser una lista de permisos")
    for j, permiso in enumerate(permisos):
        if not isinstance(permiso, str) or permiso not in PERMISOS:
            _falla(f"{ruta}.permisos[{j}]", f"permiso inexistente: {permiso!r}"[:120])
    if len(set(permisos)) != len(permisos):
        _falla(f"{ruta}.permisos", "permisos repetidos")
    rol = {
        "nombre": _texto(valor["nombre"], f"{ruta}.nombre", 60),
        "nivel": _entero(valor.get("nivel", 1), f"{ruta}.nivel", 1, 9),
        "minutos_inactividad": _entero(valor.get("minutos_inactividad", 30), f"{ruta}.minutos_inactividad", 1, 720),
        "requiere_totp": _logico(valor.get("requiere_totp", False), f"{ruta}.requiere_totp"),
        "permisos": list(permisos),
    }
    if "aprobar_solicitudes" in permisos and not rol["requiere_totp"]:
        _falla(ruta, "un rol que aprueba solicitudes debe exigir el autenticador")
    return rol


def _politica(valor, ruta):
    claves = ("accion", "permiso_directo", "permiso_solicitar", "permiso_aprobar", "horas_caducidad", "horas_resaltar", "permite_delegacion", "permite_codigo")
    _objeto(valor, ruta, claves, claves[:4])
    politica = {"accion": _opcion(valor["accion"], f"{ruta}.accion", ACCIONES)}
    for clave in claves[1:4]:
        politica[clave] = _opcion(valor[clave], f"{ruta}.{clave}", tuple(PERMISOS))
    politica["horas_caducidad"] = _entero(valor.get("horas_caducidad", 72), f"{ruta}.horas_caducidad", 1, 8760)
    politica["horas_resaltar"] = _entero(valor.get("horas_resaltar", 24), f"{ruta}.horas_resaltar", 0, 8760)
    politica["permite_delegacion"] = _logico(valor.get("permite_delegacion", True), f"{ruta}.permite_delegacion")
    politica["permite_codigo"] = _logico(valor.get("permite_codigo", True), f"{ruta}.permite_codigo")
    return politica


def _campo(valor, ruta):
    _objeto(valor, ruta, ("etiqueta", "tipo", "obligatorio", "principal", "orden"), ("etiqueta", "tipo"))
    return {
        "etiqueta": _texto(valor["etiqueta"], f"{ruta}.etiqueta", 60),
        "tipo": _opcion(valor["tipo"], f"{ruta}.tipo", TIPOS_CAMPO),
        "obligatorio": _logico(valor.get("obligatorio", False), f"{ruta}.obligatorio"),
        "principal": _logico(valor.get("principal", False), f"{ruta}.principal"),
        "orden": _entero(valor.get("orden", 10), f"{ruta}.orden", 0, 1000),
    }


def _recargo(valor, ruta):
    if valor is None:
        return None
    if type(valor) is bool:
        return {"tipo": "fijo", "dias_gracia": 0, "se_repite": False} if valor else None
    _objeto(valor, ruta, ("tipo", "dias_gracia", "se_repite"))
    return {
        "tipo": _opcion(valor.get("tipo", "fijo"), f"{ruta}.tipo", TIPOS_RECARGO),
        "dias_gracia": _entero(valor.get("dias_gracia", 0), f"{ruta}.dias_gracia", 0, 60),
        "se_repite": _logico(valor.get("se_repite", False), f"{ruta}.se_repite"),
    }


def _concepto(valor, ruta):
    _objeto(valor, ruta, ("nombre", "tipo", "periodicidad", "aplica_a", "prioridad", "recargo"), ("nombre", "tipo"))
    concepto = {
        "nombre": _texto(valor["nombre"], f"{ruta}.nombre", 100),
        "tipo": _opcion(valor["tipo"], f"{ruta}.tipo", TIPOS_CONCEPTO),
        "aplica_a": _opcion(valor.get("aplica_a", "manual"), f"{ruta}.aplica_a", APLICA_A),
        "prioridad": _entero(valor.get("prioridad", 100), f"{ruta}.prioridad", 0, 1000),
        "recargo": _recargo(valor.get("recargo", False), f"{ruta}.recargo"),
    }
    periodicidad = valor.get("periodicidad", "")
    if concepto["tipo"] == "recurrente":
        concepto["periodicidad"] = _opcion(periodicidad, f"{ruta}.periodicidad", PERIODICIDADES)
    elif periodicidad not in ("", None):
        _falla(f"{ruta}.periodicidad", "solo los conceptos recurrentes tienen periodicidad")
    else:
        concepto["periodicidad"] = ""
    return concepto


def validar(datos):
    _objeto(datos, "plantilla", tuple(RAIZ), [c for c, obligatoria in RAIZ.items() if obligatoria])
    limpia = {"nombre": _texto(datos["nombre"], "nombre", 60), "descripcion": _texto(datos.get("descripcion", ""), "descripcion", 300, 0)}
    vocabulario = _objeto(datos.get("vocabulario", {}), "vocabulario", VOCABULARIO)
    limpia["vocabulario"] = {clave: _texto(texto, f"vocabulario.{clave}", 60) for clave, texto in vocabulario.items()}
    limpia["roles"] = [_rol(r, f"roles[{i}]") for i, r in enumerate(_lista(datos["roles"], "roles", "roles"))]
    if not limpia["roles"]:
        _falla("roles", "debe haber al menos un rol")
    _sin_repetidos([r["nombre"] for r in limpia["roles"]], "roles")
    limpia["rol_inicial"] = _texto(datos["rol_inicial"], "rol_inicial", 60)
    inicial = next((r for r in limpia["roles"] if r["nombre"] == limpia["rol_inicial"]), None)
    if inicial is None:
        _falla("rol_inicial", "no corresponde a ningún rol de la plantilla")
    if not set(INDISPENSABLES) <= set(inicial["permisos"]) or not inicial["requiere_totp"]:
        _falla("rol_inicial", "debe administrar usuarios y roles y exigir el autenticador")
    limpia["politicas"] = [_politica(p, f"politicas[{i}]") for i, p in enumerate(_lista(datos["politicas"], "politicas", "politicas"))]
    acciones = [p["accion"] for p in limpia["politicas"]]
    if len(set(acciones)) != len(acciones):
        _falla("politicas", "acción repetida")
    faltantes = set(REQUERIDAS) - set(acciones)
    if faltantes:
        _falla("politicas", f"faltan políticas para: {', '.join(sorted(faltantes))}")
    for accion in ACCIONES:
        if accion not in acciones:
            limpia["politicas"].append(_politica(definicion(accion), f"politicas.{accion}"))
    nombres_roles = {p for r in limpia["roles"] for p in r["permisos"]}
    for politica in limpia["politicas"]:
        if politica["permiso_aprobar"] not in nombres_roles:
            _falla(f"politicas.{politica['accion']}", "ningún rol tiene el permiso para aprobar")
    limpia["motivos_baja"] = _textos(datos, "motivos_baja", 100)
    limpia["relaciones_contacto"] = _textos(datos, "relaciones_contacto", 60)
    limpia["medios_pago"] = _textos(datos, "medios_pago", 60)
    limpia["cajas"] = _textos(datos, "cajas", 60)
    denominaciones = _lista(datos.get("denominaciones", []), "denominaciones", "denominaciones")
    limpia["denominaciones"] = [_entero(v, f"denominaciones[{i}]", 1, 100000000) for i, v in enumerate(denominaciones)]
    if len(set(limpia["denominaciones"])) != len(limpia["denominaciones"]):
        _falla("denominaciones", "valor repetido")
    campos = _lista(datos.get("campos_contacto", []), "campos_contacto", "campos_contacto")
    limpia["campos_contacto"] = [_campo(c, f"campos_contacto[{i}]") for i, c in enumerate(campos)]
    _sin_repetidos([c["etiqueta"] for c in limpia["campos_contacto"]], "campos_contacto")
    if sum(1 for c in limpia["campos_contacto"] if c["principal"]) > 1:
        _falla("campos_contacto", "solo un campo puede ser el principal")
    conceptos = _lista(datos.get("conceptos", []), "conceptos", "conceptos")
    limpia["conceptos"] = [_concepto(c, f"conceptos[{i}]") for i, c in enumerate(conceptos)]
    _sin_repetidos([c["nombre"] for c in limpia["conceptos"]], "conceptos")
    return limpia


def desde_bytes(contenido):
    if len(contenido) > LIMITE_BYTES:
        raise PlantillaInvalida("El archivo pasa de 256 KB.")
    try:
        texto = contenido.decode("utf-8")
    except UnicodeDecodeError:
        raise PlantillaInvalida("El archivo no está en UTF-8.")
    try:
        datos = json.loads(texto)
    except (ValueError, RecursionError):
        raise PlantillaInvalida("El archivo no es un JSON válido.")
    return validar(datos)
