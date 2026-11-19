from django.urls import reverse

from configuracion.contexto import menu
from configuracion.models import con_vocabulario, inventario_activo, vocabulario
from configuracion.moneda import formatear
from rezagos.presentacion import ve_saldos
from titulares import lista
from titulares.models import Titular

LARGO = 60
MAXIMO_PERSONAS = 7
MAXIMO_TOTAL = 40

ACCIONES = (
    ("Cobrar", "Abrir la lista para cobrar", "cobros:buscar", ("registrar_pago_efectivo",)),
    ("Dar de alta", "Registrar a {titular_min} nuevo", "titulares:nuevo", ("solicitar_alta_baja", "alta_baja_directa")),
    ("Abrir o cerrar mi turno", "Mi caja", "caja:inicio", ("turno_caja",)),
    ("Verificar un recibo", "Con su código o su QR", "cobros:verificar", ("ver_titulares",)),
    ("Subir el estado de cuenta", "El archivo que da el banco", "conciliacion:cola", ("conciliar_banco", "sugerir_conciliacion")),
    ("Cambiar colores y logotipo", "Marca del negocio", "configuracion:marca", ("administrar_configuracion",)),
)


def llano(texto):
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn").lower()


def _coincide(texto, buscado):
    return not buscado or buscado in llano(texto)


def _acciones(permisos, voc, buscado):
    resultado = []
    for titulo, detalle, nombre, requeridos in ACCIONES:
        if not any(p in permisos for p in requeridos):
            continue
        detalle = con_vocabulario(detalle, voc)
        if _coincide(f"{titulo} {detalle}", buscado):
            resultado.append({"grupo": "Acciones", "titulo": titulo, "detalle": detalle, "url": reverse(nombre), "tipo": "accion"})
    return resultado


def _pantallas(permisos, voc, buscado):
    armado = menu(permisos, voc, inventario_activo(), "")
    vistas = set()
    resultado = []
    for entrada in armado["visibles"] + armado["mas"]:
        if entrada["url"] in vistas or not _coincide(entrada["texto"], buscado):
            continue
        vistas.add(entrada["url"])
        resultado.append({"grupo": "Pantallas", "titulo": entrada["texto"], "detalle": "", "url": entrada["url"], "tipo": "pantalla"})
    return resultado


MAXIMO_REZAGADOS = 3


def _rezagados(usuario):
    from rezagos import calculo
    from rezagos.presentacion import ve_dirigidas

    dirigidas = ve_dirigidas(usuario)
    situaciones = sorted((s for s in calculo.evaluar().values() if s.aviso or s.marcas(dirigidas)), key=lambda s: (-s.dias, -s.vencido, s.titular_id))
    ids = [s.titular_id for s in situaciones[: MAXIMO_REZAGADOS * 3]]
    por_id = {t.pk: t for t in Titular.objects.filter(pk__in=ids, estado=Titular.ACTIVO).select_related("agrupacion")}
    return [por_id[pk] for pk in ids if pk in por_id][:MAXIMO_REZAGADOS]


def _personas(usuario, permisos, voc, texto):
    cobra = "registrar_pago_efectivo" in permisos
    mira = "ver_titulares" in permisos
    if not (cobra or mira):
        return []
    if not texto:
        return [dict(fila, grupo="Rezagados") for fila in _filas(usuario, cobra, voc, _rezagados(usuario))]
    estados = [Titular.ACTIVO] if not mira else [e for e, _ in Titular.ESTADOS if e != Titular.RECHAZADO]
    consulta = lista.filtrar(Titular.objects.filter(estado__in=estados).select_related("agrupacion"), texto).order_by("apellidos", "nombre", "id")[:MAXIMO_PERSONAS]
    return _filas(usuario, cobra, voc, list(consulta))


def _filas(usuario, cobra, voc, filas):
    saldos = ve_saldos(usuario)
    deudas = lista.adeudos([t.pk for t in filas]) if saldos else {}
    resultado = []
    for titular in filas:
        if cobra and titular.estado == Titular.ACTIVO:
            url = f"{reverse('cobros:buscar')}?abrir={titular.pk}"
        else:
            url = reverse("titulares:detalle", args=[titular.pk])
        detalle = f"{voc['matricula']} {titular.matricula_formateada}"
        if titular.agrupacion_id:
            detalle += f" · {titular.agrupacion}"
        fila = {"grupo": voc["titulares"], "titulo": titular.nombre_completo, "detalle": detalle, "url": url, "tipo": "persona"}
        if saldos:
            deuda = deudas.get(titular.pk, 0)
            fila["lado"] = formatear(deuda) if deuda else "Al corriente"
        resultado.append(fila)
    return resultado


def buscar(usuario, texto):
    texto = " ".join(str(texto or "").split())[:LARGO]
    buscado = llano(texto)
    permisos = usuario.permisos_efectivos()
    voc = vocabulario()
    resultado = _personas(usuario, permisos, voc, texto) + _acciones(permisos, voc, buscado) + _pantallas(permisos, voc, buscado)
    return resultado[:MAXIMO_TOTAL]
