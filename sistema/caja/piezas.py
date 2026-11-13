from django import forms
from django.db.models import Sum

from configuracion.models import parametro

from .models import Denominacion, MovimientoPiezas

MAXIMO_PIEZAS = 100000


class ErrorPiezas(ValueError):
    pass


def activo():
    return bool(parametro("control_denominaciones"))


def denominaciones():
    return list(Denominacion.objects.filter(activa=True))


def validar(piezas):
    if piezas is None:
        return {}
    if not isinstance(piezas, dict):
        raise ErrorPiezas("Las piezas no son válidas.")
    validas = {d.valor for d in denominaciones()}
    limpio = {}
    for valor, cantidad in piezas.items():
        try:
            valor = int(valor)
        except (TypeError, ValueError):
            raise ErrorPiezas("Denominación no válida.")
        if valor not in validas:
            raise ErrorPiezas("Denominación no válida.")
        if type(cantidad) is not int or cantidad < 0 or cantidad > MAXIMO_PIEZAS:
            raise ErrorPiezas("Cantidad de piezas no válida.")
        if cantidad:
            limpio[str(valor)] = cantidad
    return dict(sorted(limpio.items(), key=lambda par: -int(par[0])))


def total(piezas):
    return sum(int(valor) * cantidad for valor, cantidad in (piezas or {}).items())


def exigir_total(piezas, importe, mensaje):
    limpio = validar(piezas)
    if total(limpio) != importe:
        raise ErrorPiezas(mensaje)
    return limpio


def validar_cobro(importe, recibidas, cambio):
    recibidas = validar(recibidas)
    cambio = validar(cambio)
    entregado = total(recibidas)
    if entregado < importe:
        raise ErrorPiezas("Las piezas recibidas no alcanzan el importe del pago.")
    if total(cambio) != entregado - importe:
        raise ErrorPiezas("El cambio capturado debe sumar exactamente la diferencia entre lo recibido y el importe.")
    return {"recibidas": recibidas, "cambio": cambio}


def existencias(turno):
    filas = MovimientoPiezas.objects.filter(turno=turno).values("denominacion").annotate(t=Sum("piezas")).order_by("-denominacion")
    return {str(f["denominacion"]): f["t"] for f in filas if f["t"]}


def disponibles(turno, extra=None):
    reunidas = {int(v): max(c, 0) for v, c in existencias(turno).items()}
    for valor, cantidad in (extra or {}).items():
        reunidas[int(valor)] = reunidas.get(int(valor), 0) + cantidad
    return {v: c for v, c in reunidas.items() if c > 0}


def registrar(turno, usuario, origen, piezas, signo, **referencias):
    filas = [
        MovimientoPiezas(turno=turno, usuario=usuario, origen=origen, denominacion=int(valor), piezas=signo * cantidad, **referencias)
        for valor, cantidad in (piezas or {}).items()
        if cantidad
    ]
    for fila in filas:
        fila.save()
    return filas


def campos(formulario, prefijo, etiqueta, requerido=False):
    nombres = []
    for denominacion in denominaciones():
        nombre = f"{prefijo}{denominacion.valor}"
        formulario.fields[nombre] = forms.IntegerField(label=f"{etiqueta} {denominacion}", min_value=0, max_value=MAXIMO_PIEZAS, required=requerido, initial=0)
        nombres.append((nombre, denominacion.valor))
    return nombres


def leer(datos, nombres):
    return {str(valor): datos.get(nombre) or 0 for nombre, valor in nombres if datos.get(nombre)}


def renglones(esperadas, contadas):
    valores = sorted({int(v) for v in list(esperadas) + list(contadas)}, reverse=True)
    filas = []
    for valor in valores:
        esperada = int(esperadas.get(str(valor), 0))
        contada = int(contadas.get(str(valor), 0))
        filas.append({"denominacion": valor, "esperadas": esperada, "contadas": contada, "diferencia": contada - esperada})
    return filas
