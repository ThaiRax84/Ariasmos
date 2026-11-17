import csv
import hashlib
import json
import os
import secrets
from collections import defaultdict
from io import BytesIO, StringIO

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from openpyxl import Workbook

from auditoria.servicios import diferencias, registrar
from banco import lectura
from cobros import libro
from cobros.models import Cargo, ConceptoCobro, Pago
from configuracion.models import hoy_negocio, parametro, vocabulario
from nucleo import telefono
from nucleo.exportar import neutralizar
from nucleo.matricula import normalizar as normalizar_matricula

from . import contactos
from .models import Agrupacion, CampoContacto, Familia, LotePadron, Titular
from .servicios import crear_titular, foto_titular, guardar_contacto

SINONIMOS = {
    "matricula": ["matricula", "numero de cliente", "no de cliente", "clave", "folio", "id"],
    "nombre": ["nombre", "nombres", "nombre s"],
    "apellidos": ["apellidos", "apellido"],
    "nombre_completo": ["nombre completo", "alumno", "cliente", "titular", "nombre del alumno", "nombre del cliente"],
    "agrupacion": ["grupo", "grado", "agrupacion", "salon", "clase"],
    "responsable": ["responsable", "tutor", "padre o tutor", "contacto", "padre", "madre"],
    "telefono": ["telefono", "celular", "tel", "movil", "whatsapp"],
    "correo": ["correo", "email", "e mail", "correo electronico"],
    "saldo_total": ["saldo", "adeudo", "saldo total", "debe"],
}
PAPELES = list(SINONIMOS)
CAMPOS_CAMBIO = ("nombre", "apellidos", "agrupacion", "responsable", "telefono", "correo")
SUBCARPETA = "hojas"


class ErrorPadron(ValueError):
    pass


def sinonimos(voc=None):
    voc = voc or vocabulario()
    propios = {
        "matricula": [voc["matricula"], voc["matriculas"]],
        "nombre_completo": [voc["titular"], voc["titulares"], f"nombre del {voc['titular']}", f"nombre de {voc['titular']}"],
        "agrupacion": [voc["agrupacion"], voc["agrupaciones"]],
        "responsable": [voc["familia"]],
    }
    resultado = {}
    for papel, lista in SINONIMOS.items():
        extra = [lectura.normal(t) for t in propios.get(papel, []) if lectura.normal(t)]
        resultado[papel] = list(dict.fromkeys(extra + lista))
    return resultado


def proponer(filas):
    lista = sinonimos()
    encabezado = lectura.detectar_encabezado(filas, lista)
    propuesta = lectura.proponer(filas, encabezado, lista)
    titulos = [lectura.normal(c) for c in filas[encabezado]]
    for concepto in ConceptoCobro.objects.filter(activo=True):
        nombre = lectura.normal(concepto.nombre)
        for indice, titulo in enumerate(titulos):
            if indice not in propuesta.values() and nombre and (titulo == nombre or titulo == f"saldo {nombre}" or titulo == f"adeudo {nombre}"):
                propuesta[f"saldo_{concepto.pk}"] = indice
                if propuesta.get("saldo_total") == indice:
                    propuesta.pop("saldo_total")
    return encabezado, propuesta


def _partir(completo):
    palabras = completo.split()
    if len(palabras) < 2:
        return completo, ""
    if len(palabras) == 2:
        return palabras[0], palabras[1]
    return " ".join(palabras[:-2]), " ".join(palabras[-2:])


def llave(nombre, apellidos, tel):
    return f"{lectura.normal(nombre + ' ' + apellidos)}|{tel or ''}"


def llaves_existentes():
    campo = CampoContacto.objects.filter(tipo=CampoContacto.TELEFONO, principal=True).first() or CampoContacto.objects.filter(tipo=CampoContacto.TELEFONO).first()
    llaves = defaultdict(set)
    for titular in Titular.objects.exclude(estado=Titular.RECHAZADO).select_related("familia"):
        contacto = contactos.principal(titular)
        tel = contacto.valor(campo) if contacto is not None and campo is not None else ""
        llaves[lectura.normal(f"{titular.nombre} {titular.apellidos}")].add(tel or "")
    return llaves


