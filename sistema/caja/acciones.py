from .models import RetiroCaja, Turno
from .servicios import ErrorCaja, neto_de, recibe_movimientos, turno_abierto


class ErrorAccion(ValueError):
    pass


def _entero(valor, nombre):
    if type(valor) is not int:
        raise ErrorAccion(f"{nombre} debe ser un número entero.")
    return valor


class AccionCaja:
    def llave(self, datos):
        return {}

    def exige_solicitud(self, usuario, titular, datos):
        return True

    def puede_resolver(self, usuario, datos):
        return True

    def rechazar(self, titular, datos, contexto=None):
        pass


class RetiroSobreTope(AccionCaja):
    motivo_obligatoria = "retiro_fuera_de_topes"
    mensaje_propio = "Nadie resuelve su propio retiro."

    def llave(self, datos):
        return {"datos__ficha": datos.get("ficha")}

    def validar(self, titular, datos):
        from . import retiros

        if titular is not None:
            raise ErrorAccion("Un retiro de caja no corresponde a un registro del padrón.")
        if set(datos) - {"turno", "importe", "motivo", "nota", "piezas", "ficha", "excede"}:
            raise ErrorAccion("La solicitud de retiro trae datos no permitidos.")
        importe = _entero(datos.get("importe"), "El importe")
        if importe <= 0:
            raise ErrorAccion("El importe debe ser mayor que cero.")
        if not isinstance(datos.get("ficha"), str) or not datos["ficha"]:
            raise ErrorAccion("Falta la ficha del retiro.")
        if not isinstance(datos.get("nota", ""), str):
            raise ErrorAccion("La nota no es válida.")
        try:
            motivo = retiros._motivo(datos.get("motivo"))
            piezas = retiros.validar_piezas(datos.get("piezas"), importe)
        except ErrorCaja as error:
            raise ErrorAccion(str(error))
        return importe, motivo, piezas

    def aplicar(self, titular, datos, contexto):
        from . import retiros

        importe, motivo, piezas = self.validar(titular, datos)
        turno = Turno.objects.select_related("caja").filter(pk=datos.get("turno"), usuario=contexto.solicitante, estado=Turno.ABIERTO).first()
        if turno is None or not recibe_movimientos(turno):
            raise ErrorAccion("El turno del retiro ya no está abierto: hay que pedir un retiro nuevo.")
        if importe > neto_de(turno):
            raise ErrorAccion("El turno no tiene efectivo suficiente para este retiro.")
        retiro = retiros.crear(turno, contexto.solicitante, importe, motivo, datos.get("nota", ""), piezas, contexto.request, contexto.solicitud, contexto.autorizador)
        contexto.resultado = retiro
        return {"retiro": retiro.pk, "folio": str(retiro)}


class RevertirRetiro(AccionCaja):
    motivo_obligatoria = "reversion_de_retiro"
    mensaje_propio = "Nadie resuelve la reversión de un retiro que él mismo hizo."

    def llave(self, datos):
        return {"datos__retiro": datos.get("retiro")}

    def _retiro(self, datos):
        return RetiroCaja.objects.filter(pk=datos.get("retiro")).select_related("registrado_por").first() if type(datos.get("retiro")) is int else None

    def puede_resolver(self, usuario, datos):
        retiro = self._retiro(datos)
        return retiro is not None and retiro.registrado_por_id != usuario.pk

    def validar(self, titular, datos):
        if titular is not None:
            raise ErrorAccion("Un retiro de caja no corresponde a un registro del padrón.")
        if set(datos) - {"retiro", "motivo", "piezas"}:
            raise ErrorAccion("La solicitud trae datos no permitidos.")
        retiro = self._retiro(datos)
        if retiro is None:
            raise ErrorAccion("El retiro no existe.")
        if retiro.revertido:
            raise ErrorAccion("El retiro ya fue revertido.")
        motivo = (datos.get("motivo") or "").strip() if isinstance(datos.get("motivo"), str) else ""
        if not motivo:
            raise ErrorAccion("Indica el motivo.")
        return retiro, motivo

    def aplicar(self, titular, datos, contexto):
        from . import retiros

        retiro, motivo = self.validar(titular, datos)
        turno = turno_abierto(contexto.solicitante)
        if turno is None:
            raise ErrorAccion(f"Para regresar el efectivo, {contexto.solicitante} necesita un turno de caja abierto.")
        try:
            contexto.resultado = retiros.revertir(retiro, motivo, contexto.ejecutor, turno, contexto.autorizador, contexto.solicitud, contexto.request, datos.get("piezas"))
        except ErrorCaja as error:
            raise ErrorAccion(str(error))
        return {"retiro": retiro.pk, "folio": str(retiro), "importe": retiro.importe}
