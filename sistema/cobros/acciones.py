from datetime import date

from django.db.models import Max, Q

from caja.servicios import turno_abierto
from configuracion.models import parametro
from configuracion.moneda import formatear

from . import libro
from .models import Beca, CancelacionCargo, Cargo, ConceptoCobro, Pago, Prorroga, ReversionPago


class ErrorAccion(ValueError):
    pass


def _fecha(texto, nombre):
    try:
        return date.fromisoformat(texto) if texto else None
    except (TypeError, ValueError):
        raise ErrorAccion(f"Fecha no válida en {nombre}.")


def _entero(valor, nombre):
    if type(valor) is not int:
        raise ErrorAccion(f"{nombre} debe ser un número entero.")
    return valor


def _cargo(titular, datos):
    cargo = Cargo.objects.filter(pk=datos.get("cargo"), titular=titular).select_related("concepto").first()
    if cargo is None:
        raise ErrorAccion("El cargo no pertenece a este registro.")
    return cargo


def _motivo(datos):
    motivo = (datos.get("motivo") or "").strip()
    if not motivo:
        raise ErrorAccion("Indica el motivo.")
    return motivo


class AccionLibro:
    motivo_obligatoria = "pago_cobrado_por_quien_revierte"
    mensaje_propio = "Nadie resuelve la reversión de un pago que él mismo cobró."

    def llave(self, datos):
        return {}

    def exige_solicitud(self, usuario, titular, datos):
        return False

    def puede_resolver(self, usuario, datos):
        return True

    def rechazar(self, titular, datos, contexto=None):
        pass


class OtorgarBeca(AccionLibro):
    def llave(self, datos):
        return {"datos__concepto": datos.get("concepto")}

    def validar(self, titular, datos):
        if set(datos) - {"concepto", "puntos_base", "desde", "hasta", "motivo"}:
            raise ErrorAccion("La beca solo admite porcentaje.")
        concepto = ConceptoCobro.objects.filter(pk=datos.get("concepto"), tipo=ConceptoCobro.RECURRENTE, activo=True).first()
        if concepto is None:
            raise ErrorAccion("La beca aplica a un concepto recurrente activo.")
        puntos = _entero(datos.get("puntos_base"), "El porcentaje")
        if not 1 <= puntos <= 10000:
            raise ErrorAccion("El porcentaje de beca va de 0.01 % a 100 %.")
        desde = _fecha(datos.get("desde"), "vigente desde")
        hasta = _fecha(datos.get("hasta"), "vigente hasta")
        if desde is None or (hasta is not None and hasta < desde):
            raise ErrorAccion("Revisa la vigencia de la beca.")
        _motivo(datos)
        cruce = Beca.objects.filter(titular=titular, concepto=concepto).filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=desde))
        if hasta is not None:
            cruce = cruce.filter(vigente_desde__lte=hasta)
        if cruce.exists():
            raise ErrorAccion("Ya hay una beca vigente para ese concepto en esas fechas.")
        return concepto

    def aplicar(self, titular, datos, contexto):
        concepto = self.validar(titular, datos)
        beca = Beca.objects.create(
            titular=titular, concepto=concepto, puntos_base=datos["puntos_base"], vigente_desde=_fecha(datos["desde"], ""),
            vigente_hasta=_fecha(datos.get("hasta"), ""), motivo=_motivo(datos)[:300], creada_por=contexto.solicitante,
            autorizada_por=contexto.autorizador, solicitud=contexto.solicitud,
        )
        contexto.resultado = beca
        return {"beca": beca.pk, "porcentaje": beca.porcentaje_texto, "concepto": str(concepto)}


class OtorgarProrroga(AccionLibro):
    def llave(self, datos):
        return {"datos__cargo": datos.get("cargo")}

    def validar(self, titular, datos):
        cargo = _cargo(titular, datos)
        if cargo.origen == Cargo.RECARGO:
            raise ErrorAccion("Un recargo no lleva prórroga.")
        if libro.saldo_de(cargo) <= 0:
            raise ErrorAccion("El cargo ya no tiene saldo.")
        limite = _fecha(datos.get("fecha_limite"), "fecha límite")
        anterior = Prorroga.objects.filter(cargo=cargo).aggregate(m=Max("fecha_limite"))["m"]
        if limite is None or limite <= cargo.vencimiento or (anterior is not None and limite <= anterior):
            raise ErrorAccion("La fecha límite debe ser posterior al vencimiento y a cualquier prórroga anterior.")
        _motivo(datos)
        return cargo, limite

    def aplicar(self, titular, datos, contexto):
        cargo, limite = self.validar(titular, datos)
        prorroga = Prorroga.objects.create(cargo=cargo, fecha_limite=limite, motivo=_motivo(datos)[:300], creada_por=contexto.solicitante, autorizada_por=contexto.autorizador, solicitud=contexto.solicitud)
        contexto.resultado = prorroga
        return {"cargo": str(cargo), "fecha_limite": limite}


