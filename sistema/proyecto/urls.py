from django.urls import include, path

from cuentas import views as cuentas_views

from . import vistas

urlpatterns = [
    path("", vistas.inicio, name="inicio"),
    path("asistente/", include("configuracion.urls_asistente")),
    path("dispositivo/pendiente/", cuentas_views.dispositivo_pendiente, name="dispositivo_pendiente"),
    path("cuentas/", include("cuentas.urls")),
    path("titulares/", include("titulares.urls")),
    path("solicitudes/", include("solicitudes.urls")),
    path("cobros/", include("cobros.urls")),
    path("caja/", include("caja.urls")),
    path("configuracion/cuentas/", include("banco.urls")),
    path("banco/", include("banco.urls_conciliacion")),
    path("configuracion/", include("configuracion.urls")),
    path("auditoria/", include("auditoria.urls")),
    path("cortes/", include("cortes.urls")),
    path("respaldos/", include("respaldos.urls")),
]
