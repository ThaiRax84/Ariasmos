from .models import CuentaBancaria

LUGARES = {
    CuentaBancaria.AMBOS: "en referencia numérica y en concepto",
    CuentaBancaria.NUMERICA: "en referencia numérica",
    CuentaBancaria.CONCEPTO: "en concepto",
}


def datos_de_pago():
    cuenta = CuentaBancaria.principal_activa()
    if cuenta is None:
        return None
    return {"cuenta": cuenta, "medios": list(cuenta.medios.filter(activo=True)), "lugar": LUGARES[cuenta.referencia_en]}
