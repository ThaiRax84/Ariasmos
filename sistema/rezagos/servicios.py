from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone

from auditoria.servicios import diferencias, registrar
from configuracion.models import Parametro

from . import calculo, tras_alta
from .models import VALOR, ExcepcionLimite, LimiteAdeudo, ReglaRezago

EVENTOS_LIMITES = ("limites_adeudo_cambiados", "excepcion_limite_guardada", "excepcion_limite_quitada")


def sin_credito(titular):
    return calculo.sin_credito(titular)


def _a_solicitud(request, accion, titular, datos):
    from solicitudes import motor

    try:
        resultado = motor.ejecutar(accion, request.user, titular, datos, request=request)
    except motor.ErrorSolicitud as error:
        return None, str(error)
    messages.info(request, f"{titular} está sin crédito: quedó como solicitud y la autoriza otra persona. Recibir pagos no cambia.")
    return redirect("solicitudes:detalle", pk=resultado.solicitud.pk), None


def solicitar_cargo(request, titular, concepto, cantidad, unitario):
    return _a_solicitud(request, "cargo_sin_credito", titular, {"concepto": concepto.pk, "cantidad": cantidad, "importe_unitario": unitario})


def solicitar_venta(request, titular, renglones):
    return _a_solicitud(request, "venta_sin_credito", titular, {"renglones": [[articulo, cantidad] for articulo, cantidad in renglones]})


def foto_limites(limite):
    return {"modo_importe": limite.modo_importe, "importe_maximo": limite.importe_maximo if limite.modo_importe == VALOR else None, "modo_dias": limite.modo_dias, "dias_maximos": limite.dias_maximos if limite.modo_dias == VALOR else None}


def guardar_limites(datos, usuario, request=None):
    with transaction.atomic():
        limite = LimiteAdeudo.actual()
        antes = foto_limites(limite)
        limite.modo_importe = datos["modo_importe"]
        limite.importe_maximo = datos["importe_maximo"] if datos["modo_importe"] == VALOR else 0
        limite.modo_dias = datos["modo_dias"]
        limite.dias_maximos = datos["dias_maximos"] if datos["modo_dias"] == VALOR else 0
        limite.save()
        despues = foto_limites(limite)
        cambios = diferencias(antes, despues)
        if cambios:
            registrar("limites_adeudo_cambiados", usuario=usuario, objeto=limite, datos={"antes": antes, "despues": despues, "cambios": cambios}, request=request)
    return bool(cambios)


def foto_excepcion(excepcion):
    if excepcion is None:
        return {}
    return {
        "modo_importe": excepcion.modo_importe,
        "importe_maximo": excepcion.importe_maximo if excepcion.modo_importe == VALOR else None,
        "modo_dias": excepcion.modo_dias,
        "dias_maximos": excepcion.dias_maximos if excepcion.modo_dias == VALOR else None,
        "motivo": excepcion.motivo,
        "vigente_hasta": excepcion.vigente_hasta.isoformat() if excepcion.vigente_hasta else None,
    }


def guardar_excepcion(titular, datos, usuario, request=None):
    with transaction.atomic():
        excepcion = ExcepcionLimite.objects.select_for_update().filter(titular=titular).first()
        antes = foto_excepcion(excepcion)
        if datos.get("quitar"):
            if excepcion is None:
                return False
            excepcion.delete()
            registrar("excepcion_limite_quitada", usuario=usuario, titular=titular.pk, datos={"titular": titular.matricula, "antes": antes, "despues": {}, "cambios": diferencias(antes, {})}, request=request)
            return True
        excepcion = excepcion or ExcepcionLimite(titular=titular, creada_por=usuario)
        excepcion.modo_importe = datos["modo_importe"]
        excepcion.importe_maximo = datos["importe_maximo"] if datos["modo_importe"] == VALOR else 0
        excepcion.modo_dias = datos["modo_dias"]
        excepcion.dias_maximos = datos["dias_maximos"] if datos["modo_dias"] == VALOR else 0
        excepcion.motivo = datos["motivo"]
        excepcion.vigente_hasta = datos.get("vigente_hasta")
        excepcion.save()
        despues = foto_excepcion(excepcion)
        cambios = diferencias(antes, despues)
        if cambios:
            registrar("excepcion_limite_guardada", usuario=usuario, objeto=excepcion, titular=titular.pk, datos={"titular": titular.matricula, "antes": antes, "despues": despues, "cambios": cambios}, request=request)
    return bool(cambios)


