import hashlib
import hmac

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from auditoria.servicios import diferencias, registrar
from banco.formularios import FormularioCuenta
from banco.models import CuentaBancaria
from banco.servicios import guardar_cuenta
from banco.views import avisar as avisar_banco
from cobros.models import ConceptoCobro, ReglaRecargo
from cuentas import qr, secretos
from cuentas import servicios as cuentas_servicios
from cuentas.formularios import FormularioCodigo
from cuentas.models import CodigoUsado, Usuario
from cortes.models import TIPOS as TIPOS_CORTE
from cortes.models import DefinicionCorte, Destino, ReglaDestino
from nucleo import sobre, totp
from respaldos.servicios import clave_respaldo

from . import esquema, plantillas
from .formularios import (
    IMPORTAR,
    FormularioAsistenteConceptos,
    FormularioAsistenteCortes,
    FormularioAsistenteInicio,
    FormularioAsistenteUsuario,
    FormularioCajaCortes,
    FormularioPersonalizar,
    FormularioRevisarPlantilla,
    TOPES_CARPETA,
    guardar_caja,
    valores_caja,
)
from .resumen import resumir
from .models import VOCABULARIO_BASE, Negocio, Parametro, Vocabulario, hoy_negocio, parametro, vocabulario

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


TOTAL_PASOS = 8


def _paso(request, plantilla, formulario, numero, titulo, **extra):
    return render(request, plantilla, {"formulario": formulario, "paso": numero, "total": TOTAL_PASOS, "titulo": titulo, **extra})


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
    inicial = {"nombre": negocio.nombre, "zona_horaria": negocio.zona_horaria, "moneda": negocio.moneda} if negocio else {}
    datos_post = request.POST if request.method == "POST" else None
    formulario = FormularioAsistenteInicio(datos_post, request.FILES if request.method == "POST" else None, plantillas=plantillas.disponibles(), initial=inicial)
    if request.method == "POST" and formulario.is_valid():
        if not _token_valido(formulario.cleaned_data["token"]):
            registrar("asistente_token_invalido", request=request)
            messages.error(request, "El token de instalación no es correcto.")
            return _paso(request, "asistente/paso.html", formulario, 1, "Datos del negocio y plantilla")
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
                Vocabulario.objects.update_or_create(clave=clave, defaults={"texto": datos[clave].strip()})
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
    lista = ConceptoCobro.objects.all()
    formulario = FormularioAsistenteConceptos(request.POST if request.method == "POST" else None, conceptos=lista, con_recargo=_estado(request).get("recargos") or {})
    if request.method == "POST" and formulario.is_valid():
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
        return redirect("asistente:pago")
    return _paso(request, "asistente/paso.html", formulario, 3, "Importes de los conceptos")


def pago(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    actual = CuentaBancaria.principal_activa()
    formulario = FormularioCuenta(request.POST if request.method == "POST" else None, cuenta=actual, en_asistente=True)
    if request.method == "POST" and formulario.is_valid():
        guardada = guardar_cuenta(formulario, None, cuenta=actual, request=request, forzar_principal=True)
        avisar_banco(request, formulario, guardada)
        return redirect("asistente:caja")
    return _paso(request, "asistente/pago.html", formulario, 4, "Datos de pago")


def caja(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    antes = valores_caja()
    formulario = FormularioCajaCortes(request.POST if request.method == "POST" else None, valores=antes)
    if request.method == "POST" and formulario.is_valid():
        nuevos = formulario.valores()
        with transaction.atomic():
            guardar_caja(nuevos)
            registrar("asistente_caja", datos={"cambios": diferencias(antes, valores_caja()), "origen": "asistente"}, request=request)
        return redirect("asistente:cortes")
    return _paso(request, "asistente/paso.html", formulario, 5, "Caja: cortes y retiros")


def cortes(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    if request.method == "POST" and request.POST.get("omitir"):
        registrar("asistente_cortes_omitido", request=request)
        return redirect("asistente:usuario")
    niveles = {d.tipo: d.nivel for d in DefinicionCorte.objects.all()}
    pendiente = Negocio.objects.filter(pk=1, clave_recuperacion_pendiente=True).exists()
    formulario = FormularioAsistenteCortes(request.POST if request.method == "POST" else None, niveles=niveles, carpeta=negocio.carpeta_respaldo, carpeta_banco=negocio.carpeta_banco, pide_clave=pendiente)
    if request.method == "POST" and formulario.is_valid():
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
            if datos["carpeta_banco"] != negocio.carpeta_banco:
                Negocio.objects.filter(pk=1).update(carpeta_banco=datos["carpeta_banco"])
                registrar("carpeta_banco_cambiada", objeto=negocio, datos={"cambios": {"carpeta_banco": [negocio.carpeta_banco, datos["carpeta_banco"]]}, "origen": "asistente"}, request=request)
            if pendiente and datos.get("guardada"):
                Negocio.objects.filter(pk=1).update(clave_recuperacion_pendiente=False)
                registrar("clave_recuperacion_guardada", objeto=negocio, request=request)
            registrar("asistente_cortes", datos={"entrega": bool(datos["carpeta_entrega"]), "respaldo": bool(datos["carpeta_respaldo"]), "carpeta_banco": bool(datos["carpeta_banco"])}, request=request)
        return redirect("asistente:usuario")
    contexto = {"texto_clave": sobre.clave_a_texto(clave_respaldo()) if pendiente else ""}
    respuesta = _paso(request, "asistente/cortes.html", formulario, 6, "Entrega y respaldo", **contexto)
    respuesta["Cache-Control"] = "no-store"
    return respuesta


def usuario(request):
    negocio = _exigir_autorizado(request)
    if negocio is None:
        return redirect("asistente:inicio")
    formulario = FormularioAsistenteUsuario(request.POST if request.method == "POST" else None)
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
            _guardar_estado(request, usuario=nuevo.pk, secreto=totp.generar_secreto())
            return redirect("asistente:codigo")
    return _paso(request, "asistente/paso.html", formulario, 7, "Primer usuario de Dirección")


def codigo(request):
    negocio = _exigir_autorizado(request)
    estado = _estado(request)
    if negocio is None or not estado.get("usuario") or not estado.get("secreto"):
        return redirect("asistente:inicio")
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
            return redirect("inicio")
        messages.error(request, "El código no coincide. Revisa la hora del teléfono.")
    contexto = {
        "formulario": formulario,
        "paso": 8,
        "total": TOTAL_PASOS,
        "titulo": "Autenticador del primer usuario",
        **qr.contexto(secreto, nuevo.usuario, negocio.nombre),
    }
    respuesta = render(request, "asistente/codigo.html", contexto)
    respuesta["Cache-Control"] = "no-store"
    return respuesta
