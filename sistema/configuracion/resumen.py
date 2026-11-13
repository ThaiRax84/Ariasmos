from cuentas.permisos import PERMISOS
from solicitudes.models import ACCIONES

DELICADOS = (
    "alta_baja_directa",
    "aprobar_solicitudes",
    "otorgar_delegaciones",
    "aplicar_ajustes",
    "recibir_efectivo",
    "conciliar_banco",
    "aprobar_dispositivos",
    "administrar_usuarios",
    "administrar_roles",
    "administrar_politicas",
    "administrar_configuracion",
    "ver_auditoria",
    "administrar_respaldos",
)
RESERVADOS_A_NIVELES_ALTOS = ("aprobar_solicitudes", "administrar_usuarios", "administrar_roles", "administrar_configuracion")


def _roles_con(roles, permiso):
    nombres = [r["nombre"] for r in roles if permiso in r["permisos"]]
    return ", ".join(nombres) if nombres else "nadie"


def resumir(datos):
    roles = sorted(datos["roles"], key=lambda r: (r["nivel"], r["nombre"]))
    acciones = dict(ACCIONES)
    resumen_roles = [
        {"nombre": r["nombre"], "nivel": r["nivel"], "delicados": [PERMISOS[p] for p in DELICADOS if p in r["permisos"]], "total": len(r["permisos"])}
        for r in roles
    ]
    resumen_politicas = []
    advertencias = []
    for politica in datos["politicas"]:
        nombre = acciones.get(politica["accion"], politica["accion"])
        resumen_politicas.append(
            {
                "accion": nombre,
                "directo": _roles_con(roles, politica["permiso_directo"]),
                "solicita": _roles_con(roles, politica["permiso_solicitar"]),
                "aprueba": _roles_con(roles, politica["permiso_aprobar"]),
            }
        )
        if politica["permiso_directo"] == politica["permiso_solicitar"]:
            advertencias.append(f"«{nombre}»: quien puede solicitarla también puede hacerla directo, sin aprobación de nadie.")
    menor = min(r["nivel"] for r in roles)
    for rol in roles:
        if rol["nivel"] != menor:
            continue
        for permiso in RESERVADOS_A_NIVELES_ALTOS:
            if permiso in rol["permisos"]:
                advertencias.append(f"El rol de menor nivel «{rol['nombre']}» puede {PERMISOS[permiso].lower()}.")
    return {"roles": resumen_roles, "politicas": resumen_politicas, "advertencias": advertencias, "moneda": datos["moneda"], "denominaciones": len(datos["denominaciones"])}
