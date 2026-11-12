from auditoria.models import Evento
from cuentas.models import Usuario

ACCIONES = {"alta": "el alta", "baja": "la baja", "reactivacion": "la reactivación", "correccion_nombre": "la corrección de nombre"}

VIAS = {"directa": "directamente", "delegacion": "con delegación temporal", "bandeja": "desde la bandeja", "codigo": "con código por teléfono"}

ETIQUETAS = {
    "nombre": "Nombre",
    "apellidos": "Apellidos",
    "notas": "Notas",
    "estado": "Estado",
    "motivo_baja": "Motivo de baja",
    "concepto": "Concepto",
    "importe_centavos": "Importe propio (centavos)",
    "descuento_centesimas": "Descuento (centésimas de %)",
    "vigente_desde": "Vigente desde",
    "vigente_hasta": "Vigente hasta",
    "activo": "Activo",
    "nota": "Nota",
}


def _accion(datos):
    return ACCIONES.get(datos.get("accion", ""), datos.get("accion", ""))


def _via(datos):
    return VIAS.get(datos.get("via", ""), "")


def describir(evento):
    datos = evento.datos or {}
    textos = {
        "titular_creado": lambda: "Capturó el registro",
        "titular_editado": lambda: "Editó datos",
        "contacto_creado": lambda: f"Agregó el contacto {datos.get('contacto', '')}",
        "contacto_editado": lambda: f"Editó el contacto {datos.get('contacto', '')}",
        "alta_aplicada": lambda: f"Aprobó el alta {_via(datos)}",
        "baja_aplicada": lambda: f"Aplicó la baja {_via(datos)}",
        "reactivacion_aplicada": lambda: f"Reactivó el registro {_via(datos)}",
        "correccion_nombre_aplicada": lambda: f"Corrigió el nombre {_via(datos)}",
        "solicitud_creada": lambda: f"Solicitó {_accion(datos)}",
        "solicitud_aprobada": lambda: (
            f"Capturó el código de {datos.get('autorizador_nombre', '')} que autorizó {_accion(datos)}"
            if datos.get("via") == "codigo"
            else f"Aprobó {_accion(datos)} {_via(datos)}"
        ),
        "solicitud_rechazada": lambda: f"Rechazó {_accion(datos)}" + (f": {datos['nota']}" if datos.get("nota") else ""),
        "solicitud_caducada": lambda: f"Caducó la solicitud de {_accion(datos)}",
        "codigo_rechazado": lambda: "Código por teléfono rechazado",
        "codigo_bloqueado": lambda: "Se bloqueó la vía de código por intentos erróneos",
        "plan_cobro_creado": lambda: f"Creó un plan de cobro ({datos.get('nombre', '')})",
        "plan_cobro_cambiado": lambda: f"Cambió un plan de cobro ({datos.get('nombre', '')})",
        "ficha_pago_consultada": lambda: "Consultó la ficha de pago",
        "acceso_denegado": lambda: "Intentó una acción sin permiso",
        "aprobacion_rechazada": lambda: "Intentó aprobar su propia solicitud",
    }
    funcion = textos.get(evento.accion)
    return funcion() if funcion else evento.accion.replace("_", " ").capitalize()


def _valor(valor):
    if valor is None or valor == "":
        return "—"
    if valor is True:
        return "Sí"
    if valor is False:
        return "No"
    if isinstance(valor, list):
        return ", ".join(str(v) for v in valor) or "—"
    return str(valor)


def cambios(evento, voc):
    etiquetas = dict(ETIQUETAS, agrupacion=voc["agrupacion"])
    filas = []
    for clave, par in (evento.datos or {}).get("cambios", {}).items():
        if not isinstance(par, list) or len(par) != 2:
            continue
        filas.append((etiquetas.get(clave, clave), _valor(par[0]), _valor(par[1])))
    return filas


def historial(titular, voc):
    eventos = list(Evento.objects.filter(titular=titular.pk).order_by("-numero")[:500])
    nombres = dict(Usuario.objects.filter(pk__in={e.usuario_id for e in eventos if e.usuario_id}).values_list("pk", "nombre"))
    return [
        {
            "momento": evento.momento,
            "usuario": nombres.get(evento.usuario_id) or evento.usuario_texto or "Sistema",
            "descripcion": describir(evento),
            "cambios": cambios(evento, voc),
        }
        for evento in eventos
    ]
