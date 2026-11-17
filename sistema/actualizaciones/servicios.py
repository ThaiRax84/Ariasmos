import hashlib
import os
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connections, transaction
from django.db.models import Max
from django.utils import timezone

from auditoria.servicios import registrar
from nucleo import sobre
from proyecto.version import actual as version_instalada

from . import aviso, canales, llaves
from .models import Configuracion, Descarga, LlaveDeUso, RechazoReciente, VersionPublicada

AVISO = "version.json"
FIRMA = "version.json.firma"
CAMBIO = "cambio-de-llave.json"
FIRMA_CAMBIO = "cambio-de-llave.json.firma"
CONTEXTO_CLAVE = "actualizaciones|clave_canal"
HORAS_ENTRE_RECHAZOS = 6
INTENTOS_POR_HORA = 3
MINUTOS_ENTRE_BUSQUEDAS_MANUALES = 10
PLAZO_AVISO = 60
PLAZO_INSTALADOR = 30 * 60
DIAS_AVISOS_DIRECCION = 7
TEXTOS = {
    "sin_conexion": "Sin conexión con el canal; se intentará más tarde.",
    "clave_rechazada": "El canal rechazó la clave de solo lectura.",
    "sin_publicacion": "El canal todavía no tiene versiones publicadas.",
    "respuesta_invalida": "El canal respondió algo inesperado.",
}

_buscado_al_arrancar = False
_hilo_descarga = None


class ErrorActualizacion(ValueError):
    pass


def configuracion():
    return Configuracion.objects.get_or_create(pk=1)[0]


def _clave_cifrado():
    return sobre.derivar(bytes(settings.CLAVE_SECRETOS), "actualizaciones")


def cifrar_clave(texto):
    return sobre.cifrar_texto(_clave_cifrado(), texto, CONTEXTO_CLAVE)


def leer_clave(config):
    if not config.clave_cifrada:
        return ""
    return sobre.descifrar_texto(_clave_cifrado(), config.clave_cifrada, CONTEXTO_CLAVE)


def carpeta():
    ruta = getattr(settings, "RUTA_ACTUALIZACIONES", "")
    if not ruta:
        raise ErrorActualizacion("La instalación no tiene carpeta de actualizaciones.")
    return Path(ruta)


def nombre_instalador(version):
    if not aviso.version_valida(version):
        raise ErrorActualizacion("Versión no válida.")
    return f"Ariasmos-{version}-instalador.exe"


def nombre_parcial(version):
    if not aviso.version_valida(version):
        raise ErrorActualizacion("Versión no válida.")
    return f"Ariasmos-{version}.parcial"


def instalada():
    texto = version_instalada()
    return texto if aviso.version_valida(texto) else None


def guardar_configuracion(activa, repositorio, clave_nueva, usuario=None, request=None, origen=""):
    from .canales.github import clave_valida, repositorio_valido

    repositorio = (repositorio or "").strip()
    clave_nueva = (clave_nueva or "").strip()
    if activa and not llaves.disponibles():
        raise ErrorActualizacion("Esta copia del programa no trae las llaves públicas de actualización: las actualizaciones no se pueden activar.")
    if repositorio and not repositorio_valido(repositorio):
        raise ErrorActualizacion("Escribe el repositorio del canal como propietario/nombre.")
    if clave_nueva and not clave_valida(clave_nueva):
        raise ErrorActualizacion("La clave no tiene el formato de una clave de GitHub.")
    with transaction.atomic():
        config = configuracion()
        cambia_repositorio = repositorio != config.repositorio
        if activa and not repositorio:
            raise ErrorActualizacion("Para activar las actualizaciones escribe el repositorio del canal.")
        if activa and not clave_nueva and (not config.clave_cifrada or cambia_repositorio):
            raise ErrorActualizacion("Para activar las actualizaciones escribe la clave de solo lectura del canal.")
        antes = {"activa": config.activa, "canal": config.canal, "repositorio": config.repositorio}
        config.activa = bool(activa)
        config.repositorio = repositorio
        if clave_nueva:
            config.clave_cifrada = cifrar_clave(clave_nueva)
        elif cambia_repositorio:
            config.clave_cifrada = ""
        if not config.activa:
            config.busqueda_pedida = False
        else:
            config.proxima_busqueda = None
        config.cambiada_en = timezone.now()
        config.cambiada_por = usuario if usuario is not None and getattr(usuario, "is_authenticated", False) else None
        config.save()
        despues = {"activa": config.activa, "canal": config.canal, "repositorio": config.repositorio}
        datos = {"antes": antes, "despues": despues, "clave_cambiada": bool(clave_nueva), "clave_guardada": config.tiene_clave}
        if origen:
            datos["origen"] = origen
        registrar("actualizaciones_configuradas", usuario=usuario, objeto=config, datos=datos, request=request)
    return config


