import csv
from collections import defaultdict
from io import BytesIO, StringIO

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from openpyxl import Workbook

from auditoria.servicios import registrar
from banco import lectura
from cobros import libro
from cobros.models import Cargo, ConceptoCobro, Pago
from configuracion.models import hoy_negocio, parametro
from nucleo import telefono
from nucleo.exportar import neutralizar

from . import contactos
from .models import Agrupacion, CampoContacto, Familia, LotePadron, Titular
from .servicios import crear_titular, guardar_contacto

SINONIMOS = {
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


class ErrorPadron(ValueError):
    pass


def proponer(filas):
    encabezado = lectura.detectar_encabezado(filas, SINONIMOS)
    propuesta = lectura.proponer(filas, encabezado, SINONIMOS)
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


def analizar(filas, encabezado, columnas, concepto_saldo_total=None):
    columnas = {papel: int(indice) for papel, indice in columnas.items() if indice not in (None, "")}
    if not ({"nombre", "apellidos"} <= set(columnas) or "nombre_completo" in columnas):
        raise ErrorPadron("Indica las columnas de nombre y apellidos, o la de nombre completo.")
    if "saldo_total" in columnas and concepto_saldo_total is None:
        raise ErrorPadron("Elige el concepto al que se carga el saldo total.")
    obligatorio_tel = CampoContacto.objects.filter(tipo=CampoContacto.TELEFONO, obligatorio=True, activo=True).exists()
    prefijo, digitos = str(parametro("prefijo_pais_telefono")), parametro("digitos_telefono_nacional")
    existentes = llaves_existentes()
    vistos = set()
    resultado = []
    for numero, fila in enumerate(filas[encabezado + 1:], start=encabezado + 2):
        def valor(papel, maximo=150):
            indice = columnas.get(papel)
            return " ".join((fila[indice] if indice is not None and indice < len(fila) else "").split())[:maximo]

        if not any(c.strip() for c in fila):
            continue
        errores = []
        nombre, apellidos = valor("nombre", 100), valor("apellidos", 150)
        if "nombre_completo" in columnas and not (nombre and apellidos):
            nombre, apellidos = _partir(valor("nombre_completo", 250))
            nombre, apellidos = nombre[:100], apellidos[:150]
        if not nombre:
            errores.append("falta el nombre")
        if not apellidos:
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
            importe = lectura.importe(texto)
            if importe is None or abs(importe) >= 10 ** 11:
                errores.append(f"saldo no válido ({texto})")
            elif importe:
                saldos.append([concepto, importe])
        clave = llave(nombre, apellidos, tel)
        duplicado = ""
        if not errores:
            if ya_existe(existentes, nombre, apellidos, tel):
                duplicado = "ya existe en el padrón"
            elif clave in vistos:
                duplicado = "repetido en el archivo"
            vistos.add(clave)
        resultado.append(
            {
                "numero": numero, "nombre": nombre, "apellidos": apellidos, "agrupacion": valor("agrupacion", 100),
                "responsable": valor("responsable", 150), "telefono": tel, "correo": correo, "saldos": saldos,
                "errores": errores, "duplicado": duplicado, "familia": None,
            }
        )
    grupos = defaultdict(list)
    for indice, fila in enumerate(resultado):
        if not fila["errores"] and not fila["duplicado"] and fila["responsable"] and fila["telefono"]:
            grupos[(lectura.normal(fila["responsable"]), fila["telefono"])].append(indice)
    familias = []
    for (_, _), indices in grupos.items():
        if len(indices) >= 2:
            for i in indices:
                resultado[i]["familia"] = len(familias)
            familias.append({"responsable": resultado[indices[0]]["responsable"], "telefono": resultado[indices[0]]["telefono"], "miembros": [resultado[i]["nombre"] + " " + resultado[i]["apellidos"] for i in indices]})
    return {"filas": resultado, "familias": familias}


def _valores(tel, correo):
    valores = {}
    campo_tel = CampoContacto.objects.filter(tipo=CampoContacto.TELEFONO, activo=True).order_by("-principal", "orden").first()
    campo_correo = CampoContacto.objects.filter(tipo=CampoContacto.CORREO, activo=True).order_by("-principal", "orden").first()
    if tel and campo_tel:
        valores[str(campo_tel.pk)] = tel
    if correo and campo_correo:
        valores[str(campo_correo.pk)] = correo
    return valores


def aplicar(analisis, aceptadas, usuario, nombre_archivo, sha256, request=None):
    hoy = hoy_negocio()
    aceptadas = set(aceptadas)
    filas = [f for f in analisis["filas"] if not f["errores"] and not f["duplicado"]]
    with transaction.atomic():
        lote = LotePadron.objects.create(
            nombre_archivo=nombre_archivo, sha256=sha256, creado_por=usuario, filas=len(analisis["filas"]),
            duplicados=sum(1 for f in analisis["filas"] if f["duplicado"]), con_error=sum(1 for f in analisis["filas"] if f["errores"]),
        )
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
        lote.resultado = {"titulares": [t.pk for t, _ in creados]}
        lote.save()
        registrar("padron_importado", usuario=usuario, datos={"lote": lote.pk, "archivo": nombre_archivo, "sha256": sha256, "creados": lote.creados, "familias": lote.familias, "cargos": cargos, "a_favor": a_favor}, request=request)
    return lote


def titulares_de(lote):
    orden = {pk: i for i, pk in enumerate(lote.resultado.get("titulares", []))}
    lista = list(Titular.objects.filter(pk__in=orden).select_related("agrupacion", "familia"))
    return sorted(lista, key=lambda t: orden[t.pk])


ENCABEZADO = ["Matrícula", "Nombre", "Apellidos", "Agrupación", "Familia"]


def renglones(lote):
    return [[t.matricula, t.nombre, t.apellidos, str(t.agrupacion or ""), str(t.familia or "")] for t in titulares_de(lote)]


def a_csv(lote):
    salida = StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(ENCABEZADO)
    for fila in renglones(lote):
        escritor.writerow([neutralizar(v) for v in fila])
    return salida.getvalue().encode("utf-8-sig")


def a_xlsx(lote):
    libro_xlsx = Workbook()
    hoja = libro_xlsx.active
    hoja.title = "Matriculas"
    hoja.append(ENCABEZADO)
    for fila in renglones(lote):
        hoja.append([neutralizar(v) for v in fila])
    for celda in hoja["A"]:
        celda.number_format = "@"
    salida = BytesIO()
    libro_xlsx.save(salida)
    return salida.getvalue()
