import csv
import io
import re
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.utils import timezone

from auditoria.servicios import registrar
from caja import comprobantes
from caja import piezas as control_piezas
from caja.models import MovimientoPiezas, Turno
from caja.servicios import neto_de, recibe_movimientos
from cobros import libro
from cobros.models import CancelacionCargo, Cargo, Pago
from configuracion.models import hoy_negocio, parametro
from configuracion.moneda import formatear
from nucleo.exportar import neutralizar
from titulares.models import MATRICULA_INTERNA, Titular

from .models import (
    MAXIMO_CANTIDAD,
    MAXIMO_CONTEO,
    NO_APLICA,
    OBSERVADO,
    PATRON_CLAVE,
    POR_REVISAR,
    REVISADO,
    Articulo,
    ComprobanteInventario,
    Conteo,
    Devolucion,
    MovimientoInventario,
    RegistroInventario,
    RenglonConteo,
    RenglonDevolucion,
    RenglonVenta,
    Venta,
)

MAXIMO_RENGLONES = 30
LIMITE_CONTEO = 1024 * 1024
MAXIMO_FILAS_CONTEO = 5000
CLAVE = re.compile(PATRON_CLAVE)
CANTIDAD = re.compile(r"^[0-9]{1,7}$")
TITULOS_CLAVE = {"clave", "codigo", "sku"}
TITULOS_CANTIDAD = {"cantidad", "contado", "conteo", "existencia fisica"}


class ErrorInventario(ValueError):
    pass


class RevisionPropia(ErrorInventario):
    pass


def activo():
    return bool(parametro("modulo_inventario"))


def exigir_activo():
    if not activo():
        raise ErrorInventario("El inventario no está encendido.")


def existencias(articulos=None):
    consulta = MovimientoInventario.objects.all()
    if articulos is not None:
        consulta = consulta.filter(articulo__in=articulos)
    return {fila["articulo"]: fila["total"] for fila in consulta.values("articulo").annotate(total=Sum("cantidad")).order_by()}


def existencia(articulo):
    return existencias([articulo.pk]).get(articulo.pk, 0)


def cuenta_publico(usuario):
    existente = Titular.todos.filter(interno=True).first()
    if existente is not None:
        return existente
    try:
        with transaction.atomic():
            cuenta = Titular.todos.create(
                matricula=MATRICULA_INTERNA, nombre="Público", apellidos="en general", estado=Titular.ACTIVO, interno=True, creado_por=usuario, activo_desde=hoy_negocio(),
            )
    except IntegrityError:
        return Titular.todos.get(interno=True)
    registrar("cuenta_publico_creada", usuario=usuario, objeto=cuenta, datos={"nombre": cuenta.nombre_completo})
    return cuenta


def _entero(valor, nombre, minimo, maximo):
    if type(valor) is not int or valor < minimo or valor > maximo:
        raise ErrorInventario(f"{nombre} debe ser un número entero entre {minimo} y {maximo}.")
    return valor


def validar_renglones(renglones):
    if not renglones:
        raise ErrorInventario("Agrega al menos un artículo.")
    if len(renglones) > MAXIMO_RENGLONES:
        raise ErrorInventario(f"Una venta lleva a lo más {MAXIMO_RENGLONES} artículos distintos.")
    cantidades = {}
    for articulo_id, cantidad in renglones:
        if type(articulo_id) is not int:
            raise ErrorInventario("Artículo no válido.")
        _entero(cantidad, "La cantidad", 1, MAXIMO_CANTIDAD)
        cantidades[articulo_id] = cantidades.get(articulo_id, 0) + cantidad
        _entero(cantidades[articulo_id], "La cantidad de un mismo artículo", 1, MAXIMO_CANTIDAD)
    articulos = {a.pk: a for a in Articulo.objects.filter(pk__in=list(cantidades), activo=True).select_related("concepto")}
    if set(articulos) != set(cantidades):
        raise ErrorInventario("Uno de los artículos no existe o no está activo.")
    return [(articulos[pk], cantidad) for pk, cantidad in cantidades.items()]