def rechazar(motivo, datos=None, ahora=None):
    ahora = ahora or timezone.now()
    motivo = str(motivo)[:60]
    with transaction.atomic():
        previo = RechazoReciente.objects.filter(motivo=motivo).first()
        if previo is not None and previo.ultimo > ahora - timedelta(hours=HORAS_ENTRE_RECHAZOS):
            return False
        RechazoReciente.objects.update_or_create(motivo=motivo, defaults={"ultimo": ahora})
        registrar("actualizacion_rechazada", datos={"motivo": motivo, **(datos or {})})
    return True


def _proxima(ahora):
    from configuracion.models import Negocio

    negocio = Negocio.actual()
    zona = ZoneInfo(negocio.zona_horaria) if negocio else timezone.get_default_timezone()
    manana = timezone.localtime(ahora, zona).date() + timedelta(days=1)
    return datetime.combine(manana, time(0, 0), tzinfo=zona) + timedelta(minutes=secrets.randbelow(24 * 60))


def toca_buscar(config, ahora=None):
    ahora = ahora or timezone.now()
    if not config.activa:
        return False
    if config.busqueda_pedida or not _buscado_al_arrancar:
        return True
    return config.proxima_busqueda is None or config.proxima_busqueda <= ahora


def ultimo_contador_llave(recuperacion):
    return LlaveDeUso.objects.filter(recuperacion=recuperacion).aggregate(ultimo=Max("contador"))["ultimo"] or 0


def ultimo_contador_version(llave):
    return VersionPublicada.objects.filter(llave=llave).aggregate(ultimo=Max("contador"))["ultimo"] or 0


def _alinear_contadores(config):
    llave, recuperacion = llaves.de_uso(), llaves.recuperacion()
    de_version, de_llave = ultimo_contador_version(llave), ultimo_contador_llave(recuperacion)
    if (config.contador_version, config.contador_llave) != (de_version, de_llave):
        Configuracion.objects.filter(pk=1).update(contador_version=de_version, contador_llave=de_llave)
        config.contador_version, config.contador_llave = de_version, de_llave


def retirar_de_otra_llave():
    llave = llaves.de_uso()
    ajenas = Descarga.objects.exclude(version__llave=llave).filter(estado__in=(Descarga.PENDIENTE, Descarga.EN_CURSO, Descarga.LISTA)).select_related("version")
    versiones = sorted({descarga.version.version for descarga in ajenas})
    if not versiones:
        return []
    with transaction.atomic():
        Descarga.objects.filter(pk__in=[descarga.pk for descarga in ajenas]).update(estado=Descarga.FALLIDA, en_proceso=None, terminada_en=timezone.now(), motivo="La llave de uso de las actualizaciones cambió; la descarga se retiró.")
        registrar("actualizacion_rechazada", datos={"motivo": "llave_de_uso_distinta", "versiones": versiones[:20]})
    try:
        destino = carpeta()
    except ErrorActualizacion:
        return versiones
    vigentes = set(VersionPublicada.objects.filter(llave=llave, descargas__estado=Descarga.LISTA).values_list("version", flat=True))
    for version in versiones:
        if aviso.version_valida(version) and version not in vigentes:
            for nombre in (nombre_instalador(version), nombre_parcial(version)):
                try:
                    _quitar(destino / nombre)
                except OSError:
                    pass
    return versiones


def _leer_firmado(canal, recursos, nombre, firma):
    datos, firmado = recursos.get(nombre), recursos.get(firma)
    if datos is None or firmado is None:
        return None
    if datos.tamano > aviso.LIMITE_AVISO or firmado.tamano > aviso.LIMITE_AVISO:
        raise aviso.AvisoInvalido("tamano_aviso")
    return canal.leer(datos, aviso.LIMITE_AVISO, PLAZO_AVISO), canal.leer(firmado, aviso.LIMITE_AVISO, PLAZO_AVISO)


