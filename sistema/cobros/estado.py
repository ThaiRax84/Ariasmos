from django.db.models import Max, Prefetch

from . import libro
from .models import Aplicacion, Cargo, Pago


def estado_cuenta(titulares):
    ids = [t.pk for t in titulares]
    cargos = list(
        libro.con_saldo(Cargo.objects.filter(titular__in=ids))
        .select_related("concepto", "beca", "titular", "cargo_base")
        .prefetch_related("cancelaciones", "prorrogas")
        .annotate(prorroga=Max("prorrogas__fecha_limite"))
        .order_by("vencimiento", "id")
    )
    filas = []
    for cargo in cargos:
        filas.append({"cargo": cargo, "estado": libro.estado_de(cargo), "recargos": [c for c in cargos if c.cargo_base_id == cargo.pk]})
    pagos = list(
        libro.con_remanente(Pago.objects.filter(titular__in=ids))
        .select_related("titular", "recibo", "reversion")
        .prefetch_related(Prefetch("aplicaciones", queryset=Aplicacion.objects.select_related("cargo__titular", "cargo__concepto")))
        .order_by("-fecha", "-id")
    )
    for pago in pagos:
        pago.revertido = hasattr(pago, "reversion")
        pago.disponible = 0 if pago.revertido else pago.remanente
    return {
        "cargos": filas,
        "pagos": pagos,
        "adeudo": sum(c.saldo for c in cargos),
        "a_favor": sum(p.disponible for p in pagos),
        "titulares": titulares,
    }