def _crear_venta(titular, lista, modo, usuario, request, permitir_interno=False):
    total = sum(articulo.precio * cantidad for articulo, cantidad in lista)
    venta = Venta.objects.create(titular=titular, modo=modo, total=total, usuario=usuario)
    actuales = existencias([a.pk for a, _ in lista])
    hoy = hoy_negocio()
    sin_existencia = []
    for articulo, cantidad in lista:
        descripcion = f"{articulo.nombre} × {cantidad}" if cantidad > 1 else articulo.nombre
        cargo = libro.crear_cargo(titular, articulo.concepto, articulo.precio * cantidad, hoy, Cargo.MANUAL, descripcion=descripcion, cantidad=cantidad, usuario=usuario, request=request, permitir_interno=permitir_interno)
        if cargo is None:
            raise ErrorInventario("No se pudo crear el cargo de la venta.")
        antes = actuales.get(articulo.pk, 0)
        falta = antes < cantidad
        RenglonVenta.objects.create(venta=venta, articulo=articulo, cantidad=cantidad, precio_unitario=articulo.precio, cargo=cargo, existencia_antes=antes, sin_existencia=falta)
        MovimientoInventario.objects.create(articulo=articulo, tipo=MovimientoInventario.VENTA, cantidad=-cantidad, usuario=usuario, venta=venta)
        if falta:
            sin_existencia.append(articulo.clave)
    registrar(
        "venta_registrada",
        usuario=usuario,
        objeto=venta,
        titular=titular.pk,
        datos={
            "venta": str(venta), "modo": modo, "total": total, "total_texto": formatear(total), "publico": titular.interno,
            "renglones": [{"articulo": a.clave, "cantidad": c, "precio": a.precio} for a, c in lista], "sin_existencia": sin_existencia,
        },
        request=request,
    )
    return venta


def vender(titular, renglones, modo, usuario, request=None):
    exigir_activo()
    if modo not in (Venta.AHORA, Venta.ADEUDO):
        raise ErrorInventario("Elige cómo se paga la venta.")
    lista = validar_renglones(renglones)
    with transaction.atomic():
        titular = Titular.objects.filter(pk=titular.pk).first()
        if titular is None or titular.estado not in (Titular.ACTIVO, Titular.PENDIENTE):
            raise ErrorInventario("Solo se vende a un registro activo o pendiente de alta.")
        return _crear_venta(titular, lista, modo, usuario, request)


def total_de(renglones):
    return sum(articulo.precio * cantidad for articulo, cantidad in validar_renglones(renglones))


def vender_publico(renglones, usuario, turno, ficha, piezas=None, request=None):
    exigir_activo()
    lista = validar_renglones(renglones)
    total = sum(articulo.precio * cantidad for articulo, cantidad in lista)
    if total > parametro("tope_pago_individual"):
        raise ErrorInventario(f"La venta sin matrícula pasa del tope de un pago individual ({formatear(parametro('tope_pago_individual'))}); divídela o véndela a un registro.")
    with transaction.atomic():
        if ficha:
            existente = Pago.objects.filter(ficha=ficha).select_related("venta").first()
            if existente is not None:
                raise libro.PagoDuplicado(existente)
        if turno is None or not recibe_movimientos(turno):
            raise ErrorInventario("Se necesita tu turno de caja abierto y fuera de arqueo.")
        publico = cuenta_publico(usuario)
        venta = _crear_venta(publico, lista, Venta.AHORA, usuario, request, permitir_interno=True)
        cargos = list(venta.renglones.values_list("cargo_id", flat=True))
        pago = libro.registrar_pago(publico, total, Pago.EFECTIVO, usuario, turno=turno, ficha=ficha, request=request, piezas=piezas, primero=cargos, permitir_interno=True)
        Venta.objects.filter(pk=venta.pk, pago__isnull=True).update(pago=pago)
        quedan = sum(p.saldo for p in libro.pendientes_de([publico.pk]))
        a_favor = sum(p.remanente for p in libro.con_remanente(Pago.objects.filter(titular=publico, reversion__isnull=True)))
        if quedan or a_favor:
            raise ErrorInventario("La cuenta interna no puede quedar con adeudo ni saldo a favor; no se registró la venta.")
    venta.refresh_from_db()
    return venta


def cargos_de(venta):
    return list(venta.renglones.values_list("cargo_id", flat=True))


def pendiente_de(venta):
    return sum(libro.saldo_de(r.cargo) for r in venta.renglones.select_related("cargo"))


def venta_por_cobrar(titular, valor):
    texto = str(valor or "")
    if not texto.isdigit() or len(texto) > 12:
        return None
    return Venta.objects.filter(pk=int(texto), titular_id=titular.pk, modo=Venta.AHORA, pago__isnull=True).first()