def _cambio_de_llave(canal, recursos, config):
    leido = _leer_firmado(canal, recursos, CAMBIO, FIRMA_CAMBIO)
    if leido is None:
        return None
    datos, firma = leido
    recuperacion = llaves.recuperacion()
    try:
        cambio = aviso.leer_cambio_de_llave(datos, firma, recuperacion)
    except aviso.AvisoInvalido as error:
        rechazar(f"cambio_de_llave_{error.motivo}")
        return None
    ultimo = ultimo_contador_llave(recuperacion)
    if cambio["contador"] <= ultimo:
        guardada = LlaveDeUso.objects.filter(contador=cambio["contador"], recuperacion=recuperacion).first()
        if guardada is None or bytes(guardada.aviso) != bytes(datos):
            rechazar("cambio_de_llave_contador", {"contador": cambio["contador"], "ultimo": ultimo})
        return None
    with transaction.atomic():
        LlaveDeUso.objects.create(llave=cambio["llave_uso"], recuperacion=recuperacion, contador=cambio["contador"], aviso=bytes(datos), firma=bytes(firma))
        Configuracion.objects.filter(pk=1).update(contador_llave=cambio["contador"])
        config.contador_llave = cambio["contador"]
        huella = hashlib.sha256(aviso.llave_de_texto(cambio["llave_uso"])).hexdigest()[:16]
        registrar("llave_de_uso_cambiada", datos={"contador": cambio["contador"], "huella_llave": huella})
    return cambio


def _version(canal, recursos, config):
    leido = _leer_firmado(canal, recursos, AVISO, FIRMA)
    if leido is None:
        rechazar("aviso_incompleto")
        return "El canal no trae el aviso de versión firmado."
    datos, firma = leido
    llave = llaves.de_uso()
    try:
        leida = aviso.leer_version(datos, firma, llave)
    except aviso.AvisoInvalido as error:
        rechazar(error.motivo)
        return "Se rechazó el aviso de versión."
    actual = instalada()
    if actual is None:
        rechazar("version_instalada_desconocida")
        return "No se conoce la versión instalada."
    ultimo = ultimo_contador_version(llave)
    if leida["contador"] <= ultimo:
        guardada = VersionPublicada.objects.filter(contador=leida["contador"], llave=llave).first()
        if guardada is not None and bytes(guardada.aviso) == bytes(datos):
            return f"Sin cambios: la última versión publicada es {leida['version']}."
        rechazar("contador", {"contador": leida["contador"], "ultimo": ultimo, "version": leida["version"]})
        return "Se rechazó el aviso de versión."
    if not aviso.mayor(leida["version"], actual):
        if leida["version"] == actual:
            return f"Al día: la versión instalada es la última ({actual})."
        rechazar("version_anterior", {"version": leida["version"], "instalada": actual})
        return "Se rechazó el aviso de versión."
    with transaction.atomic():
        VersionPublicada.objects.create(version=leida["version"], contador=leida["contador"], aviso=bytes(datos), firma=bytes(firma), llave=llave, datos=leida)
        Configuracion.objects.filter(pk=1).update(contador_version=leida["contador"])
        config.contador_version = leida["contador"]
        registrar("actualizacion_aceptada", datos={"version": leida["version"], "contador": leida["contador"], "minimo": leida["minimo"], "sha256": leida["instalador"]["sha256"]})
    return f"Hay una versión nueva: {leida['version']}."


def _canal(config):
    return canales.obtener(config.canal, config.repositorio, leer_clave(config))


def _texto_error(error):
    if isinstance(error, canales.SinConexion):
        return TEXTOS["sin_conexion"]
    if isinstance(error, canales.ClaveRechazada):
        return TEXTOS["clave_rechazada"]
    if isinstance(error, canales.SinPublicacion):
        return TEXTOS["sin_publicacion"]
    return TEXTOS["respuesta_invalida"]


