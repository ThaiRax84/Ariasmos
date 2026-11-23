from .models import Ajuste

AJUSTES = {
    "dias_vigencia": (30, 1, 366),
    "dias_gracia": (14, 0, 90),
    "dias_codigo": (7, 1, 90),
    "minutos_tolerancia": (10, 1, 60),
    "rechazos_por_hora": (30, 1, 10000),
}


def valor(clave):
    omision, minimo, maximo = AJUSTES[clave]
    guardado = (
        Ajuste.objects.filter(clave=clave).values_list("valor", flat=True).first()
    )
    return (
        guardado if guardado is not None and minimo <= guardado <= maximo else omision
    )