def foto_regla(regla):
    if regla is None or regla.pk is None:
        return {}
    return {
        "nombre": regla.nombre,
        "texto": regla.texto,
        "alcance": regla.alcance,
        "agrupacion": str(regla.agrupacion) if regla.agrupacion_id else None,
        "titular": regla.titular.matricula if regla.titular_id else None,
        "dias_minimos": regla.dias_minimos,
        "importe_minimo": regla.importe_minimo,
        "al_rebasar_limite": regla.al_rebasar_limite,
        "acciones": regla.acciones,
        "activa": regla.activa,
    }


def guardar_regla(regla, datos, usuario, request=None):
    with transaction.atomic():
        antes = foto_regla(regla)
        nueva = regla.pk is None
        for campo in ("nombre", "texto", "alcance", "agrupacion", "titular", "dias_minimos", "importe_minimo", "al_rebasar_limite", "activa") + ReglaRezago.ACCIONES:
            setattr(regla, campo, datos[campo])
        regla.save()
        despues = foto_regla(regla)
        registrar(
            "regla_rezago_creada" if nueva else "regla_rezago_cambiada",
            usuario=usuario,
            objeto=regla,
            titular=regla.titular_id,
            datos={"nombre": regla.nombre, "antes": antes, "despues": despues, "cambios": diferencias(antes, despues)},
            request=request,
        )
    return regla


def guardar_recargos_tras_alta(valor, usuario, request=None):
    antes = tras_alta.modo()
    if valor not in (tras_alta.SIGUIENTE_PERIODO, tras_alta.DESDE_ALTA):
        raise ValueError("valor no permitido")
    if valor == antes:
        return False
    with transaction.atomic():
        Parametro.objects.update_or_create(clave="recargos_tras_alta", defaults={"valor": valor})
        registrar("recargos_tras_alta_cambiado", usuario=usuario, datos={"cambios": {"recargos_tras_alta": [antes, valor]}}, request=request)
    return True


def cargar_de_plantilla(datos, request=None):
    if ReglaRezago.objects.exists():
        return 0
    creadas = 0
    for definicion in datos.get("rezagos", []):
        regla = ReglaRezago(
            nombre=definicion["nombre"],
            texto=definicion["texto"],
            dias_minimos=definicion.get("dias_minimos"),
            al_rebasar_limite=definicion.get("al_rebasar_limite", False),
            **{accion: accion in definicion["acciones"] for accion in ReglaRezago.ACCIONES},
        )
        regla.save()
        creadas += 1
    if creadas:
        registrar("reglas_rezago_de_plantilla", datos={"reglas": [d["nombre"] for d in datos.get("rezagos", [])]}, request=request)
    return creadas


def exportar_reglas():
    return [
        {"nombre": r.nombre, "texto": r.texto, **({"dias_minimos": r.dias_minimos} if r.dias_minimos else {}), **({"al_rebasar_limite": True} if r.al_rebasar_limite else {}), "acciones": r.acciones}
        for r in ReglaRezago.objects.filter(activa=True, alcance=ReglaRezago.TODOS, importe_minimo__isnull=True)
        if r.dias_minimos or r.al_rebasar_limite
    ][:50]


def cambios_ajenos(usuario, dias=7):
    from auditoria.models import Evento

    desde = timezone.now() - timedelta(days=dias)
    eventos = Evento.objects.filter(accion__in=EVENTOS_LIMITES, momento__gte=desde).exclude(usuario=usuario).select_related("usuario").order_by("-numero")[:50]
    lista = []
    for evento in eventos:
        datos = evento.datos or {}
        cambios = datos.get("cambios") if isinstance(datos.get("cambios"), dict) else {}
        lista.append({"momento": evento.momento, "quien": str(evento.usuario) if evento.usuario else "", "accion": evento.accion, "matricula": str(datos.get("titular") or ""), "cambios": [{"campo": c, "antes": v[0], "despues": v[1]} for c, v in cambios.items() if isinstance(v, list) and len(v) == 2]})
    return lista