def ya_existe(existentes, nombre, apellidos, tel):
    telefonos = existentes.get(lectura.normal(f"{nombre} {apellidos}"))
    return telefonos is not None and (not tel or tel in telefonos or "" in telefonos)


def _campo_telefono():
    return CampoContacto.objects.filter(tipo=CampoContacto.TELEFONO, activo=True).order_by("-principal", "orden").first()


def _campo_correo():
    return CampoContacto.objects.filter(tipo=CampoContacto.CORREO, activo=True).order_by("-principal", "orden").first()


def estado_actual(titular):
    contacto = contactos.principal(titular)
    campo_tel, campo_correo = _campo_telefono(), _campo_correo()
    return {
        "nombre": titular.nombre,
        "apellidos": titular.apellidos,
        "agrupacion": str(titular.agrupacion) if titular.agrupacion_id else "",
        "responsable": contacto.nombre if contacto is not None else "",
        "telefono": (contacto.valor(campo_tel) if contacto is not None and campo_tel is not None else "") or "",
        "correo": (contacto.valor(campo_correo) if contacto is not None and campo_correo is not None else "") or "",
    }


def _cambios(titular, propuesta):
    actual = estado_actual(titular)
    if propuesta["nombre"] and " ".join(f"{propuesta['nombre']} {propuesta['apellidos']}".split()) == " ".join(f"{actual['nombre']} {actual['apellidos']}".split()):
        propuesta = dict(propuesta, nombre="", apellidos="")
    return {campo: [actual[campo], valor] for campo, valor in propuesta.items() if valor and valor != actual[campo]}