def ligar_pago(venta, pago):
    if venta is None:
        return False
    return Venta.objects.filter(pk=venta.pk, pago__isnull=True, titular_id=pago.titular_id).update(pago=pago) == 1


def en_plazo(venta, hoy=None):
    hoy = hoy or hoy_negocio()
    dias = max(int(parametro("dias_devolucion")), 0)
    return libro.fecha_local(venta.creada) + timedelta(days=dias) >= hoy


def devueltos(venta, incluir_pendientes=False):
    filas = RenglonDevolucion.objects.filter(renglon__venta=venta).values("renglon").annotate(t=Sum("cantidad")).order_by()
    resultado = {f["renglon"]: f["t"] for f in filas}
    if incluir_pendientes:
        from solicitudes.models import Solicitud

        for solicitud in Solicitud.objects.filter(accion="devolucion_efectivo", estado=Solicitud.PENDIENTE, datos__venta=venta.pk):
            for clave, (cantidad, _) in (solicitud.datos.get("renglones") or {}).items():
                if str(clave).isdigit() and type(cantidad) is int:
                    resultado[int(clave)] = resultado.get(int(clave), 0) + cantidad
    return resultado


def disponibles(venta, incluir_pendientes=False):
    usados = devueltos(venta, incluir_pendientes)
    return {r.pk: r.cantidad - usados.get(r.pk, 0) for r in venta.renglones.all()}


def validar_devolucion(venta, cantidades, incluir_pendientes=True):
    if not isinstance(cantidades, dict) or not cantidades:
        raise ErrorInventario("Indica qué artículos se devuelven.")
    libres = disponibles(venta, incluir_pendientes)
    renglones = {r.pk: r for r in venta.renglones.select_related("articulo", "cargo")}
    limpio = {}
    for clave, par in cantidades.items():
        if not str(clave).isdigit() or int(clave) not in renglones:
            raise ErrorInventario("Ese artículo no es de esta venta.")
        if not isinstance(par, (list, tuple)) or len(par) != 2 or type(par[1]) is not bool:
            raise ErrorInventario("Los datos de la devolución no son válidos.")
        cantidad = _entero(par[0], "La cantidad a devolver", 1, MAXIMO_CANTIDAD)
        if cantidad > libres.get(int(clave), 0):
            raise ErrorInventario(f"No se puede devolver más de lo vendido y no devuelto ({renglones[int(clave)].articulo.nombre}).")
        limpio[int(clave)] = (renglones[int(clave)], cantidad, par[1])
    return limpio


def _motivo(motivo):
    texto = " ".join(str(motivo or "").split())[:300]
    if not texto:
        raise ErrorInventario("Escribe el motivo de la devolución.")
    return texto


def _cancelar(renglon, valor, motivo, usuario, autorizador, solicitud, request):
    pendiente = libro.saldo_de(renglon.cargo)
    cancelado = min(pendiente, valor)
    if cancelado > 0:
        libro.cancelar_cargo(renglon.cargo, cancelado, CancelacionCargo.CANCELACION, f"Devolución de artículos: {motivo}"[:300], usuario, autorizador, solicitud, request)
    return cancelado


def _regresar(devolucion, renglon, cantidad, buen_estado, usuario):
    RenglonDevolucion.objects.create(devolucion=devolucion, renglon=renglon, cantidad=cantidad, buen_estado=buen_estado)
    MovimientoInventario.objects.create(articulo=renglon.articulo, tipo=MovimientoInventario.DEVOLUCION, cantidad=cantidad, usuario=usuario, devolucion=devolucion)
    if not buen_estado:
        MovimientoInventario.objects.create(articulo=renglon.articulo, tipo=MovimientoInventario.MERMA, cantidad=-cantidad, usuario=usuario, devolucion=devolucion, nota="Devuelto en mal estado")