def buscar(ahora=None):
    global _buscado_al_arrancar
    ahora = ahora or timezone.now()
    config = configuracion()
    _buscado_al_arrancar = True
    Configuracion.objects.filter(pk=1).update(ultima_busqueda=ahora, proxima_busqueda=_proxima(ahora), busqueda_pedida=False)
    if not config.activa:
        return "Actualizaciones apagadas."
    if not llaves.disponibles():
        texto = "Esta copia del programa no trae llaves de actualización."
        Configuracion.objects.filter(pk=1).update(ultimo_resultado=texto)
        return texto
    try:
        canal = _canal(config)
        recursos = canal.publicacion()
        _cambio_de_llave(canal, recursos, config)
        retirar_de_otra_llave()
        _alinear_contadores(config)
        texto = _version(canal, recursos, config)
    except canales.ErrorCanal as error:
        texto = _texto_error(error)
        if isinstance(error, canales.RespuestaInvalida):
            rechazar("respuesta_invalida")
    except aviso.AvisoInvalido as error:
        rechazar(error.motivo)
        texto = "Se rechazó el aviso de versión."
    except sobre.ErrorSobre:
        texto = "No se pudo leer la clave guardada del canal; vuelve a escribirla."
    Configuracion.objects.filter(pk=1).update(ultimo_resultado=texto[:200])
    return texto


def pedir_busqueda(usuario, request=None, ahora=None):
    ahora = ahora or timezone.now()
    with transaction.atomic():
        config = configuracion()
        if not config.activa:
            raise ErrorActualizacion("Las actualizaciones están apagadas.")
        if config.busqueda_pedida_en and config.busqueda_pedida_en > ahora - timedelta(minutes=MINUTOS_ENTRE_BUSQUEDAS_MANUALES):
            raise ErrorActualizacion(f"Ya se pidió una búsqueda hace menos de {MINUTOS_ENTRE_BUSQUEDAS_MANUALES} minutos.")
        Configuracion.objects.filter(pk=1).update(busqueda_pedida=True, busqueda_pedida_en=ahora)
        registrar("actualizacion_busqueda_pedida", usuario=usuario, request=request)


def vigente():
    actual = instalada()
    if actual is None:
        return None
    llave = llaves.de_uso()
    if llave is None:
        return None
    version = VersionPublicada.objects.filter(llave=llave).order_by("-contador").first()
    if version is not None and aviso.version_valida(version.version) and aviso.mayor(version.version, actual):
        return version
    return None


def requiere_paso_previo(version):
    actual = instalada()
    return actual is None or aviso.mayor(version.minimo, actual)


def archivo_listo(descarga):
    if descarga is None or descarga.estado != Descarga.LISTA:
        return False
    try:
        ruta = carpeta() / nombre_instalador(descarga.version.version)
        informacion = os.lstat(ruta)
    except (OSError, ErrorActualizacion):
        return False
    return stat.S_ISREG(informacion.st_mode) and informacion.st_size == descarga.version.datos["instalador"]["tamano"]


def pedir_descarga(usuario, request=None, ahora=None):
    ahora = ahora or timezone.now()
    with transaction.atomic():
        config = configuracion()
        if not config.activa:
            raise ErrorActualizacion("Las actualizaciones están apagadas.")
        version = vigente()
        if version is None:
            raise ErrorActualizacion("No hay una versión nueva que descargar.")
        if requiere_paso_previo(version):
            raise ErrorActualizacion(f"Antes hay que instalar la versión {version.minimo}.")
        if Descarga.objects.filter(en_proceso=True).exists():
            raise ErrorActualizacion("Ya hay una descarga en curso.")
        if archivo_listo(Descarga.objects.filter(version=version, estado=Descarga.LISTA).first()):
            raise ErrorActualizacion("Esta versión ya está descargada y lista para instalar.")
        if Descarga.objects.filter(pedida_en__gte=ahora - timedelta(hours=1)).count() >= INTENTOS_POR_HORA:
            raise ErrorActualizacion("Ya se intentó descargar tres veces en la última hora; inténtalo más tarde.")
        descarga = Descarga.objects.create(version=version, pedida_por=usuario, estado=Descarga.PENDIENTE, en_proceso=True)
        registrar("actualizacion_descarga_pedida", usuario=usuario, objeto=descarga, datos={"version": version.version}, request=request)
    return descarga


def _abrir_parcial(ruta):
    banderas = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    return os.open(ruta, banderas, 0o600)


