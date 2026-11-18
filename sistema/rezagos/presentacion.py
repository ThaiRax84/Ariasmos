from configuracion.moneda import formatear
from titulares.models import Titular

from . import calculo
from .models import ILIMITADO, NEGOCIO, VALOR

MAXIMO_AVISO = 20
ORDENES = {
    "dias": lambda f: (-f["dias"], f["orden_nombre"]),
    "nombre": lambda f: (f["orden_nombre"], -f["dias"]),
    "matricula": lambda f: (f["matricula"], -f["dias"]),
    "agrupacion": lambda f: (f["agrupacion"].casefold(), -f["dias"], f["orden_nombre"]),
    "adeudo": lambda f: (-f["vencido"], -f["dias"]),
}


def ve_saldos(usuario):
    return usuario.tiene_permiso("ver_titulares")


def ve_dirigidas(usuario):
    return usuario.tiene_permiso("ver_titulares") or usuario.tiene_permiso("configurar_rezagos")


def _fila(titular, situacion, saldos, dirigidas):
    fila = {
        "pk": titular.pk,
        "nombre": titular.nombre_completo,
        "orden_nombre": f"{titular.apellidos} {titular.nombre}".casefold(),
        "matricula": titular.matricula_formateada,
        "agrupacion": str(titular.agrupacion or ""),
        "dias": situacion.dias,
        "texto": situacion.texto_aviso(dirigidas),
        "marcas": situacion.marcas(dirigidas),
        "sin_credito": situacion.sin_credito,
        "vencido": situacion.vencido if saldos else 0,
    }
    if saldos:
        fila["adeudo"] = situacion.vencido
    return fila


def _titulares(ids):
    return {t.pk: t for t in Titular.objects.filter(pk__in=list(ids)).select_related("agrupacion")}


def aviso_para(usuario, situaciones=None):
    situaciones = calculo.evaluar() if situaciones is None else situaciones
    con_aviso = sorted((s for s in situaciones.values() if s.aviso), key=lambda s: (-s.dias, -s.vencido, s.titular_id))
    if not con_aviso:
        return None
    saldos, dirigidas = ve_saldos(usuario), ve_dirigidas(usuario)
    primeros = con_aviso[:MAXIMO_AVISO]
    titulares = _titulares(s.titular_id for s in primeros)
    filas = [_fila(titulares[s.titular_id], s, saldos, dirigidas) for s in primeros if s.titular_id in titulares]
    return {"filas": filas, "total": len(con_aviso), "mas": len(con_aviso) > len(filas), "ver_saldos": saldos, "ver_fichas": saldos}


def lista_para(usuario, orden="dias"):
    situaciones = calculo.evaluar()
    saldos, dirigidas = ve_saldos(usuario), ve_dirigidas(usuario)
    titulares = _titulares(situaciones)
    filas = [_fila(titulares[pk], s, saldos, dirigidas) for pk, s in situaciones.items() if pk in titulares]
    if orden == "adeudo" and not saldos:
        orden = "dias"
    filas.sort(key=ORDENES.get(orden, ORDENES["dias"]))
    return filas


def texto_limite(modo, valor, es_dinero):
    if modo == ILIMITADO:
        return "Ilimitado"
    if modo == NEGOCIO:
        return "Como el negocio"
    if modo == VALOR:
        return f"Hasta {formatear(valor)}" if es_dinero else f"Hasta {valor} días"
    return ""


def efectivo_texto(valor, es_dinero):
    if valor is None:
        return "Ilimitado"
    return f"Hasta {formatear(valor)}" if es_dinero else f"Hasta {valor} días"


CAMPOS = {"modo_importe": "Importe", "importe_maximo": "Importe máximo", "modo_dias": "Días", "dias_maximos": "Días máximos", "motivo": "Motivo", "vigente_hasta": "Vigente hasta"}
MODOS = {ILIMITADO: "Ilimitado", VALOR: "Hasta un valor", NEGOCIO: "Como el negocio"}


def valor_cambio(campo, valor):
    if valor is None or valor == "":
        return "—"
    if campo == "importe_maximo" and isinstance(valor, int):
        return formatear(valor)
    if campo.startswith("modo_"):
        return MODOS.get(valor, str(valor))
    return str(valor)


def cambios_legibles(cambios):
    return [{"momento": c["momento"], "quien": c["quien"], "matricula": c["matricula"], "excepcion": c["accion"] != "limites_adeudo_cambiados", "quitada": c["accion"] == "excepcion_limite_quitada", "renglones": [{"nombre": CAMPOS.get(r["campo"], r["campo"]), "antes": valor_cambio(r["campo"], r["antes"]), "despues": valor_cambio(r["campo"], r["despues"])} for r in c["cambios"]]} for c in cambios]


def filas_cobranza(fecha, como_titular):
    situaciones = [s for s in calculo.evaluar(fecha).values() if s.cobranza]
    if not situaciones:
        return []
    titulares = {t.pk: t for t in Titular.objects.filter(pk__in=[s.titular_id for s in situaciones]).select_related("familia")}
    situaciones.sort(key=lambda s: (-s.dias, s.titular_id))
    return [{"titular": como_titular(titulares[s.titular_id]), "aviso": s.texto_aviso(False), "dias_atraso": s.dias, "importe_pendiente": s.vencido} for s in situaciones if s.titular_id in titulares]
