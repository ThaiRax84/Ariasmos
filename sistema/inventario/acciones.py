from caja.servicios import turno_abierto

from .models import Conteo, Devolucion, Venta


class ErrorAccion(ValueError):
    pass


class AccionInventario:
    def llave(self, datos):
        return {}

    def exige_solicitud(self, usuario, titular, datos):
        return True

    def puede_resolver(self, usuario, datos):
        return True

    def rechazar(self, titular, datos, contexto=None):
        pass


class ConteoInventario(AccionInventario):
    motivo_obligatoria = "conteo_de_inventario"
    mensaje_propio = "Nadie aprueba su propio conteo."

    def llave(self, datos):
        return {"datos__conteo": datos.get("conteo")}

    def _conteo(self, datos):
        return Conteo.objects.filter(pk=datos.get("conteo")).first() if type(datos.get("conteo")) is int else None

    def puede_resolver(self, usuario, datos):
        conteo = self._conteo(datos)
        return conteo is not None and conteo.usuario_id != usuario.pk

    def validar(self, titular, datos):
        if titular is not None:
            raise ErrorAccion("Un conteo de inventario no corresponde a un registro del padrón.")
        if set(datos) != {"conteo"}:
            raise ErrorAccion("La solicitud trae datos no permitidos.")
        conteo = self._conteo(datos)
        if conteo is None:
            raise ErrorAccion("El conteo no existe.")
        if conteo.aplicado_en is not None:
            raise ErrorAccion("El conteo ya se aplicó.")
        return conteo

    def aplicar(self, titular, datos, contexto):
        from . import servicios

        conteo = self.validar(titular, datos)
        ajustes = servicios.aplicar_conteo(conteo, contexto.autorizador, contexto.request)
        contexto.resultado = conteo
        return {"conteo": conteo.pk, "ajustes": ajustes}


class DevolucionEfectivo(AccionInventario):
    motivo_obligatoria = "devolucion_en_efectivo"
    mensaje_propio = "Nadie resuelve una devolución en efectivo que pidió, ni la de una venta que cobró."

    def llave(self, datos):
        return {"datos__venta": datos.get("venta")}

    def _venta(self, datos):
        return Venta.objects.filter(pk=datos.get("venta")).select_related("pago", "titular").first() if type(datos.get("venta")) is int else None

    def puede_resolver(self, usuario, datos):
        venta = self._venta(datos)
        if venta is None:
            return False
        return venta.pago is None or venta.pago.registrado_por_id != usuario.pk

    def validar(self, titular, datos):
        from . import servicios

        if titular is not None:
            raise ErrorAccion("Una devolución de artículos no corresponde a un registro del padrón.")
        if set(datos) - {"venta", "renglones", "motivo", "piezas"} or not {"venta", "renglones", "motivo"} <= set(datos):
            raise ErrorAccion("La solicitud trae datos no permitidos.")
        venta = self._venta(datos)
        if venta is None:
            raise ErrorAccion("La venta no existe.")
        if not isinstance(datos.get("motivo"), str) or not datos["motivo"].strip():
            raise ErrorAccion("Indica el motivo.")
        try:
            servicios.validar_devolucion(venta, datos.get("renglones"), incluir_pendientes=False)
        except servicios.ErrorInventario as error:
            raise ErrorAccion(str(error))
        if not servicios.en_plazo(venta):
            raise ErrorAccion("La venta está fuera del plazo de devolución.")
        return venta

    def aplicar(self, titular, datos, contexto):
        from . import servicios

        venta = self.validar(titular, datos)
        turno = turno_abierto(contexto.solicitante)
        if turno is None:
            raise ErrorAccion(f"Para entregar el efectivo, {contexto.solicitante} necesita su turno de caja abierto.")
        try:
            devolucion = servicios.devolver(
                venta, datos["renglones"], Devolucion.EFECTIVO, contexto.solicitante, datos["motivo"], contexto.request, turno=turno,
                solicitud=contexto.solicitud, autorizador=contexto.autorizador, piezas=datos.get("piezas"),
            )
        except servicios.ErrorInventario as error:
            raise ErrorAccion(str(error))
        contexto.resultado = devolucion
        return {"devolucion": devolucion.pk, "venta": str(venta), "importe": devolucion.importe_dinero}
