from django.urls import reverse

from proyecto.version import actual as version_actual

from .models import inventario_activo, vocabulario

MAXIMO_VISIBLES = 7
PERMISOS_INVENTARIO = ("vender_articulos", "registrar_movimientos_inventario", "subir_conteo_inventario", "devolver_articulos", "revisar_inventario", "administrar_articulos")


def _alguno(permisos, *nombres):
    return any(nombre in permisos for nombre in nombres)


def _prioritarias(permisos, voc, inventario):
    return [
        ("Inicio", "inicio", True, ("=/",), ()),
        ("Cobrar", "cobros:buscar", "registrar_pago_efectivo" in permisos, ("/cobros/cobrar/", "/cobros/recibos/"), ()),
        (voc["titulares"], "titulares:lista", "ver_titulares" in permisos, ("/titulares/", "/cobros/titulares/", "/cobros/cargos/", "/cobros/pagos/"), ("/titulares/familias/",)),
        ("Inventario", "inventario:indice", inventario and _alguno(permisos, *PERMISOS_INVENTARIO), ("/inventario/",), ()),
        ("Mi caja", "caja:inicio", "turno_caja" in permisos, ("/caja/",), ("/caja/custodia/", "/caja/traslados/")),
        ("Banco", "conciliacion:cola", _alguno(permisos, "conciliar_banco", "sugerir_conciliacion"), ("/banco/",), ()),
        ("Efectivo", "caja:custodia", "recibir_efectivo" in permisos, ("/caja/custodia/", "/caja/traslados/"), ()),
        ("Solicitudes", "solicitudes:bandeja", _alguno(permisos, "solicitar_alta_baja", "aprob_solicitudes", "alta_baja_directa"), ("/solicitudes/",), ("/solicitudes/politicas/",)),
        ("Cortes", "cortes:lista", _alguno(permisos, "turno_caja", "ver_cortes"), ("/cortes/",), ()),
    ]


def _demas(permisos, voc):
    return [
        (voc["familias"], "titulares:familias", "ver_titulares" in permisos, ("/titulares/familias/",), ()),
        ("Conceptos", "cobros:conceptos", "administrar_conceptos" in permisos, ("/cobros/conceptos/", "/cobros/recargos/", "/cobros/planes/"), ()),
        ("Delegaciones", "delegaciones", "otorgar_delegaciones" in permisos, ("/cuentas/delegaciones/",), ()),
        ("Equipos", "dispositivos", "aprobar_dispositivos" in permisos, ("/cuentas/dispositivos/", "/cuentas/conectar/"), ()),
        ("Usuarios", "usuarios", "administrar_usuarios" in permisos, ("/cuentas/usuarios/",), ()),
        ("Roles", "roles", "administrar_roles" in permisos, ("/cuentas/roles/",), ()),
        ("Políticas", "solicitudes:politicas", "administrar_politicas" in permisos, ("/solicitudes/politicas/",), ()),
        ("Topes del banco", "conciliacion:topes", "configurar_topes_banco" in permisos and not _alguno(permisos, "conciliar_banco", "sugerir_conciliacion"), ("/banco/topes/",), ()),
        ("Configuración", "configuracion:indice", "administrar_configuracion" in permisos, ("/configuracion/", "/actualizaciones/"), ()),
        ("Respaldos", "respaldos:panel", "administrar_respaldos" in permisos, ("/respaldos/",), ()),
        ("Auditoría", "auditoria:lista", "ver_auditoria" in permisos, ("/auditoria/",), ()),
    ]


def _activa(ruta, prefijos, excluidos):
    if any(ruta.startswith(e) for e in excluidos):
        return False
    for prefijo in prefijos:
        if prefijo.startswith("="):
            if ruta == prefijo[1:]:
                return True
        elif ruta.startswith(prefijo):
            return True
    return False


def menu(permisos, voc, inventario, ruta):
    def armar(entradas):
        return [{"texto": texto, "url": reverse(nombre), "activa": _activa(ruta, prefijos, excluidos)} for texto, nombre, permitido, prefijos, excluidos in entradas if permitido]

    prioritarias = armar(_prioritarias(permisos, voc, inventario))
    visibles = prioritarias[:MAXIMO_VISIBLES]
    mas = prioritarias[MAXIMO_VISIBLES:] + armar(_demas(permisos, voc))
    return {"visibles": visibles, "mas": mas, "mas_activa": any(e["activa"] for e in mas)}


def _turno(usuario, permisos):
    if "turno_caja" not in permisos:
        return None
    from caja.servicios import turno_abierto

    return turno_abierto(usuario)


def general(request):
    from .marca import actual as marca_actual
    from .moneda import actual as moneda_actual

    usuario = getattr(request, "user", None)
    autenticado = usuario is not None and usuario.is_authenticated
    permisos = usuario.permisos_efectivos() if autenticado else set()
    voc = vocabulario()
    inventario = inventario_activo() if permisos else False
    contexto = {
        "negocio": getattr(request, "negocio", None),
        "voc": voc,
        "permisos": permisos,
        "version": version_actual(),
        "inventario_activo": inventario,
        "marca": marca_actual(),
        "moneda": moneda_actual(),
    }
    if autenticado:
        contexto["menu"] = menu(permisos, voc, inventario, request.path)
        contexto["turno_sesion"] = _turno(usuario, permisos)
    return contexto
