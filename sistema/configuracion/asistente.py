import hashlib
import hmac

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.db import transaction
from django.forms.utils import ErrorDict
from django.http import Http404, QueryDict
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters

from auditoria.servicios import diferencias, registrar
from actualizaciones import servicios as actualizaciones
from banco import conciliacion
from banco.formularios import FormularioCuenta
from banco.models import CuentaBancaria
from banco.servicios import guardar_cuenta
from banco.views import avisar as avisar_banco
from caja.models import Denominacion
from cobros.models import ConceptoCobro, ReglaRecargo
from cuentas import qr, secretos
from cuentas import servicios as cuentas_servicios
from cuentas.formularios import FormularioCodigo
from cuentas.models import CodigoUsado, Usuario
from cortes.models import TIPOS as TIPOS_CORTE
from cortes.models import DefinicionCorte, Destino, ReglaDestino
from nucleo import sobre, totp
from respaldos.servicios import clave_respaldo
from rezagos.servicios import cargar_de_plantilla as cargar_reglas_de_rezago

from . import esquema, plantillas, zonas
from . import marca as marca_negocio
from .formularios import (
    IMPORTAR,
    FormularioAsistenteConceptos,
    FormularioAsistenteCortes,
    FormularioAsistenteInicio,
    FormularioAsistenteUsuario,
    FormularioCajaCortes,
    FormularioDenominacionesMoneda,
    FormularioLogo,
    FormularioMarca,
    FormularioPersonalizar,
    FormularioReglas,
    FormularioRevisarPlantilla,
    TOPES_CARPETA,
    guardar_caja,
    valores_caja,
    valores_reglas,
)
from .resumen import resumir
from .models import VOCABULARIO_BASE, Negocio, Parametro, Vocabulario, con_vocabulario, hoy_negocio, parametro, vocabulario

CLAVE_SESION = "asistente"


def _disponible(request):
    negocio = Negocio.actual()
    if negocio and negocio.configurado:
        raise Http404
    return negocio


def _estado(request):
    return request.session.get(CLAVE_SESION) or {}


def _guardar_estado(request, **cambios):
    estado = dict(_estado(request))
    estado.update(cambios)
    request.session[CLAVE_SESION] = estado


def _token_valido(token):
    esperado = getattr(settings, "TOKEN_ASISTENTE_HASH", "")
    if not esperado or not token:
        return False
    return hmac.compare_digest(hashlib.sha256(token.encode("utf-8")).hexdigest(), esperado)


NOMBRES_PASOS = ("Negocio y plantilla", "Vocabulario y conceptos", "Importes", "Marca", "Datos de pago", "Caja: cortes y retiros", "Reglas del negocio", "Entrega y respaldo", "Primer usuario", "Autenticador")
TOTAL_PASOS = len(NOMBRES_PASOS)
PASO = {nombre: numero for numero, nombre in enumerate(("inicio", "personalizar", "conceptos", "marca", "pago", "caja", "reglas", "cortes", "usuario", "codigo"), start=1)}


NOMBRE_DE_PASO = {numero: nombre for nombre, numero in PASO.items()}
ANTERIOR = {"conceptos": "personalizar", "marca": "conceptos", "pago": "marca", "caja": "pago", "reglas": "caja", "cortes": "reglas", "usuario": "cortes", "codigo": "usuario"}
RESERVADOS = {"csrfmiddlewaretoken", "ficha_envio", "token", "contrasena1", "contrasena2", "clave_canal", "codigo", "atras", "omitir", "accion", "seguir", "guardada"}


