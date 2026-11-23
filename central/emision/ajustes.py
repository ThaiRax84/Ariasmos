from .models import Ajuste

AJUSTES = {"dias_vigencia": 30, "dias_gracia": 14, "dias_codigo": 7, "minutos_tolerancia": 10, "rechazos_por_hora": 30}


def valor(clave):
    guardado = Ajuste.objects.filter(clave=clave).values_list("valor", flat=True).first()
    return AJUSTES[clave] if guardado is None else guardado