def devolver(venta, cantidades, medio, usuario, motivo, request=None, turno=None, solicitud=None, autorizador=None, piezas=None):
    exigir_activo()
    motivo = _motivo(motivo)
    if not parametro("devoluciones_inventario"):
        raise ErrorInventario("El negocio no acepta devoluciones de artículos.")
    if medio not in (Devolucion.SALDO, Devolucion.EFECTIVO, Devolucion.SIN_DINERO):
        raise ErrorInventario("Elige cómo regresa el dinero.")
    if medio == Devolucion.EFECTIVO and solicitud is None:
        raise ErrorInventario("La devolución en efectivo siempre se solicita y la resuelve otra persona.")
    with transaction.atomic():
        venta = Venta.objects.select_related("titular").get(pk=venta.pk)
        if not en_plazo(venta):
            raise ErrorInventario("La venta está fuera del plazo de devolución.")
        limpio = validar_devolucion(venta, cantidades, incluir_pendientes=False)
        if venta.titular.interno and medio != Devolucion.EFECTIVO:
            raise ErrorInventario("Una venta sin matrícula solo se devuelve en efectivo.")
        valor = sum(renglon.precio_unitario * cantidad for renglon, cantidad, _ in limpio.values())
        cancelado = sum(_cancelar(renglon, renglon.precio_unitario * cantidad, motivo, usuario, autorizador, solicitud, request) for renglon, cantidad, _ in limpio.values())
        dinero = valor - cancelado
        if dinero == 0:
            medio = Devolucion.SIN_DINERO
        elif medio == Devolucion.SIN_DINERO:
            raise ErrorInventario("Parte de lo devuelto ya estaba pagado: elige saldo a favor o efectivo.")
        pago_credito = None
        if medio == Devolucion.EFECTIVO:
            if turno is None or not Turno.objects.filter(pk=turno.pk, estado=Turno.ABIERTO).exists() or not recibe_movimientos(turno):
                raise ErrorInventario("Para devolver efectivo se necesita el turno de caja abierto de quien lo entrega.")
            if neto_de(turno) < dinero:
                registrar("devolucion_rechazada", usuario=usuario, objeto=venta, datos={"venta": str(venta), "motivo": "efectivo_insuficiente", "turno": turno.pk}, request=request)
                raise ErrorInventario("El turno de quien entrega el efectivo no tiene lo suficiente para esta devolución.")
            if control_piezas.activo():
                try:
                    piezas = control_piezas.exigir_total(piezas or {}, dinero, "Las piezas que entregas deben sumar exactamente lo que se devuelve.")
                except control_piezas.ErrorPiezas as error:
                    raise ErrorInventario(str(error))
            else:
                piezas = {}
        elif medio == Devolucion.SALDO:
            pago_credito = libro.registrar_pago(venta.titular, dinero, Pago.DEVOLUCION, usuario, request=request, serie=str(parametro("serie_devoluciones")).strip().upper() or "D")
        revision = NO_APLICA if medio == Devolucion.EFECTIVO else POR_REVISAR
        devolucion = Devolucion.objects.create(
            venta=venta, medio=medio, motivo=motivo, importe_cancelado=cancelado, importe_dinero=dinero, usuario=usuario, autorizada_por=autorizador,
            solicitud=solicitud, turno=turno if medio == Devolucion.EFECTIVO else None, pago_credito=pago_credito, revision=revision,
        )
        for renglon, cantidad, buen_estado in limpio.values():
            _regresar(devolucion, renglon, cantidad, buen_estado, usuario)
        if medio == Devolucion.EFECTIVO and piezas:
            control_piezas.registrar(turno, usuario, MovimientoPiezas.DEVOLUCION_ARTICULOS, piezas, -1, devolucion_articulos=devolucion)
        registrar(
            "devolucion_articulos",
            usuario=usuario,
            objeto=devolucion,
            titular=venta.titular_id,
            datos={
                "venta": str(venta), "medio": medio, "valor": valor, "cancelado": cancelado, "dinero": dinero, "motivo": motivo,
                "renglones": [{"articulo": r.articulo.clave, "cantidad": c, "buen_estado": b} for r, c, b in limpio.values()],
                "autorizo": str(autorizador) if autorizador else None, "turno": turno.pk if turno is not None and medio == Devolucion.EFECTIVO else None,
            },
            request=request,
        )
    return devolucion


def solicitar_efectivo(venta, cantidades, usuario, motivo, piezas=None, request=None):
    from solicitudes import motor

    exigir_activo()
    if not parametro("devoluciones_inventario"):
        raise ErrorInventario("El negocio no acepta devoluciones de artículos.")
    datos = {"venta": venta.pk, "renglones": {str(k): list(v) for k, v in cantidades.items()}, "motivo": _motivo(motivo)}
    if piezas:
        datos["piezas"] = piezas
    with transaction.atomic():
        try:
            return motor.ejecutar("devolucion_efectivo", usuario, None, datos, request=request)
        except motor.ErrorSolicitud as error:
            raise ErrorInventario(str(error))