INTROS = {
    "inicio": "Empecemos: dinos cómo se llama tu negocio y a qué se parece. Todo se puede cambiar después en Configuración.",
    "personalizar": "La plantilla ya quedó cargada. Si te sirve como está, sigue adelante; todo se puede cambiar después en Configuración.",
    "conceptos": "Escribe cuánto cuesta cada concepto y cuándo vence. Lo que dejes vacío se completa después en Configuración.",
    "marca": "Sube el logo del negocio y te proponemos los colores del programa tomados de él. Puedes aceptarlos, elegir otros u omitir este paso.",
    "pago": "Con estos datos se arma la ficha de pago que se entrega a cada {titular_min}. Puedes omitir este paso y capturarlo después.",
    "caja": "Cada negocio decide cuándo hace su corte y cuánto efectivo puede salir de la caja sin pedir permiso. Se puede cambiar después.",
    "reglas": "Pequeños detalles de cómo trabaja tu negocio. Si no sabes qué poner, deja lo que ya viene: sirve para empezar hoy.",
    "cortes": "Dónde se guardan los cortes y los respaldos. Puedes omitir este paso y configurarlo después.",
    "usuario": "La primera persona que entra al programa. Después ella da de alta a las demás.",
    "codigo": "Quien dirige el negocio entra con su contraseña y con un código de su teléfono. Así, aunque alguien conozca la contraseña, no puede entrar ni autorizar nada sin el teléfono.",
}


def _contexto_pasos(request, numero):
    nombre = NOMBRE_DE_PASO.get(numero, "")
    hechos = _estado(request).get("autorizado")
    enlaces = [(n, f"asistente:{NOMBRE_DE_PASO[i]}" if hechos and i < numero and NOMBRE_DE_PASO[i] != "inicio" else "") for i, n in enumerate(NOMBRES_PASOS, start=1)]
    intro = con_vocabulario(INTROS.get(nombre, ""))
    return {"paso": numero, "total": TOTAL_PASOS, "nombres_pasos": NOMBRES_PASOS, "pasos_enlaces": enlaces, "anterior": ANTERIOR.get(nombre, ""), "intro": intro}


def _paso(request, plantilla, formulario, numero, titulo, **extra):
    return render(request, plantilla, {"formulario": formulario, "titulo": titulo, **_contexto_pasos(request, numero), **extra})


def _atras(request, paso):
    borradores = dict(_estado(request).get("borradores") or {})
    borradores[paso] = {clave: request.POST.getlist(clave)[:50] for clave in list(request.POST)[:300] if clave not in RESERVADOS}
    _guardar_estado(request, borradores=borradores)
    return redirect(f"asistente:{ANTERIOR[paso]}")


def _pide_atras(request, paso):
    return request.method == "POST" and request.POST.get("atras") and paso in ANTERIOR


def _recordar(request, paso, *formularios):
    borrador = (_estado(request).get("borradores") or {}).get(paso)
    if request.method != "GET" or not borrador:
        return
    datos = QueryDict(mutable=True)
    for clave, valores in borrador.items():
        datos.setlist(clave, [str(v)[:2000] for v in valores])
    for formulario in formularios:
        if formulario is not None and not formulario.is_bound:
            formulario.data = datos
            formulario.is_bound = True
            formulario._errors = ErrorDict()


def _olvidar(request, paso):
    borradores = dict(_estado(request).get("borradores") or {})
    if borradores.pop(paso, None) is not None:
        _guardar_estado(request, borradores=borradores)


def _leer_plantilla(formulario):
    elegida = formulario.cleaned_data["plantilla"]
    if elegida != IMPORTAR:
        return elegida, plantillas.leer(elegida)
    archivo = formulario.cleaned_data["archivo"]
    if archivo.size > esquema.LIMITE_BYTES:
        raise esquema.PlantillaInvalida("El archivo pasa de 256 KB.")
    return "importada", esquema.desde_bytes(archivo.read(esquema.LIMITE_BYTES + 1))


