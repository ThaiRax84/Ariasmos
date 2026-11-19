from django.core.paginator import Paginator
from django.db.models import Q, Sum

from cobros import libro
from cobros.models import Cargo
from nucleo.matricula import normalizar
from proyecto.orden import elegir
from rezagos.presentacion import ve_saldos

from .models import Titular

POR_PAGINA = 50
LARGO_FILTRO = 60
MAXIMO_PALABRAS = 6
MAXIMO_COMPLETA = 30


def _condicion(palabra):
    condicion = Q(nombre__icontains=palabra) | Q(apellidos__icontains=palabra) | Q(agrupacion__nombre__icontains=palabra) | Q(familia__nombre__icontains=palabra)
    digitos = normalizar(palabra)
    if digitos:
        condicion |= Q(matricula__startswith=digitos)
    return condicion


def filtrar(consulta, texto):
    digitos = normalizar(texto)
    if digitos and len(digitos) >= 3 and not any(c.isalpha() for c in texto):
        return consulta.filter(matricula__startswith=digitos)
    for palabra in texto.split()[:MAXIMO_PALABRAS]:
        consulta = consulta.filter(_condicion(palabra))
    return consulta


def adeudos(ids):
    if not ids:
        return {}
    filas = libro.con_saldo(Cargo.objects.filter(titular_id__in=ids)).filter(saldo__gt=0).order_by().values("titular_id").annotate(total=Sum("saldo"))
    return {f["titular_id"]: f["total"] for f in filas}


def preparar(request, lista, estados):
    texto = " ".join(request.GET.get("q", "").split())[:LARGO_FILTRO]
    orden = elegir(request, lista)
    base = Titular.objects.filter(estado__in=estados).select_related("familia", "agrupacion")
    if texto:
        base = filtrar(base, texto)
    pagina = Paginator(base.order_by(*orden.campos), POR_PAGINA).get_page(request.GET.get("pagina"))
    filas = list(pagina.object_list)
    saldos = ve_saldos(request.user)
    deudas = adeudos([t.pk for t in filas]) if saldos else {}
    for titular in filas:
        titular.adeudo = deudas.get(titular.pk, 0)
    completos = []
    if texto and not filas:
        completos = list(filtrar(Titular.objects.exclude(estado=Titular.RECHAZADO).exclude(estado__in=estados), texto).select_related("familia", "agrupacion").order_by(*orden.campos)[:MAXIMO_COMPLETA])
    return {"q": texto, "orden": orden, "pagina": pagina, "filas": filas, "ve_saldos": saldos, "completos": completos}