def tras_reversion(pago, regresan, usuario, autorizador=None, solicitud=None, request=None):
    venta = Venta.objects.filter(pago=pago).select_related("titular").first()
    if venta is None:
        return None
    regresan = {int(r) for r in (regresan or []) if str(r).isdigit()}
    libres = disponibles(venta)
    elegidos = [r for r in venta.renglones.select_related("articulo", "cargo") if r.pk in regresan and libres.get(r.pk, 0) > 0]
    if not elegidos:
        return None
    cancelado = sum(_cancelar(renglon, renglon.precio_unitario * libres[renglon.pk], "regresó al revertir el pago", usuario, autorizador, solicitud, request) for renglon in elegidos)
    devolucion = Devolucion.objects.create(
        venta=venta, medio=Devolucion.REVERSION, motivo=f"Reversión del pago {pago.recibo}"[:300], importe_cancelado=cancelado, usuario=usuario, autorizada_por=autorizador, solicitud=solicitud, revision=NO_APLICA,
    )
    for renglon in elegidos:
        _regresar(devolucion, renglon, libres[renglon.pk], True, usuario)
    registrar("articulos_regresados", usuario=usuario, objeto=devolucion, titular=venta.titular_id, datos={"venta": str(venta), "pago": pago.pk, "renglones": [{"articulo": r.articulo.clave, "cantidad": libres[r.pk]} for r in elegidos], "cancelado": cancelado}, request=request)
    return devolucion


def _revisar(modelo, objeto, usuario, resultado, nota, evento, request):
    if resultado not in (REVISADO, OBSERVADO):
        raise ErrorInventario("Elige si queda revisado u observado.")
    nota = " ".join(str(nota or "").split())[:300]
    if resultado == OBSERVADO and not nota:
        raise ErrorInventario("Escribe la observación.")
    if objeto.usuario_id == usuario.pk:
        registrar("revision_propia_denegada", usuario=usuario, objeto=objeto, datos={"tipo": evento}, request=request)
        raise RevisionPropia("Nadie revisa lo que registró.")
    with transaction.atomic():
        hechos = modelo.objects.filter(pk=objeto.pk, revision=POR_REVISAR).exclude(usuario=usuario).update(revision=resultado, revisado_por=usuario, revisado_en=timezone.now(), nota_revision=nota)
        if hechos != 1:
            raise ErrorInventario("Ya estaba revisado.")
        registrar(evento, usuario=usuario, objeto=objeto, datos={"resultado": resultado, "nota": nota}, request=request)


def revisar_registro(registro, usuario, resultado, nota="", request=None):
    _revisar(RegistroInventario, registro, usuario, resultado, nota, "registro_inventario_revisado", request)


def revisar_devolucion(devolucion, usuario, resultado, nota="", request=None):
    _revisar(Devolucion, devolucion, usuario, resultado, nota, "devolucion_revisada", request)


def revisar_sin_existencia(renglon, usuario, request=None):
    if renglon.venta.usuario_id == usuario.pk:
        registrar("revision_propia_denegada", usuario=usuario, objeto=renglon.venta, datos={"tipo": "sin_existencia"}, request=request)
        raise RevisionPropia("Nadie revisa lo que registró.")
    with transaction.atomic():
        hechos = RenglonVenta.objects.filter(pk=renglon.pk, sin_existencia=True, revisado_por__isnull=True).update(revisado_por=usuario, revisado_en=timezone.now())
        if hechos != 1:
            raise ErrorInventario("Ya estaba revisado.")
        registrar("venta_sin_existencia_revisada", usuario=usuario, objeto=renglon.venta, datos={"articulo": renglon.articulo.clave, "cantidad": renglon.cantidad, "existencia_antes": renglon.existencia_antes}, request=request)


def registrar_movimiento(tipo, articulo, cantidad, motivo, nota, usuario, comprobante=None, request=None):
    exigir_activo()
    if tipo not in (RegistroInventario.ENTRADA, RegistroInventario.MERMA):
        raise ErrorInventario("Elige si es entrada o merma.")
    _entero(cantidad, "La cantidad", 1, MAXIMO_CANTIDAD)
    motivo = " ".join(str(motivo or "").split())[:150]
    if not motivo:
        raise ErrorInventario("Escribe el motivo.")
    preparado = comprobantes.preparar(comprobante) if comprobante is not None else None
    with transaction.atomic():
        articulo = Articulo.objects.filter(pk=articulo.pk, activo=True).first()
        if articulo is None:
            raise ErrorInventario("El artículo no existe o no está activo.")
        registro = RegistroInventario.objects.create(tipo=tipo, articulo=articulo, cantidad=cantidad, motivo=motivo, nota=" ".join(str(nota or "").split())[:300], usuario=usuario)
        signo = 1 if tipo == RegistroInventario.ENTRADA else -1
        MovimientoInventario.objects.create(articulo=articulo, tipo=tipo, cantidad=signo * cantidad, usuario=usuario, registro=registro, nota=motivo)
        registrar(f"inventario_{tipo}", usuario=usuario, objeto=registro, datos={"articulo": articulo.clave, "cantidad": cantidad, "motivo": motivo, "nota": registro.nota}, request=request)
        if preparado is not None:
            adjuntar_preparado(registro, usuario, preparado, request)
    return registro


