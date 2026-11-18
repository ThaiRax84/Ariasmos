from cobros import libro
from cobros.models import Cargo, ConceptoCobro
from configuracion.models import hoy_negocio, vocabulario
from configuracion.moneda import formatear
from tarifas import servicios as tarifas
from titulares.models import Titular

MAXIMO_IMPORTE = 10 ** 12
MAXIMO_RENGLONES = 30


class ErrorAccion(ValueError):
    pass


class SinCredito:
    motivo_obligatoria = "sin_credito"
    mensaje_propio = "Nadie aprueba su propia solicitud."

    def llave(self, datos):
        return {}

    def exige_solicitud(self, usuario, titular, datos):
        return True

    def puede_resolver(self, usuario, datos):
        return True

    def rechazar(self, titular, datos, contexto=None):
        pass

    def _titular(self, titular):
        if titular is None or titular.estado not in (Titular.ACTIVO, Titular.PENDIENTE):
            raise ErrorAccion(f"Solo aplica a {vocabulario()['titular_min']} activo o pendiente de alta.")


class CargoSinCredito(SinCredito):
    def llave(self, datos):
        return {"datos__concepto": datos.get("concepto")}

    def validar(self, titular, datos):
        self._titular(titular)
        if set(datos) != {"concepto", "cantidad", "importe_unitario"}:
            raise ErrorAccion("La solicitud trae datos no permitidos.")
        concepto = ConceptoCobro.objects.filter(pk=datos.get("concepto"), activo=True, tipo=ConceptoCobro.POR_EVENTO).first() if type(datos.get("concepto")) is int else None
        if concepto is None:
            raise ErrorAccion("El concepto no existe o no está activo.")
        cantidad = datos.get("cantidad")
        error = tarifas.error_cargo(concepto, titular, cantidad)
        if error:
            raise ErrorAccion(error)
        unitario = datos.get("importe_unitario")
        if type(unitario) is not int or not 0 < unitario < MAXIMO_IMPORTE:
            raise ErrorAccion("El importe por unidad no es válido.")
        return concepto, cantidad, unitario

    def aplicar(self, titular, datos, contexto):
        concepto, cantidad, unitario = self.validar(titular, datos)
        descripcion = tarifas.descripcion_cargo(concepto, cantidad)
        cargo = libro.crear_cargo(titular, concepto, unitario * cantidad, hoy_negocio(), Cargo.MANUAL, descripcion=descripcion, cantidad=cantidad, usuario=contexto.solicitante, request=contexto.request)
        if cargo is None:
            raise ErrorAccion("No se pudo crear el cargo.")
        contexto.resultado = cargo
        return {"cargo": str(cargo), "importe": cargo.importe_final}


class VentaSinCredito(SinCredito):
    def _renglones(self, datos):
        renglones = datos.get("renglones")
        if not isinstance(renglones, list) or not 0 < len(renglones) <= MAXIMO_RENGLONES:
            raise ErrorAccion("La venta no trae artículos válidos.")
        limpios = []
        for renglon in renglones:
            if not (isinstance(renglon, list) and len(renglon) == 2 and all(type(v) is int for v in renglon)):
                raise ErrorAccion("La venta no trae artículos válidos.")
            limpios.append((renglon[0], renglon[1]))
        return limpios

    def validar(self, titular, datos):
        from inventario import servicios as inventario

        self._titular(titular)
        if set(datos) != {"renglones"}:
            raise ErrorAccion("La solicitud trae datos no permitidos.")
        inventario.exigir_activo()
        renglones = self._renglones(datos)
        inventario.validar_renglones(renglones)
        return renglones

    def aplicar(self, titular, datos, contexto):
        from inventario import servicios as inventario
        from inventario.models import Venta

        renglones = self.validar(titular, datos)
        venta = inventario.vender(titular, renglones, Venta.ADEUDO, contexto.solicitante, contexto.request)
        contexto.resultado = venta
        return {"venta": str(venta), "total": venta.total}


def describir(solicitud):
    from inventario.models import Articulo

    datos = solicitud.datos or {}
    filas = []
    if solicitud.accion == "cargo_sin_credito":
        concepto = ConceptoCobro.objects.filter(pk=datos.get("concepto")).first()
        cantidad = int(datos.get("cantidad") or 0)
        unitario = int(datos.get("importe_unitario") or 0)
        filas += [("Concepto", str(concepto) if concepto else "—"), ("Cantidad", str(cantidad)), ("Importe por unidad", formatear(unitario)), ("Importe", formatear(unitario * cantidad))]
    elif solicitud.accion == "venta_sin_credito":
        renglones = [r for r in datos.get("renglones") or [] if isinstance(r, list) and len(r) == 2]
        articulos = {a.pk: a for a in Articulo.objects.filter(pk__in=[r[0] for r in renglones])}
        filas.append(("Artículos", "; ".join(f"{articulos[r[0]].nombre} × {r[1]}" for r in renglones if r[0] in articulos)))
        filas.append(("Total al precio de hoy", formatear(sum(articulos[r[0]].precio * r[1] for r in renglones if r[0] in articulos))))
    filas.append(("Por qué es solicitud", f"{vocabulario()['titular']} sin crédito: rebasó su límite de adeudo o una regla de rezago le quita el crédito."))
    return filas
