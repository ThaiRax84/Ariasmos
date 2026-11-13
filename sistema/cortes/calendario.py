import json
import re
from datetime import datetime, time, timedelta

from configuracion.models import PARAMETROS, parametro

DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
HORA = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
PROPUESTO = {str(dia): "18:00" for dia in range(6)}


class CalendarioInvalido(ValueError):
    pass


def validar(datos):
    if not isinstance(datos, dict):
        raise CalendarioInvalido("El calendario debe relacionar días de la semana con horas.")
    limpio = {}
    for clave, hora in datos.items():
        if not isinstance(clave, str) or clave not in {str(d) for d in range(7)}:
            raise CalendarioInvalido("Los días van de 0 (lunes) a 6 (domingo).")
        if not isinstance(hora, str) or not HORA.match(hora):
            raise CalendarioInvalido(f"{DIAS[int(clave)]}: escribe la hora como HH:MM, por ejemplo 18:00.")
        limpio[clave] = hora
    return dict(sorted(limpio.items()))


def desde_texto(texto):
    try:
        datos = json.loads(texto)
    except (TypeError, ValueError, RecursionError):
        raise CalendarioInvalido("El calendario guardado no es válido.")
    return validar(datos)


def a_texto(calendario):
    return json.dumps(validar(calendario), separators=(",", ":"), sort_keys=True)


def actual():
    try:
        return desde_texto(parametro("calendario_corte"))
    except CalendarioInvalido:
        return desde_texto(PARAMETROS["calendario_corte"][0])


def todos_los_dias(hora):
    return {str(dia): hora for dia in range(7)}


def limite(abierto, calendario=None):
    calendario = actual() if calendario is None else calendario
    for desfase in range(7):
        dia = abierto.date() + timedelta(days=desfase)
        hora = calendario.get(str(dia.weekday()))
        if hora:
            return datetime.combine(dia, time.fromisoformat(hora), tzinfo=abierto.tzinfo)
    return None


def describir(calendario=None):
    calendario = actual() if calendario is None else calendario
    if not calendario:
        return "sin corte de caja"
    return ", ".join(f"{DIAS[int(dia)].lower()} {hora}" for dia, hora in calendario.items())