def inicio(request):
    negocio = _disponible(request)
    inicial = {"nombre": negocio.nombre, "zona_horaria": negocio.zona_horaria, "moneda": negocio.moneda, "plantilla": negocio.plantilla} if negocio else {"zona_horaria": zonas.de_la_computadora(), "plantilla": "generico"}
    datos_post = request.POST if request.method == "POST" else None
    formulario = FormularioAsistenteInicio(datos_post, request.FILES if request.method == "POST" else None, plantillas=plantillas.disponibles(con_descripcion=True), initial=inicial)
    if request.method == "POST" and formulario.is_valid():
        if not _token_valido(formulario.cleaned_data["token"]):
            registrar("asistente_token_invalido", request=request)
            messages.error(request, "El token de instalación no es correcto.")
            return _paso(request, "asistente/paso.html", formulario, PASO["inicio"], "Datos del negocio y plantilla")
        try:
            origen, datos = _leer_plantilla(formulario)
        except esquema.PlantillaInvalida as error:
            registrar("plantilla_rechazada", datos={"motivo": str(error)[:200]}, request=request)
            formulario.add_error("archivo" if formulario.cleaned_data["plantilla"] == IMPORTAR else "plantilla", f"La plantilla no es válida: {error}")
            return _paso(request, "asistente/paso.html", formulario, 1, "Datos del negocio y plantilla")
        with transaction.atomic():
            guardado, _ = Negocio.objects.update_or_create(
                pk=1,
                defaults={"nombre": formulario.cleaned_data["nombre"], "zona_horaria": formulario.cleaned_data["zona_horaria"], "moneda": formulario.cleaned_data["moneda"], "plantilla": origen, "configurado": False},
            )
            registrar("asistente_negocio", objeto=guardado, datos={"nombre": guardado.nombre, "plantilla": origen, "moneda": guardado.moneda}, request=request)
        _guardar_estado(request, inventario=bool(formulario.cleaned_data.get("inventario")))
        if origen == "importada":
            _guardar_estado(request, autorizado=True, pendiente=datos)
            return redirect("asistente:revisar")
        _aplicar_plantilla(request, datos, origen)
        return redirect("asistente:personalizar")
    return _paso(request, "asistente/paso.html", formulario, 1, "Datos del negocio y plantilla")


def _aplicar_plantilla(request, datos, origen):
    with transaction.atomic():
        plantillas.cargar_datos(datos, origen, request=request)
        cargar_reglas_de_rezago(datos, request=request)
        inventario = bool(_estado(request).get("inventario"))
        Parametro.objects.update_or_create(clave="modulo_inventario", defaults={"valor": "1" if inventario else "0"})
        registrar("asistente_inventario", datos={"modulo_inventario": inventario, "origen": "asistente"}, request=request)
    _guardar_estado(request, autorizado=True, pendiente=None, rol_inicial=datos["rol_inicial"], recargos=plantillas.recargos(datos))


def revisar(request):
    negocio = _exigir_autorizado(request)
    pendiente = _estado(request).get("pendiente")
    if negocio is None or not pendiente:
        return redirect("asistente:inicio")
    try:
        datos = esquema.validar(pendiente)
    except esquema.PlantillaInvalida:
        return redirect("asistente:inicio")
    resumen = resumir(datos)
    formulario = FormularioRevisarPlantilla(request.POST if request.method == "POST" else None, advertencias=bool(resumen["advertencias"]))
    if request.method == "POST" and formulario.is_valid():
        if resumen["advertencias"]:
            registrar("plantilla_aceptada_con_advertencias", datos={"advertencias": resumen["advertencias"]}, request=request)
        _aplicar_plantilla(request, datos, "importada")
        return redirect("asistente:personalizar")
    return _paso(request, "asistente/revisar.html", formulario, 1, "Revisa la plantilla antes de aplicarla", resumen=resumen, nombre=datos["nombre"])


def _exigir_autorizado(request):
    negocio = _disponible(request)
    if negocio is None or not _estado(request).get("autorizado"):
        return None
    return negocio


