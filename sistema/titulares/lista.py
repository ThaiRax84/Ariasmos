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


TODOS = "todos"
CON_ADEUDO = "adeudo"
REZAGADOS = "rezago"


def _con_adeudo(consulta):
    deudores = libro.con_saldo(Cargo.objects.filter(titular__in=consulta.values("pk"))).filter(saldo__gt=0).values("titular_id")
    return consulta.filter(pk__in=deudores)


def _rezagados(usuario):
    from rezagos import calculo
    from rezagos.presentacion import ve_dirigidas

    dirigidas = ve_dirigidas(usuario)
    return {pk for pk, s in calculo.evaluar().items() if s.aviso or s.marcas(dirigidas)}


def filtros_de_estado(request, estados):
    saldos = ve_saldos(request.user)
    permitidos = [TODOS] + ([CON_ADEUDO] if saldos else []) + [REZAGADOS]
    pedido = request.GET.get("estado", TODOS)
    elegido = pedido if pedido in permitidos else TODOS
    activos = Titular.objects.filter(estado__in=estados)
    rezagados = _rezagados(request.user)
    cuentas = {TODOS: activos.count(), REZAGADOS: activos.filter(pk__in=rezagados).count()}
    if saldos:
        cuentas[CON_ADEUDO] = _con_adeudo(activos).count()
    return elegido, [{"clave": c, "cuenta": cuentas[c]} for c in permitidos], rezagados


def preparar(request, lista, estados, con_filtros=False):
    texto = " ".join(request.GET.get("q", "").split())[:LARGO_FILTRO]
    orden = elegir(request, lista)
    base = Titular.objects.filter(estado__in=estados).select_related("familia", "agrupacion")
    elegido, filtros = "", []
    if con_filtros:
        elegido, filtros, rezagados = filtros_de_estado(request, estados)
        if elegido == CON_ADEUDO:
            base = _con_adeudo(base)
        elif elegido == REZAGADOS:
            base = base.filter(pk__in=rezagados)
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
    return {"q": texto, "orden": orden, "pagina": pagina, "filas": filas, "ve_saldos": saldos, "completos": completos, "estado": elegido if elegido != TODOS else "", "filtros": filtros}
