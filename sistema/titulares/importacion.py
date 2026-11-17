from django.db import transaction

from configuracion.models import vocabulario

from . import padron


class ImportacionPadron:
    motivo_obligatoria = "hoja_con_cambios_de_nombre"
    mensaje_propio = "Nadie aprueba su propia hoja."

    def llave(self, datos):
        return {"datos__sha256": datos.get("sha256")}

    def exige_solicitud(self, usuario, titular, datos):
        from solicitudes.models import PoliticaAccion

        if not datos.get("nombres"):
            return False
        politica = PoliticaAccion.objects.filter(accion="correccion_nombre").first()
        return politica is None or not usuario.tiene_permiso_de_rol(politica.permiso_directo)

    def puede_resolver(self, usuario, datos):
        return True

    def validar(self, titular, datos):
        if titular is not None:
            raise padron.ErrorPadron(f"La hoja no se liga a un registro de {vocabulario()['padron_min']}.")
        analisis = padron.leer_hoja(datos.get("hoja", ""), datos.get("huella", ""))
        if not any(not f["errores"] and not f["duplicado"] for f in analisis.get("filas", [])):
            raise padron.ErrorPadron("La hoja no trae nada que aplicar.")
        return analisis

    def aplicar(self, titular, datos, contexto):
        analisis = self.validar(titular, datos)
        lote = padron.aplicar(
            analisis, datos.get("familias", []), contexto.solicitante, datos.get("nombre_archivo", ""), datos.get("sha256", ""),
            request=contexto.request, autorizador=contexto.autorizador, solicitud=contexto.solicitud,
        )
        transaction.on_commit(lambda: padron.borrar_hoja(datos.get("hoja", "")))
        contexto.resultado = lote
        return {"lote": lote.pk, "altas": lote.creados, "actualizados": lote.actualizados, "saltados": lote.resultado.get("saltados", [])}

    def rechazar(self, titular, datos, contexto=None):
        transaction.on_commit(lambda: padron.borrar_hoja(datos.get("hoja", "")))

    def caducar(self, datos):
        padron.borrar_hoja(datos.get("hoja", ""))