def _preparar_carpeta():
    destino = carpeta()
    if destino.is_symlink():
        raise ErrorActualizacion("La carpeta de actualizaciones es un enlace.")
    destino.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not destino.is_dir() or destino.is_symlink():
        raise ErrorActualizacion("La carpeta de actualizaciones no es una carpeta.")
    return destino


def _quitar(ruta):
    try:
        os.unlink(ruta)
    except FileNotFoundError:
        pass


def _terminar(descarga, estado, motivo="", solo_en_curso=False, **extra):
    consulta = Descarga.objects.filter(pk=descarga.pk)
    if solo_en_curso:
        consulta = consulta.filter(estado=Descarga.EN_CURSO)
    consulta.update(estado=estado, en_proceso=None, terminada_en=timezone.now(), motivo=motivo[:200], **extra)


def descargar_pendiente():
    descarga = Descarga.objects.filter(estado=Descarga.PENDIENTE).select_related("version", "pedida_por").order_by("pedida_en", "id").first()
    if descarga is None:
        return None
    if Descarga.objects.filter(pk=descarga.pk, estado=Descarga.PENDIENTE).update(estado=Descarga.EN_CURSO, iniciada_en=timezone.now()) != 1:
        return None
    try:
        return _descargar(descarga)
    except BaseException:
        _terminar(descarga, Descarga.FALLIDA, "No se pudo completar la descarga.", solo_en_curso=True)
        raise


def _descargar(descarga):
    version = descarga.version
    esperado = version.datos["instalador"]
    config = configuracion()
    if not config.activa:
        _terminar(descarga, Descarga.FALLIDA, "Las actualizaciones están apagadas.")
        return "Descarga cancelada: actualizaciones apagadas."
    try:
        aviso.leer_version(bytes(version.aviso), bytes(version.firma), llaves.de_uso())
    except aviso.AvisoInvalido as error:
        rechazar(f"descarga_{error.motivo}", {"version": version.version})
        _terminar(descarga, Descarga.FALLIDA, "El aviso guardado ya no es válido.")
        return "Descarga rechazada: el aviso guardado ya no es válido."
    destino = _preparar_carpeta()
    parcial = destino / nombre_parcial(version.version)
    final = destino / nombre_instalador(version.version)
    _quitar(parcial)
    huella = hashlib.sha256()
    escrito = [0]
    try:
        canal = _canal(config)
        recurso = canal.publicacion().get(esperado["nombre"])
        if recurso is None:
            raise canales.RespuestaInvalida("el canal no trae el instalador")
        if recurso.tamano != esperado["tamano"]:
            raise canales.Excedido("tamaño distinto al del aviso")
        descriptor = _abrir_parcial(parcial)
        try:
            def escribir(bloque):
                escrito[0] += len(bloque)
                if escrito[0] > esperado["tamano"]:
                    raise canales.Excedido("más grande que el aviso")
                huella.update(bloque)
                vista = memoryview(bloque)
                while vista:
                    hechos = os.write(descriptor, vista)
                    vista = vista[hechos:]

            canal.descargar(recurso, escribir, esperado["tamano"], PLAZO_INSTALADOR)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except canales.Excedido:
        _quitar(parcial)
        rechazar("tamano", {"version": version.version})
        _terminar(descarga, Descarga.FALLIDA, "El instalador no coincide con el tamaño del aviso firmado; se borró.")
        return "Descarga rechazada por tamaño."
    except (canales.ErrorCanal, sobre.ErrorSobre, OSError) as error:
        _quitar(parcial)
        _terminar(descarga, Descarga.FALLIDA, _texto_error(error) if isinstance(error, canales.ErrorCanal) else "No se pudo completar la descarga.")
        return "Descarga fallida; se puede volver a pedir."
    except BaseException:
        _quitar(parcial)
        raise
    calculada = huella.hexdigest()
    if escrito[0] != esperado["tamano"] or calculada != esperado["sha256"]:
        _quitar(parcial)
        motivo = "tamano" if escrito[0] != esperado["tamano"] else "huella"
        rechazar(motivo, {"version": version.version, "sha256_recibido": calculada})
        _terminar(descarga, Descarga.FALLIDA, "El instalador no coincide con la huella del aviso firmado; se borró." if motivo == "huella" else "El instalador no coincide con el tamaño del aviso firmado; se borró.")
        return "Descarga rechazada por huella."
    try:
        aviso.leer_version(bytes(version.aviso), bytes(version.firma), llaves.de_uso())
    except aviso.AvisoInvalido as error:
        _quitar(parcial)
        rechazar(f"descarga_{error.motivo}", {"version": version.version})
        _terminar(descarga, Descarga.FALLIDA, "El aviso guardado ya no es válido.")
        return "Descarga rechazada: el aviso guardado ya no es válido."
    os.replace(parcial, final)
    _terminar(descarga, Descarga.LISTA, archivo=final.name, sha256=calculada)
    registrar(
        "actualizacion_descargada",
        objeto=descarga,
        datos={"version": version.version, "sha256": calculada, "tamano": escrito[0], "pedida_por": descarga.pedida_por.usuario if descarga.pedida_por else ""},
    )
    return f"Versión {version.version} descargada y lista para instalar."