def adjuntar_preparado(registro, usuario, preparado, request=None):
    tipo, contenido = preparado
    nombre, huella = comprobantes.guardar(tipo, contenido)
    try:
        with transaction.atomic():
            hechos = RegistroInventario.objects.filter(pk=registro.pk, comprobante=RegistroInventario.SIN).update(comprobante=RegistroInventario.ADJUNTO)
            if hechos != 1:
                raise ErrorInventario("El registro ya tiene comprobante.")
            objeto = ComprobanteInventario.objects.create(registro=registro, archivo=nombre, tipo=tipo, tamano=len(contenido), sha256=huella, subido_por=usuario)
            registrar("comprobante_inventario_adjuntado", usuario=usuario, objeto=registro, datos={"tipo": tipo, "tamano": len(contenido), "sha256": huella}, request=request)
    except Exception:
        comprobantes.descartar(nombre)
        raise
    return objeto


def adjuntar(registro, usuario, contenido, request=None):
    if registro.usuario_id != usuario.pk:
        raise ErrorInventario("Solo quien registró el movimiento adjunta su comprobante.")
    if registro.comprobante != RegistroInventario.SIN:
        raise ErrorInventario("El registro ya tiene comprobante.")
    return adjuntar_preparado(registro, usuario, comprobantes.preparar(contenido), request)


def lista_para_contar():
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(["clave", "nombre", "cantidad"])
    for articulo in Articulo.objects.filter(activo=True).order_by("clave"):
        escritor.writerow([neutralizar(articulo.clave), neutralizar(articulo.nombre), ""])
    return ("﻿" + salida.getvalue()).encode("utf-8")


def _formulas_xlsx(contenido):
    from openpyxl import load_workbook

    libro_xlsx = load_workbook(io.BytesIO(contenido), read_only=True, data_only=False)
    try:
        for fila in libro_xlsx.worksheets[0].iter_rows(values_only=True, max_row=MAXIMO_FILAS_CONTEO + 2, max_col=10):
            for valor in fila:
                if isinstance(valor, str) and valor.startswith("="):
                    return True
    finally:
        libro_xlsx.close()
    return False


def leer_conteo(nombre, contenido):
    from banco import lectura

    if len(contenido) > LIMITE_CONTEO:
        raise ErrorInventario("El archivo pasa de 1 MB.")
    try:
        filas = lectura.filas_de_hoja(nombre, contenido)
        if contenido.startswith(b"PK\x03\x04") and _formulas_xlsx(contenido):
            raise ErrorInventario("El archivo trae fórmulas: sube solo valores.")
    except lectura.ErrorLectura as error:
        raise ErrorInventario(str(error))
    except ErrorInventario:
        raise
    except Exception:
        raise ErrorInventario("No se pudo leer el archivo.")
    if len(filas) > MAXIMO_FILAS_CONTEO + 1:
        raise ErrorInventario(f"El archivo tiene más de {MAXIMO_FILAS_CONTEO} renglones.")
    titulos = [lectura.normal(c) for c in filas[0]]
    columna_clave = next((i for i, t in enumerate(titulos) if t in TITULOS_CLAVE), None)
    columna_cantidad = next((i for i, t in enumerate(titulos) if t in TITULOS_CANTIDAD), None)
    if columna_clave is None or columna_cantidad is None:
        raise ErrorInventario("El archivo debe traer las columnas «clave» y «cantidad».")
    articulos = {a.clave: a for a in Articulo.objects.filter(activo=True)}
    errores, cantidades, vistas = [], {}, {}
    for numero, fila in enumerate(filas[1:], start=2):
        clave = fila[columna_clave].strip().upper() if columna_clave < len(fila) else ""
        texto = fila[columna_cantidad].strip() if columna_cantidad < len(fila) else ""
        if not clave and not texto:
            continue
        if clave.startswith(("=", "+", "-", "@")) or texto.startswith(("=", "+", "-", "@")):
            errores.append(f"Renglón {numero}: trae una fórmula o un signo; solo se aceptan claves y números enteros.")
            continue
        if not CLAVE.match(clave) or clave not in articulos:
            errores.append(f"Renglón {numero}: clave desconocida.")
            continue
        if clave in vistas:
            errores.append(f"Renglón {numero}: la clave {clave} se repite (renglón {vistas[clave]}).")
            continue
        vistas[clave] = numero
        if texto.endswith(".0") and texto[:-2].isdigit():
            texto = texto[:-2]
        if not CANTIDAD.match(texto) or int(texto) > MAXIMO_CONTEO:
            errores.append(f"Renglón {numero}: la cantidad debe ser un número entero de 0 a {MAXIMO_CONTEO}.")
            continue
        cantidades[articulos[clave].pk] = int(texto)
    if errores:
        raise ErrorInventario(" ".join(errores[:15]) + (f" (y {len(errores) - 15} más)" if len(errores) > 15 else ""))
    if not cantidades:
        raise ErrorInventario("El archivo no trae artículos contados.")
    return cantidades