def analizar(filas, encabezado, columnas, concepto_saldo_total=None):
    columnas = {papel: int(indice) for papel, indice in columnas.items() if indice not in (None, "")}
    voc = vocabulario()
    exigir_apellidos = bool(parametro("apellidos_obligatorios"))
    if not ({"nombre"} <= set(columnas) or "nombre_completo" in columnas or "matricula" in columnas):
        raise ErrorPadron(f"Indica la columna de nombre (y la de apellidos), la de nombre completo o la de {voc['matricula_min']}.")
    if exigir_apellidos and "nombre" in columnas and "apellidos" not in columnas and "nombre_completo" not in columnas and "matricula" not in columnas:
        raise ErrorPadron("Indica las columnas de nombre y apellidos, o la de nombre completo.")
    if "saldo_total" in columnas and concepto_saldo_total is None:
        raise ErrorPadron("Elige el concepto al que se carga el saldo total.")
    obligatorio_tel = CampoContacto.objects.filter(tipo=CampoContacto.TELEFONO, obligatorio=True, activo=True).exists()
    prefijo, digitos = str(parametro("prefijo_pais_telefono")), parametro("digitos_telefono_nacional")
    existentes = llaves_existentes()
    vistos = set()
    vistas_matriculas = set()
    resultado = []
    for numero, fila in enumerate(filas[encabezado + 1:], start=encabezado + 2):
        def valor(papel, maximo=150):
            indice = columnas.get(papel)
            return " ".join((fila[indice] if indice is not None and indice < len(fila) else "").split())[:maximo]

        if not any(c.strip() for c in fila):
            continue
        errores = []
        avisos = []
        nombre, apellidos = valor("nombre", 100), valor("apellidos", 150)
        if "nombre_completo" in columnas and not (nombre and apellidos):
            completo = valor("nombre_completo", 250)
            if completo:
                nombre, apellidos = _partir(completo) if exigir_apellidos or len(completo.split()) > 1 else (completo, "")
                nombre, apellidos = nombre[:100], apellidos[:150]
        clave_matricula = normalizar_matricula(valor("matricula", 40))
        titular_existente = None
        if clave_matricula:
            titular_existente = Titular.objects.exclude(estado=Titular.RECHAZADO).filter(matricula=clave_matricula).first()
            if titular_existente is None:
                errores.append(f"{voc['matricula_min']} {clave_matricula} no existe")
            elif clave_matricula in vistas_matriculas:
                errores.append(f"{voc['matricula_min']} {clave_matricula} repetida en el archivo")
            vistas_matriculas.add(clave_matricula)
        else:
            if not nombre:
                errores.append("falta el nombre")
            if not apellidos and exigir_apellidos:
                errores.append("faltan los apellidos")
        tel = ""
        crudo = valor("telefono", 40)
        if crudo:
            try:
                tel = telefono.normalizar(crudo, prefijo, digitos)
            except telefono.TelefonoInvalido:
                errores.append(f"teléfono no válido ({crudo})")
        elif obligatorio_tel:
            errores.append("falta el teléfono, que es obligatorio")
        correo = valor("correo", 150).lower()
        if correo:
            try:
                validate_email(correo)
            except ValidationError:
                errores.append(f"correo no válido ({correo})")
        saldos = []
        papeles_saldo = [(p, int(p.split("_")[1])) for p in columnas if p.startswith("saldo_") and p != "saldo_total"]
        if "saldo_total" in columnas:
            papeles_saldo.append(("saldo_total", concepto_saldo_total))
        for papel, concepto in papeles_saldo:
            texto = valor(papel, 40)
            if not texto:
                continue
            if clave_matricula:
                avisos.append("los saldos no cambian desde la hoja: se ignoraron")
                break
            importe = lectura.importe(texto)
            if importe is None or abs(importe) >= 10 ** 11:
                errores.append(f"saldo no válido ({texto})")
            elif importe:
                saldos.append([concepto, importe])
        if clave_matricula:
            cambios = {}
            if titular_existente is not None and not errores:
                propuesta = {"nombre": nombre, "apellidos": apellidos if nombre else "", "agrupacion": valor("agrupacion", 100), "responsable": valor("responsable", 150), "telefono": tel, "correo": correo}
                cambios = _cambios(titular_existente, propuesta)
            resultado.append(
                {
                    "numero": numero, "tipo": "cambio", "matricula": clave_matricula, "titular": titular_existente.pk if titular_existente else None,
                    "nombre_actual": titular_existente.nombre_completo if titular_existente else "", "cambios": cambios,
                    "errores": errores, "avisos": avisos, "duplicado": "" if cambios or errores else "sin cambios",
                    "nombre": nombre, "apellidos": apellidos, "agrupacion": valor("agrupacion", 100), "responsable": valor("responsable", 150),
                    "telefono": tel, "correo": correo, "saldos": [], "familia": None,
                }
            )
            continue
        clave = llave(nombre, apellidos, tel)
        duplicado = ""
        if not errores:
            if ya_existe(existentes, nombre, apellidos, tel):
                duplicado = f"ya existe en {voc['padron_min']}"
            elif clave in vistos:
                duplicado = "repetido en el archivo"
            vistos.add(clave)
        resultado.append(
            {
                "numero": numero, "tipo": "alta", "nombre": nombre, "apellidos": apellidos, "agrupacion": valor("agrupacion", 100),
                "responsable": valor("responsable", 150), "telefono": tel, "correo": correo, "saldos": saldos,
                "errores": errores, "avisos": avisos, "duplicado": duplicado, "familia": None,
            }
        )
    grupos = defaultdict(list)
    for indice, fila in enumerate(resultado):
        if fila["tipo"] == "alta" and not fila["errores"] and not fila["duplicado"] and fila["responsable"] and fila["telefono"]:
            grupos[(lectura.normal(fila["responsable"]), fila["telefono"])].append(indice)
    familias = []
    for (_, _), indices in grupos.items():
        if len(indices) >= 2:
            for i in indices:
                resultado[i]["familia"] = len(familias)
            familias.append({"responsable": resultado[indices[0]]["responsable"], "telefono": resultado[indices[0]]["telefono"], "miembros": [resultado[i]["nombre"] + " " + resultado[i]["apellidos"] for i in indices]})
    return {"filas": resultado, "familias": familias}