def _descargar_en_hilo():
    try:
        descargar_pendiente()
    except Exception as error:
        try:
            registrar("tarea_fallida", datos={"tarea": "descarga_actualizacion", "error": type(error).__name__})
        except Exception:
            pass
    finally:
        connections.close_all()


def lanzar_descarga():
    global _hilo_descarga
    if _hilo_descarga is not None and _hilo_descarga.is_alive():
        return "Descarga en curso."
    if not Descarga.objects.filter(estado=Descarga.PENDIENTE).exists():
        return None
    _hilo_descarga = threading.Thread(target=_descargar_en_hilo, name="descarga-actualizacion", daemon=True)
    _hilo_descarga.start()
    return "Descarga iniciada."


def ciclo(ahora=None, en_hilo=False):
    ahora = ahora or timezone.now()
    partes = []
    config = configuracion()
    if not config.activa:
        Descarga.objects.filter(estado=Descarga.PENDIENTE).update(estado=Descarga.FALLIDA, en_proceso=None, terminada_en=ahora, motivo="Las actualizaciones están apagadas.")
        return "actualizaciones apagadas"
    Descarga.objects.filter(estado=Descarga.EN_CURSO, iniciada_en__lt=ahora - timedelta(seconds=PLAZO_INSTALADOR + 600)).update(
        estado=Descarga.FALLIDA, en_proceso=None, terminada_en=ahora, motivo="La descarga se interrumpió."
    )
    if toca_buscar(config, ahora):
        partes.append(buscar(ahora))
    resultado = lanzar_descarga() if en_hilo else descargar_pendiente()
    if resultado:
        partes.append(resultado)
    return " ".join(partes) or "nada que hacer"


def turnos_abiertos():
    from caja.models import Turno

    return Turno.objects.filter(estado=Turno.ABIERTO).count()


def aviso_para(usuario):
    config = Configuracion.objects.filter(pk=1).first()
    if config is None or not config.activa:
        return None
    contexto = {}
    version = vigente()
    if version is not None:
        descarga = Descarga.objects.filter(version=version).order_by("-pedida_en", "-id").first()
        lista = archivo_listo(descarga)
        intentos = Descarga.objects.filter(pedida_en__gte=timezone.now() - timedelta(hours=1)).count()
        en_curso = Descarga.objects.filter(en_proceso=True).exists()
        paso_previo = requiere_paso_previo(version)
        contexto.update(
            version=version,
            cambios=version.cambios,
            paso_previo=paso_previo,
            minimo=version.minimo,
            lista=lista,
            en_curso=en_curso,
            fallida=descarga is not None and descarga.estado == Descarga.FALLIDA,
            puede_descargar=not paso_previo and not lista and not en_curso and intentos < INTENTOS_POR_HORA,
            agotado=intentos >= INTENTOS_POR_HORA and not lista and not en_curso,
            turnos_abiertos=turnos_abiertos() if lista else 0,
        )
    if usuario.tiene_permiso("administrar_configuracion"):
        from auditoria.models import Evento

        desde = timezone.now() - timedelta(days=DIAS_AVISOS_DIRECCION)
        contexto["eventos"] = list(
            Evento.objects.filter(accion__in=("llave_de_uso_cambiada", "actualizacion_descargada"), momento__gte=desde).order_by("-numero")[:10]
        )
        contexto["fallidas"] = list(Descarga.objects.filter(estado=Descarga.FALLIDA, terminada_en__gte=desde).select_related("version", "pedida_por")[:5])
        contexto["puede_buscar"] = True
    if not contexto.get("version") and not contexto.get("eventos") and not contexto.get("fallidas"):
        return None
    return contexto