def conteo_en_espera():
    from solicitudes.models import Solicitud

    return Conteo.objects.filter(solicitud__estado=Solicitud.PENDIENTE).select_related("usuario", "solicitud").first()


def subir_conteo(cantidades, usuario, origen, nombre="", sha256="", request=None):
    from solicitudes import motor

    exigir_activo()
    if not isinstance(cantidades, dict) or not cantidades:
        raise ErrorInventario("El conteo no trae artículos.")
    for articulo_id, cantidad in cantidades.items():
        if type(articulo_id) is not int:
            raise ErrorInventario("Artículo no válido.")
        _entero(cantidad, "La cantidad contada", 0, MAXIMO_CONTEO)
    motor.caducar_vencidas()
    with transaction.atomic():
        if conteo_en_espera() is not None:
            raise ErrorInventario("Ya hay un conteo en espera de aprobación.")
        articulos = {a.pk: a for a in Articulo.objects.filter(pk__in=list(cantidades), activo=True)}
        if set(articulos) != set(cantidades):
            raise ErrorInventario("Uno de los artículos no existe o no está activo.")
        esperadas = existencias(list(cantidades))
        inicial = not Conteo.objects.filter(aplicado_en__isnull=False).exists()
        conteo = Conteo.objects.create(usuario=usuario, origen=origen, nombre_archivo=nombre[:120], sha256=sha256[:64], inicial=inicial)
        for articulo_id, contado in sorted(cantidades.items()):
            esperado = esperadas.get(articulo_id, 0)
            RenglonConteo.objects.create(conteo=conteo, articulo=articulos[articulo_id], contado=contado, esperado=esperado, diferencia=contado - esperado)
        registrar(
            "conteo_inventario_subido",
            usuario=usuario,
            objeto=conteo,
            datos={"origen": origen, "archivo": conteo.nombre_archivo, "sha256": conteo.sha256, "articulos": len(cantidades), "contado": {articulos[k].clave: v for k, v in cantidades.items()}},
            request=request,
        )
        try:
            resultado = motor.ejecutar("conteo_inventario", usuario, None, {"conteo": conteo.pk}, request=request)
        except motor.ErrorSolicitud as error:
            raise ErrorInventario(str(error))
        if resultado.solicitud is None:
            raise ErrorInventario("El conteo debe quedar como solicitud.")
        Conteo.objects.filter(pk=conteo.pk, solicitud__isnull=True).update(solicitud=resultado.solicitud)
    conteo.refresh_from_db()
    return conteo


def aplicar_conteo(conteo, aprobador, request=None):
    if conteo.usuario_id == aprobador.pk:
        raise RevisionPropia("Nadie aprueba su propio conteo.")
    hechos = Conteo.objects.filter(pk=conteo.pk, aplicado_en__isnull=True).exclude(usuario=aprobador).update(aplicado_en=timezone.now(), aplicado_por=aprobador)
    if hechos != 1:
        raise ErrorInventario("El conteo ya se aplicó.")
    tipo = MovimientoInventario.CARGA_INICIAL if conteo.inicial else MovimientoInventario.AJUSTE
    ajustes = []
    for renglon in conteo.renglones.select_related("articulo"):
        if renglon.diferencia:
            MovimientoInventario.objects.create(articulo=renglon.articulo, tipo=tipo, cantidad=renglon.diferencia, usuario=aprobador, conteo=conteo, nota=f"Conteo {conteo.pk}")
            ajustes.append({"articulo": renglon.articulo.clave, "diferencia": renglon.diferencia})
    registrar("conteo_inventario_aplicado", usuario=aprobador, objeto=conteo, datos={"ajustes": ajustes, "tipo": tipo}, request=request)
    return ajustes