def resumen(analisis):
    validas = [f for f in analisis["filas"] if not f["errores"] and not f["duplicado"]]
    return {
        "altas": sum(1 for f in validas if f.get("tipo", "alta") == "alta"),
        "cambios": sum(1 for f in validas if f.get("tipo") == "cambio"),
        "nombres": sum(1 for f in validas if f.get("tipo") == "cambio" and ({"nombre", "apellidos"} & set(f["cambios"]))),
        "errores": sum(1 for f in analisis["filas"] if f["errores"]),
        "omitidas": sum(1 for f in analisis["filas"] if f["duplicado"]),
    }


def carpeta_hojas():
    from caja import comprobantes

    ruta = comprobantes.carpeta() / SUBCARPETA
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def _ruta_hoja(nombre):
    if not (len(nombre) == 37 and nombre.endswith(".json") and all(c in "0123456789abcdef" for c in nombre[:32])):
        raise ErrorPadron("Nombre de archivo de hoja no válido.")
    return carpeta_hojas() / nombre


def guardar_hoja(analisis):
    contenido = json.dumps(analisis, ensure_ascii=False, sort_keys=True).encode("utf-8")
    nombre = f"{secrets.token_hex(16)}.json"
    descriptor = os.open(_ruta_hoja(nombre), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(descriptor, "wb") as salida:
        salida.write(contenido)
        salida.flush()
        os.fsync(salida.fileno())
    return nombre, hashlib.sha256(contenido).hexdigest()


def leer_hoja(nombre, huella):
    try:
        contenido = _ruta_hoja(nombre).read_bytes()
    except OSError:
        raise ErrorPadron("La hoja de esta solicitud ya no está disponible.")
    if hashlib.sha256(contenido).hexdigest() != huella:
        raise ErrorPadron("La hoja de esta solicitud fue alterada.")
    return json.loads(contenido.decode("utf-8"))


def borrar_hoja(nombre):
    try:
        os.unlink(_ruta_hoja(nombre))
    except (OSError, ErrorPadron):
        pass


def _valores(tel, correo):
    valores = {}
    campo_tel, campo_correo = _campo_telefono(), _campo_correo()
    if tel and campo_tel:
        valores[str(campo_tel.pk)] = tel
    if correo and campo_correo:
        valores[str(campo_correo.pk)] = correo
    return valores


def _aplicar_cambio(fila, lote, usuario, autorizador, solicitud, request):
    titular = Titular.objects.select_for_update().filter(pk=fila["titular"], matricula=fila["matricula"]).exclude(estado=Titular.RECHAZADO).first()
    if titular is None:
        return f"renglón {fila['numero']}: el registro ya no existe"
    actual = estado_actual(titular)
    distintos = [campo for campo, (antes, _) in fila["cambios"].items() if campo in CAMPOS_CAMBIO and actual[campo] != antes]
    if distintos:
        return f"renglón {fila['numero']}: cambió desde que se subió la hoja ({', '.join(distintos)})"
    cambios = {campo: valores for campo, valores in fila["cambios"].items() if campo in CAMPOS_CAMBIO}
    antes = foto_titular(titular)
    campos = []
    if "nombre" in cambios or "apellidos" in cambios:
        titular.nombre = cambios.get("nombre", [None, titular.nombre])[1][:100]
        titular.apellidos = cambios.get("apellidos", [None, titular.apellidos])[1][:150]
        campos += ["nombre", "apellidos"]
    if "agrupacion" in cambios:
        titular.agrupacion = Agrupacion.objects.get_or_create(nombre=cambios["agrupacion"][1][:100])[0]
        campos.append("agrupacion")
    if campos:
        titular.save(update_fields=campos + ["actualizado"])
    if {"responsable", "telefono", "correo"} & set(cambios):
        contacto = contactos.principal(titular)
        tel = cambios.get("telefono", [None, actual["telefono"]])[1]
        correo = cambios.get("correo", [None, actual["correo"]])[1]
        valores = dict(contacto.valores) if contacto is not None else {}
        valores.update(_valores(tel, correo))
        nombre = cambios.get("responsable", [None, actual["responsable"]])[1] or titular.nombre_completo
        datos = {"nombre": nombre[:150], "relacion": contacto.relacion if contacto is not None else None, "valores": valores}
        if contacto is not None and contacto.familia_id:
            guardar_contacto(usuario, None, datos, contacto=contacto, request=request, familia=contacto.familia)
        else:
            guardar_contacto(usuario, titular, datos, contacto=contacto, principal=True, request=request)
    titular.refresh_from_db()
    registrar(
        "titular_actualizado_por_hoja", usuario=usuario, objeto=titular,
        datos={"lote": lote.pk, "renglon": fila["numero"], "solicitud": solicitud.pk if solicitud else None, "solicito": str(usuario), "aprobo": str(autorizador or usuario), "cambios": {**diferencias(antes, foto_titular(titular)), **{c: v for c, v in cambios.items() if c in ("responsable", "telefono", "correo")}}},
        request=request,
    )
    return None


def aplicar(analisis, aceptadas, usuario, nombre_archivo, sha256, request=None, autorizador=None, solicitud=None):
    hoy = hoy_negocio()
    aceptadas = set(aceptadas)
    validas = [f for f in analisis["filas"] if not f["errores"] and not f["duplicado"]]
    filas = [f for f in validas if f.get("tipo", "alta") == "alta"]
    actualizar = [f for f in validas if f.get("tipo") == "cambio"]
    with transaction.atomic():
        lote = LotePadron.objects.create(
            nombre_archivo=nombre_archivo, sha256=sha256, creado_por=usuario, filas=len(analisis["filas"]),
            duplicados=sum(1 for f in analisis["filas"] if f["duplicado"]), con_error=sum(1 for f in analisis["filas"] if f["errores"]),
            autorizado_por=autorizador if autorizador is not None and autorizador != usuario else None, solicitud=solicitud,
        )
        saltados = []
        actualizados = []
        for fila in actualizar:
            motivo = _aplicar_cambio(fila, lote, usuario, autorizador, solicitud, request)
            if motivo is None:
                actualizados.append(fila["titular"])
            else:
                saltados.append(motivo)
        familias = {}
        creados = []
        cargos = a_favor = 0
        for fila in filas:
            agrupacion = Agrupacion.objects.get_or_create(nombre=fila["agrupacion"])[0] if fila["agrupacion"] else None
            familia = None
            indice = fila["familia"]
            if indice is not None and indice in aceptadas:
                familia = familias.get(indice)
                if familia is None:
                    datos_familia = analisis["familias"][indice]
                    familia = Familia.objects.create(nombre=datos_familia["responsable"][:100])
                    registrar("familia_creada", usuario=usuario, objeto=familia, datos={"nombre": familia.nombre, "lote": lote.pk}, request=request)
                    guardar_contacto(usuario, None, {"nombre": datos_familia["responsable"], "valores": _valores(fila["telefono"], fila["correo"])}, principal=True, request=request, familia=familia)
                    familias[indice] = familia
            contacto = None
            if familia is None and (fila["responsable"] or fila["telefono"] or fila["correo"]):
                contacto = {"nombre": (fila["responsable"] or f"{fila['nombre']} {fila['apellidos']}")[:150], "valores": _valores(fila["telefono"], fila["correo"])}
            titular = crear_titular(usuario, {"nombre": fila["nombre"], "apellidos": fila["apellidos"], "agrupacion": agrupacion, "familia": familia, "constancia_consentimiento": False}, contacto=contacto, request=request)
            Titular.objects.filter(pk=titular.pk).update(estado=Titular.ACTIVO, activo_desde=hoy)
            titular.refresh_from_db()
            registrar("alta_importada", usuario=usuario, objeto=titular, datos={"via": "importacion", "lote": lote.pk, "renglon": fila["numero"], "cambios": {"estado": ["Pendiente", "Activo"]}}, request=request)
            creados.append((titular, fila))
        conceptos = {c.pk: c for c in ConceptoCobro.objects.all()}
        for titular, fila in creados:
            for concepto_id, importe in fila["saldos"]:
                if importe > 0:
                    libro.crear_cargo(titular, conceptos[concepto_id], importe, hoy, Cargo.SALDO_INICIAL, descripcion=f"Saldo inicial: {conceptos[concepto_id]}", usuario=usuario, request=request)
                    cargos += 1
        for titular, fila in creados:
            for concepto_id, importe in fila["saldos"]:
                if importe < 0:
                    libro.registrar_pago(titular, -importe, Pago.SALDO_INICIAL, usuario, request=request, serie=parametro("serie_recibos_saldo_inicial"))
                    a_favor += 1
        lote.creados = len(creados)
        lote.familias = len(familias)
        lote.cargos = cargos
        lote.a_favor = a_favor
        lote.actualizados = len(actualizados)
        lote.saltados = len(saltados)
        lote.resultado = {"titulares": [t.pk for t, _ in creados], "actualizados": actualizados, "saltados": saltados}
        lote.save()
        registrar(
            "padron_importado", usuario=usuario,
            datos={"lote": lote.pk, "archivo": nombre_archivo, "sha256": sha256, "creados": lote.creados, "actualizados": lote.actualizados, "saltados": saltados, "familias": lote.familias, "cargos": cargos, "a_favor": a_favor, "solicitud": solicitud.pk if solicitud else None, "aprobo": str(autorizador) if autorizador else None},
            request=request,
        )
    return lote


def titulares_de(lote):
    orden = {pk: i for i, pk in enumerate(lote.resultado.get("titulares", []))}
    lista = list(Titular.objects.filter(pk__in=orden).select_related("agrupacion", "familia"))
    return sorted(lista, key=lambda t: orden[t.pk])


def encabezado(voc=None):
    voc = voc or vocabulario()
    return [voc["matricula"], "Nombre", "Apellidos", voc["agrupacion"], voc["familia"]]


def nombre_archivo_matriculas(lote, extension):
    from cortes.salida import saneado

    return f"{saneado(vocabulario()['matriculas']) or 'registros'}-{lote.pk}.{extension}"


def renglones(lote):
    return [[t.matricula, t.nombre, t.apellidos, str(t.agrupacion or ""), str(t.familia or "")] for t in titulares_de(lote)]


def a_csv(lote):
    salida = StringIO()
    escritor = csv.writer(salida)
    escritor.writerow([neutralizar(v) for v in encabezado()])
    for fila in renglones(lote):
        escritor.writerow([neutralizar(v) for v in fila])
    return salida.getvalue().encode("utf-8-sig")


def a_xlsx(lote):
    libro_xlsx = Workbook()
    hoja = libro_xlsx.active
    voc = vocabulario()
    hoja.title = "".join(c for c in voc["matriculas"] if c not in "[]:*?/\\")[:31] or "Hoja"
    hoja.append([neutralizar(v) for v in encabezado(voc)])
    for fila in renglones(lote):
        hoja.append([neutralizar(v) for v in fila])
    for celda in hoja["A"]:
        celda.number_format = "@"
    salida = BytesIO()
    libro_xlsx.save(salida)
    return salida.getvalue()