def personalizar(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    lista = list(ConceptoCobro.objects.all())
    antes = vocabulario()
    formulario = FormularioPersonalizar(request.POST if request.method == "POST" else None, textos=antes, conceptos=lista)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        recargos = dict(_estado(request).get("recargos") or {})
        with transaction.atomic():
            for clave in VOCABULARIO_BASE:
                Vocabulario.objects.update_or_create(clave=clave, defaults={"texto": datos[clave].strip() or antes[clave]})
            cambios = diferencias(antes, vocabulario())
            if cambios:
                registrar("vocabulario_cambiado", datos={"cambios": cambios, "origen": "asistente"}, request=request)
            for concepto in lista:
                if datos.get(f"quitar_{concepto.pk}"):
                    registrar("concepto_quitado", datos={"nombre": concepto.nombre, "origen": "asistente"}, request=request)
                    recargos.pop(concepto.nombre, None)
                    concepto.delete()
            if datos["nuevo_nombre"]:
                nuevo = ConceptoCobro.objects.create(
                    nombre=datos["nuevo_nombre"],
                    tipo=datos["nuevo_tipo"],
                    periodicidad=datos["nuevo_periodicidad"] if datos["nuevo_tipo"] == ConceptoCobro.RECURRENTE else "",
                    aplica_a=datos.get("nuevo_aplica_a") or ConceptoCobro.MANUAL,
                )
                if datos.get("nuevo_recargo"):
                    recargos[nuevo.nombre] = {"tipo": "fijo", "dias_gracia": 0, "se_repite": False}
                registrar("concepto_creado", objeto=nuevo, datos={"nombre": nuevo.nombre, "cambios": diferencias({}, {"tipo": nuevo.tipo, "periodicidad": nuevo.periodicidad, "aplica_a": nuevo.aplica_a}), "origen": "asistente"}, request=request)
        _guardar_estado(request, recargos=recargos)
        if request.POST.get("seguir") == "agregar":
            return redirect("asistente:personalizar")
        return redirect("asistente:conceptos")
    return _paso(request, "asistente/personalizar.html", formulario, 2, "Revisar vocabulario y conceptos")


def conceptos(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    if _pide_atras(request, "conceptos"):
        return _atras(request, "conceptos")
    lista = ConceptoCobro.objects.all()
    formulario = FormularioAsistenteConceptos(request.POST if request.method == "POST" else None, conceptos=lista, con_recargo=_estado(request).get("recargos") or {})
    _recordar(request, "conceptos", formulario)
    if request.method == "POST" and formulario.is_valid():
        _olvidar(request, "conceptos")
        datos = formulario.cleaned_data
        with transaction.atomic():
            for concepto in lista:
                importe = datos.get(f"importe_{concepto.pk}")
                if importe is not None:
                    concepto.importe_centavos = importe
                if datos.get(f"dia_{concepto.pk}"):
                    concepto.dia_vencimiento = datos[f"dia_{concepto.pk}"]
                valor = datos.get(f"recargo_valor_{concepto.pk}")
                if valor:
                    regla, _ = ReglaRecargo.objects.update_or_create(
                        nombre=f"Recargo de {concepto.nombre}",
                        defaults={"tipo": datos.get(f"recargo_tipo_{concepto.pk}") or ReglaRecargo.FIJO, "valor": valor, "dias_gracia": datos.get(f"recargo_gracia_{concepto.pk}") or 0},
                    )
                    concepto.regla_recargo = regla
                concepto.save()
            registrar("asistente_conceptos", datos={"conceptos": [c.nombre for c in lista]}, request=request)
        return redirect("asistente:marca")
    return _paso(request, "asistente/conceptos.html", formulario, PASO["conceptos"], "Importes de los conceptos", omitir="asistente:marca")


def _vista_de(formulario):
    principal, acento = formulario["color_principal"].value() or "", formulario["color_acento"].value() or ""
    if not (principal and acento):
        return None
    try:
        return {"principal": marca_negocio.validar_color(principal), "acento": marca_negocio.validar_color(acento)}
    except marca_negocio.MarcaInvalida:
        return None


def marca(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    actual = marca_negocio.actual()
    if _pide_atras(request, "marca"):
        return _atras(request, "marca")
    if request.method == "POST" and request.POST.get("omitir"):
        registrar("asistente_marca_omitida", request=request)
        return redirect("asistente:pago")
    inicial = {"color_principal": actual.color_principal if actual else "", "color_acento": actual.color_acento if actual else ""}
    propuesta = _estado(request).get("propuesta_marca")
    if propuesta:
        inicial = {"color_principal": propuesta["principal"], "color_acento": propuesta["acento"]}
    colores = FormularioMarca(initial=inicial)
    logo = FormularioLogo()
    if request.method == "POST":
        try:
            if request.POST.get("accion") == "logo":
                logo = FormularioLogo(request.POST, request.FILES)
                if logo.is_valid():
                    guardada = marca_negocio.guardar_logo(marca_negocio.leer_subida(logo.cleaned_data["archivo"]), None, request)
                    from .views import propuesta_del_logo

                    _guardar_estado(request, propuesta_marca=propuesta_del_logo(guardada))
                    messages.success(request, "Logo guardado. Te proponemos los colores tomados del logo: acéptalos o elige otros.")
                    return redirect("asistente:marca")
            else:
                colores = FormularioMarca(request.POST)
                if colores.is_valid():
                    principal, acento = colores.cleaned_data["color_principal"], colores.cleaned_data["color_acento"]
                    if principal:
                        marca_negocio.guardar_colores(principal, acento, None, request)
                    _guardar_estado(request, propuesta_marca=None)
                    return redirect("asistente:pago")
        except marca_negocio.MarcaInvalida as error:
            registrar("marca_rechazada", datos={"accion": "asistente", "motivo": str(error)}, request=request)
            (logo if request.POST.get("accion") == "logo" else colores).add_error(None, str(error))
    actual = marca_negocio.actual()
    contexto = {"colores": colores, "logo": logo, "actual": actual, "vista": _vista_de(colores), "propuesta": bool(propuesta), "nombre_vista": negocio.nombre}
    return render(request, "asistente/marca.html", {"titulo": "Marca del negocio (opcional)", **_contexto_pasos(request, PASO["marca"]), **contexto})


def vista_marca_css(request):
    _disponible(request)
    return marca_negocio.respuesta_vista(request)


def logo_asistente(request):
    from django.http import HttpResponse

    from caja import comprobantes

    if _exigir_autorizado(request) is None:
        raise Http404
    actual = marca_negocio.actual()
    try:
        contenido = marca_negocio.leer_logo(actual)
    except (OSError, comprobantes.ComprobanteInvalido, marca_negocio.MarcaInvalida):
        contenido = None
    if not contenido:
        raise Http404
    respuesta = HttpResponse(contenido, content_type=comprobantes.TIPOS_MIME[actual.logo_tipo])
    respuesta["Content-Security-Policy"] = "default-src 'none'; sandbox"
    respuesta["X-Content-Type-Options"] = "nosniff"
    respuesta["Cache-Control"] = "no-store"
    return respuesta


def pago(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    if _pide_atras(request, "pago"):
        return _atras(request, "pago")
    actual = CuentaBancaria.principal_activa()
    formulario = FormularioCuenta(request.POST if request.method == "POST" else None, cuenta=actual, en_asistente=True)
    _recordar(request, "pago", formulario)
    if request.method == "POST" and formulario.is_valid():
        _olvidar(request, "pago")
        guardada = guardar_cuenta(formulario, None, cuenta=actual, request=request, forzar_principal=True)
        avisar_banco(request, formulario, guardada)
        return redirect("asistente:caja")
    return _paso(request, "asistente/pago.html", formulario, PASO["pago"], "Datos de pago (opcional)")


def caja(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    if _pide_atras(request, "caja"):
        return _atras(request, "caja")
    antes = valores_caja()
    datos_post = request.POST if request.method == "POST" else None
    formulario = FormularioCajaCortes(datos_post, valores=antes)
    faltan = not Denominacion.objects.filter(activa=True).exists()
    piezas = FormularioDenominacionesMoneda(datos_post, codigo=negocio.moneda, prefix="moneda") if faltan else None
    _recordar(request, "caja", formulario, piezas)
    if request.method == "POST" and formulario.is_valid() and (piezas is None or piezas.is_valid()):
        _olvidar(request, "caja")
        nuevos = formulario.valores()
        with transaction.atomic():
            guardar_caja(nuevos)
            if piezas is not None:
                for valor, tipo in piezas.piezas():
                    Denominacion.objects.get_or_create(valor=valor, defaults={"tipo": tipo})
                registrar("asistente_denominaciones", datos={"moneda": negocio.moneda, "denominaciones": piezas.cleaned_data["denominaciones"]}, request=request)
            registrar("asistente_caja", datos={"cambios": diferencias(antes, valores_caja()), "origen": "asistente"}, request=request)
        return redirect("asistente:reglas")
    return _paso(request, "asistente/caja.html", formulario, PASO["caja"], "Caja: cortes y retiros", piezas=piezas, denominaciones=list(Denominacion.objects.filter(activa=True)))


def reglas(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    if _pide_atras(request, "reglas"):
        return _atras(request, "reglas")
    antes = valores_reglas()
    formulario = FormularioReglas(request.POST if request.method == "POST" else None, valores=antes)
    _recordar(request, "reglas", formulario)
    if request.method == "POST" and request.POST.get("omitir"):
        registrar("asistente_reglas_omitidas", request=request)
        return redirect("asistente:cortes")
    if request.method == "POST" and formulario.is_valid():
        _olvidar(request, "reglas")
        with transaction.atomic():
            for clave, valor in formulario.valores().items():
                Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})
            registrar("asistente_reglas", datos={"cambios": diferencias(antes, valores_reglas()), "origen": "asistente"}, request=request)
        return redirect("asistente:cortes")
    return _paso(request, "asistente/paso.html", formulario, PASO["reglas"], "Reglas del negocio (opcional)", omitir=True)


@sensitive_post_parameters("clave_canal")
def cortes(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    if _pide_atras(request, "cortes"):
        return _atras(request, "cortes")
    if request.method == "POST" and request.POST.get("omitir"):
        registrar("asistente_cortes_omitido", request=request)
        return redirect("asistente:usuario")
    niveles = {d.tipo: d.nivel for d in DefinicionCorte.objects.all()}
    pendiente = Negocio.objects.filter(pk=1, clave_recuperacion_pendiente=True).exists()
    formulario = FormularioAsistenteCortes(
        request.POST if request.method == "POST" else None, niveles=niveles, carpeta=negocio.carpeta_respaldo, carpeta_banco=negocio.carpeta_banco, pide_clave=pendiente, topes=conciliacion.topes_actuales()
    )
    _recordar(request, "cortes", formulario)
    if request.method == "POST" and formulario.is_valid():
        _olvidar(request, "cortes")
        datos = formulario.cleaned_data
        with transaction.atomic():
            if datos["carpeta_entrega"]:
                destino = Destino.objects.create(nombre="Carpeta de cortes", ruta=datos["carpeta_entrega"])
                for tipo, _ in TIPOS_CORTE:
                    ReglaDestino.objects.create(destino=destino, tipo=tipo, entregar=True, nivel=datos[f"nivel_{tipo}"])
                registrar("destino_guardado", objeto=destino, datos={"origen": "asistente", "niveles": {t: datos[f"nivel_{t}"] for t, _ in TIPOS_CORTE}}, request=request)
            for tipo, _ in TIPOS_CORTE:
                DefinicionCorte.objects.filter(tipo=tipo).update(nivel=datos[f"nivel_{tipo}"])
            if datos["carpeta_respaldo"]:
                Negocio.objects.filter(pk=1).update(carpeta_respaldo=datos["carpeta_respaldo"])
            antes_topes = {clave: int(parametro(clave)) for clave in TOPES_CARPETA}
            for clave, valor in formulario.topes().items():
                Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})
            if antes_topes != formulario.topes():
                registrar("carpeta_banco_topes", objeto=negocio, datos={"cambios": diferencias(antes_topes, formulario.topes()), "origen": "asistente"}, request=request)
            conciliacion.guardar_topes(formulario.topes_banco(), request=request, origen="asistente")
            canal = formulario.actualizaciones()
            if canal is not None:
                actualizaciones.guardar_configuracion(canal["activa"], canal["repositorio"], canal["clave"], request=request, origen="asistente")
            if datos["carpeta_banco"] != negocio.carpeta_banco:
                Negocio.objects.filter(pk=1).update(carpeta_banco=datos["carpeta_banco"])
                registrar("carpeta_banco_cambiada", objeto=negocio, datos={"cambios": {"carpeta_banco": [negocio.carpeta_banco, datos["carpeta_banco"]]}, "origen": "asistente"}, request=request)
            if pendiente and datos.get("guardada"):
                Negocio.objects.filter(pk=1).update(clave_recuperacion_pendiente=False)
                registrar("clave_recuperacion_guardada", objeto=negocio, request=request)
            registrar("asistente_cortes", datos={"entrega": bool(datos["carpeta_entrega"]), "respaldo": bool(datos["carpeta_respaldo"]), "carpeta_banco": bool(datos["carpeta_banco"])}, request=request)
        return redirect("asistente:usuario")
    contexto = {"texto_clave": sobre.clave_a_texto(clave_respaldo()) if pendiente else ""}
    respuesta = _paso(request, "asistente/cortes.html", formulario, PASO["cortes"], "Entrega y respaldo", **contexto)
    respuesta["Cache-Control"] = "no-store"
    return respuesta


def usuario(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    if _pide_atras(request, "usuario"):
        return _atras(request, "usuario")
    formulario = FormularioAsistenteUsuario(request.POST if request.method == "POST" else None)
    _recordar(request, "usuario", formulario)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        existente = Usuario.objects.filter(usuario__iexact=datos["usuario"]).first()
        if existente and existente.pk != _estado(request).get("usuario"):
            formulario.add_error("usuario", "Ese usuario ya existe.")
        else:
            rol = plantillas.rol_inicial(_estado(request))
            with transaction.atomic():
                if existente:
                    existente.nombre = datos["nombre"]
                    existente.rol = rol
                    existente.set_password(datos["contrasena1"])
                    existente.save()
                    nuevo = existente
                else:
                    nuevo = Usuario.objects.create_user(datos["usuario"], datos["contrasena1"], nombre=datos["nombre"], rol=rol)
                registrar("usuario_creado", objeto=nuevo, datos={"usuario": nuevo.usuario, "rol": rol.pk, "origen": "asistente"}, request=request)
            previo = _estado(request)
            conserva = previo.get("usuario") == nuevo.pk and previo.get("secreto")
            _guardar_estado(request, usuario=nuevo.pk, secreto=previo["secreto"] if conserva else totp.generar_secreto())
            return redirect("asistente:codigo")
    rol = _estado(request).get("rol_inicial") or ""
    return _paso(request, "asistente/paso.html", formulario, PASO["usuario"], f"Primer usuario ({rol})" if rol else "Primer usuario")


def codigo(request):
    negocio = _exigir_autorizado(request)
    estado = _estado(request)
    if negocio is None or not estado.get("usuario") or not estado.get("secreto"):
        return redirect("asistente:inicio")
    if _pide_atras(request, "codigo"):
        return _atras(request, "codigo")
    nuevo = Usuario.objects.get(pk=estado["usuario"])
    secreto = estado["secreto"]
    formulario = FormularioCodigo(request.POST if request.method == "POST" else None)
    if request.method == "POST" and formulario.is_valid():
        with transaction.atomic():
            usado, _ = cuentas_servicios.consumir_codigo(nuevo, formulario.cleaned_data["codigo"], CodigoUsado.ALTA, secreto=secreto)
            if usado is not None:
                secretos.guardar(nuevo, secreto)
                nuevo.totp_confirmado = True
                nuevo.save(update_fields=["totp_cifrado", "totp_confirmado"])
                dispositivo = request.dispositivo
                cuentas_servicios.aprobar_dispositivo(dispositivo, nuevo, "Servidor (asistente)", request)
                Negocio.objects.filter(pk=1).update(configurado=True)
                Negocio.objects.filter(pk=1, cobro_desde__isnull=True).update(cobro_desde=hoy_negocio())
                registrar("asistente_completado", usuario=nuevo, objeto=negocio, request=request)
        if usado is not None:
            request.session.pop(CLAVE_SESION, None)
            login(request, nuevo, backend="django.contrib.auth.backends.ModelBackend")
            request.session["ultima_actividad"] = timezone.now().timestamp()
            cuentas_servicios.ligar_sesion(request)
            cuentas_servicios.marcar_reingreso(request)
            registrar("inicio_sesion", usuario=nuevo, objeto=nuevo, request=request)
            messages.success(request, "Instalación lista.")
            return redirect("primeros_pasos")
        messages.error(request, "El código no coincide. Revisa la hora del teléfono.")
    contexto = {
        "formulario": formulario,
        **_contexto_pasos(request, PASO["codigo"]),
        "titulo": "Autenticador del primer usuario",
        **qr.contexto(secreto, nuevo.usuario, negocio.nombre),
    }
    respuesta = render(request, "asistente/codigo.html", contexto)
    respuesta["Cache-Control"] = "no-store"
    return respuesta