class Cancelar(AccionLibro):
    tipo = CancelacionCargo.CANCELACION

    def llave(self, datos):
        return {"datos__cargo": datos.get("cargo")}

    def validar(self, titular, datos):
        cargo = _cargo(titular, datos)
        if self.tipo == CancelacionCargo.CONDONACION and cargo.origen != Cargo.RECARGO:
            raise ErrorAccion("Solo se condonan recargos.")
        if self.tipo == CancelacionCargo.CANCELACION and cargo.origen == Cargo.RECARGO:
            raise ErrorAccion("Para un recargo usa la condonación.")
        importe = _entero(datos.get("importe"), "El importe")
        saldo = libro.saldo_de(cargo)
        if importe <= 0 or importe > saldo:
            raise ErrorAccion(f"El importe debe ser mayor que cero y no pasar del saldo ({formatear(saldo)}).")
        _motivo(datos)
        return cargo, importe

    def aplicar(self, titular, datos, contexto):
        cargo, importe = self.validar(titular, datos)
        contexto.resultado = libro.cancelar_cargo(cargo, importe, self.tipo, _motivo(datos), contexto.ejecutor, contexto.autorizador, contexto.solicitud, contexto.request)
        return {"cargo": str(cargo), "importe": importe}


class Condonar(Cancelar):
    tipo = CancelacionCargo.CONDONACION


class Revertir(AccionLibro):
    admite_interno = True

    def llave(self, datos):
        return {"datos__pago": datos.get("pago")}

    def _cobrador(self, datos):
        return Pago.objects.filter(pk=datos.get("pago")).values_list("registrado_por_id", flat=True).first()

    def exige_solicitud(self, usuario, titular, datos):
        return self._cobrador(datos) == usuario.pk

    def puede_resolver(self, usuario, datos):
        return self._cobrador(datos) != usuario.pk

    def validar(self, titular, datos):
        pago = Pago.objects.filter(pk=datos.get("pago"), titular=titular).first()
        if pago is None:
            raise ErrorAccion("El pago no pertenece a este registro.")
        if ReversionPago.objects.filter(pago=pago).exists():
            raise ErrorAccion("El pago ya fue revertido.")
        _motivo(datos)
        return pago

    def aplicar(self, titular, datos, contexto):
        pago = self.validar(titular, datos)
        turno = None
        if pago.medio == Pago.EFECTIVO:
            responsable = contexto.solicitante if contexto.solicitud is not None else contexto.ejecutor
            turno = turno_abierto(responsable)
            if turno is None:
                raise ErrorAccion(f"Para devolver efectivo, {responsable} necesita un turno de caja abierto.")
        piezas = datos.get("piezas") if pago.medio == Pago.EFECTIVO else None
        contexto.resultado = libro.revertir_pago(pago, _motivo(datos), contexto.ejecutor, turno, contexto.autorizador, contexto.solicitud, contexto.request, piezas=piezas)
        from inventario import servicios as inventario

        regresan = datos.get("regresan") if isinstance(datos.get("regresan"), list) else []
        inventario.tras_reversion(pago, regresan, contexto.ejecutor, contexto.autorizador, contexto.solicitud, contexto.request)
        return {"pago": pago.pk, "importe": pago.importe, "regresan": regresan}


class PagoSobreTope(AccionLibro):
    def llave(self, datos):
        return {"datos__ficha": datos.get("ficha")}

    def validar(self, titular, datos):
        importe = _entero(datos.get("importe"), "El importe")
        if importe <= 0:
            raise ErrorAccion("El importe debe ser mayor que cero.")
        if not datos.get("ficha"):
            raise ErrorAccion("Falta la ficha del pago.")
        return importe

    def aplicar(self, titular, datos, contexto):
        from inventario import servicios as inventario

        importe = self.validar(titular, datos)
        turno = turno_abierto(contexto.solicitante)
        if turno is None:
            raise ErrorAccion(f"{contexto.solicitante} necesita un turno de caja abierto para registrar el pago.")
        venta = inventario.venta_por_cobrar(titular, datos.get("venta")) if datos.get("venta") is not None else None
        try:
            pago = libro.registrar_pago(titular, importe, Pago.EFECTIVO, contexto.solicitante, turno=turno, ficha=datos["ficha"], request=contexto.request, solicitud=contexto.solicitud, piezas=datos.get("piezas"), primero=inventario.cargos_de(venta) if venta else None)
        except libro.ErrorLibro as error:
            raise ErrorAccion(str(error))
        inventario.ligar_pago(venta, pago)
        contexto.resultado = pago
        return {"pago": pago.pk, "importe": importe, "tope": parametro("tope_pago_individual")}