def bajo_minimo():
    actuales = existencias()
    return [(a, actuales.get(a.pk, 0)) for a in Articulo.objects.filter(activo=True).order_by("clave") if actuales.get(a.pk, 0) <= a.minimo]


def avisos(usuario):
    if not activo():
        return {}
    resultado = {}
    if usuario.tiene_permiso("revisar_inventario") or usuario.tiene_permiso("administrar_articulos"):
        resultado["bajo_minimo"] = bajo_minimo()
    if usuario.tiene_permiso("revisar_inventario"):
        resultado["por_revisar"] = (
            RegistroInventario.objects.filter(revision=POR_REVISAR).exclude(usuario=usuario).count()
            + Devolucion.objects.filter(revision=POR_REVISAR).exclude(usuario=usuario).count()
            + RenglonVenta.objects.filter(sin_existencia=True, revisado_por__isnull=True).exclude(venta__usuario=usuario).count()
        )
    if usuario.tiene_permiso("ver_auditoria"):
        espera = conteo_en_espera()
        if espera is not None and espera.creado < timezone.now() - timedelta(days=max(int(parametro("dias_conteo_sin_aprobar")), 1)):
            resultado["conteo_viejo"] = espera
    return resultado


def resumen(inicio, fin, desde, hasta):
    articulos = list(Articulo.objects.order_by("clave"))
    if not articulos:
        return []
    actuales = existencias()
    del_periodo = MovimientoInventario.objects.filter(creado__gte=desde, creado__lt=hasta).values("articulo", "tipo").annotate(t=Sum("cantidad")).order_by()
    porcion = {}
    for fila in del_periodo:
        porcion.setdefault(fila["articulo"], {})[fila["tipo"]] = fila["t"]
    posteriores = {f["articulo"]: f["t"] for f in MovimientoInventario.objects.filter(creado__gte=hasta).values("articulo").annotate(t=Sum("cantidad")).order_by()}
    filas = []
    for articulo in articulos:
        tipos = porcion.get(articulo.pk, {})
        al_cierre = actuales.get(articulo.pk, 0) - posteriores.get(articulo.pk, 0)
        if not tipos and not al_cierre and not articulo.activo:
            continue
        filas.append(
            {
                "clave": articulo.clave,
                "articulo": articulo.nombre,
                "existencia_al_cierre": al_cierre,
                "ventas": -tipos.get(MovimientoInventario.VENTA, 0),
                "devoluciones": tipos.get(MovimientoInventario.DEVOLUCION, 0),
                "entradas": tipos.get(MovimientoInventario.ENTRADA, 0),
                "mermas": -tipos.get(MovimientoInventario.MERMA, 0),
                "ajustes": tipos.get(MovimientoInventario.AJUSTE, 0) + tipos.get(MovimientoInventario.CARGA_INICIAL, 0),
            }
        )
    return filas


def exportar_existencias():
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(["clave", "nombre", "precio", "existencia", "minimo", "activo"])
    actuales = existencias()
    for articulo in Articulo.objects.order_by("clave"):
        escritor.writerow([neutralizar(articulo.clave), neutralizar(articulo.nombre), f"{articulo.precio / 100:.2f}", actuales.get(articulo.pk, 0), articulo.minimo, "sí" if articulo.activo else "no"])
    return ("﻿" + salida.getvalue()).encode("utf-8")


def ventas_recientes(limite=100):
    return Venta.objects.select_related("titular", "usuario", "pago__recibo").annotate(articulos=Count("renglones"))[:limite]


def buscar_venta(texto):
    texto = str(texto or "").strip().upper()
    if texto.startswith("V-"):
        texto = texto[2:]
    if not texto.isdigit() or len(texto) > 12:
        return None
    return Venta.objects.filter(pk=int(texto)).select_related("titular").first()


def venta_de_recibo(recibo):
    return Venta.objects.filter(pago=recibo.pago).select_related("titular").first()