def lanzar_instalador(ruta):
    if sys.platform != "win32":
        raise ErrorActualizacion("El instalador solo se ejecuta en Windows.")
    banderas = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(ruta)], close_fds=True, creationflags=banderas, cwd=str(Path(ruta).parent))


def limpiar_verificadas(horas=1):
    limite = timezone.now().timestamp() - horas * 3600
    try:
        candidatas = list(carpeta().glob("verificado-*"))
    except (OSError, ErrorActualizacion):
        return
    for ruta in candidatas:
        try:
            if ruta.is_dir() and not ruta.is_symlink() and ruta.stat().st_mtime < limite:
                shutil.rmtree(ruta, ignore_errors=True)
        except OSError:
            continue


def preparar_instalacion():
    actual = instalada()
    if actual is None:
        raise ErrorActualizacion("No se conoce la versión instalada.")
    llave = llaves.de_uso()
    if llave is None:
        raise ErrorActualizacion("Esta copia del programa no trae llaves de actualización.")
    descarga = Descarga.objects.filter(estado=Descarga.LISTA, version__llave=llave).select_related("version").order_by("-version__contador", "-id").first()
    if descarga is None:
        raise ErrorActualizacion("No hay una actualización descargada.")
    version = descarga.version
    try:
        leida = aviso.leer_version(bytes(version.aviso), bytes(version.firma), llave)
    except aviso.AvisoInvalido as error:
        raise ErrorActualizacion(f"La firma del aviso de versión no es válida ({error.motivo}).")
    if leida["version"] != version.version or leida["contador"] != version.contador:
        raise ErrorActualizacion("El aviso guardado no corresponde a la descarga.")
    if not aviso.mayor(leida["version"], actual):
        raise ErrorActualizacion(f"La versión descargada ({leida['version']}) no es mayor que la instalada ({actual}).")
    if aviso.mayor(leida["minimo"], actual):
        raise ErrorActualizacion(f"Antes hay que instalar la versión {leida['minimo']}.")
    origen = carpeta() / nombre_instalador(leida["version"])
    try:
        informacion = os.lstat(origen)
    except OSError:
        raise ErrorActualizacion("No se encontró el instalador descargado.")
    if not stat.S_ISREG(informacion.st_mode):
        raise ErrorActualizacion("El instalador descargado no es un archivo normal.")
    limpiar_verificadas()
    privada = Path(tempfile.mkdtemp(prefix="verificado-", dir=str(carpeta())))
    copia = privada / nombre_instalador(leida["version"])
    huella = hashlib.sha256()
    total = 0
    try:
        with open(origen, "rb") as entrada, open(copia, "xb") as salida:
            while True:
                bloque = entrada.read(1024 * 1024)
                if not bloque:
                    break
                total += len(bloque)
                if total > leida["instalador"]["tamano"]:
                    break
                huella.update(bloque)
                salida.write(bloque)
    except OSError:
        shutil.rmtree(privada, ignore_errors=True)
        raise ErrorActualizacion("No se pudo leer el instalador descargado.")
    if total != leida["instalador"]["tamano"] or huella.hexdigest() != leida["instalador"]["sha256"]:
        shutil.rmtree(privada, ignore_errors=True)
        registrar("actualizacion_rechazada", datos={"motivo": "huella_al_instalar", "version": leida["version"]})
        raise ErrorActualizacion("La huella del instalador no coincide con el aviso firmado. No se ejecutó nada.")
    return {"version": leida["version"], "copia": copia, "carpeta": privada, "turnos_abiertos": turnos_abiertos(), "sha256": leida["instalador"]["sha256"]}


def instalar(preparada, ejecutar=None):
    (ejecutar or lanzar_instalador)(preparada["copia"])
    registrar("actualizacion_instalacion_iniciada", datos={"version": preparada["version"], "sha256": preparada["sha256"]})


def descartar_preparada(preparada):
    shutil.rmtree(preparada["carpeta"], ignore_errors=True)
