from django.urls import path

from . import vistas_conciliacion as vistas

app_name = "conciliacion"

urlpatterns = [
    path("importar/", vistas.importar, name="importar"),
    path("importar/<str:token>/columnas/", vistas.columnas, name="columnas"),
    path("importar/<str:token>/", vistas.previa, name="previa"),
    path("importaciones/", vistas.importaciones, name="importaciones"),
    path("importaciones/<int:pk>/", vistas.importacion, name="importacion"),
    path("cola/", vistas.cola, name="cola"),
    path("movimientos/<int:pk>/", vistas.movimiento, name="movimiento"),
    path("movimientos/<int:pk>/proponer/", vistas.proponer, name="proponer"),
    path("movimientos/<int:pk>/confirmar/", vistas.confirmar, name="confirmar"),
    path("movimientos/<int:pk>/no-cobro/", vistas.no_cobro, name="no_cobro"),
    path("movimientos/<int:pk>/emparejar/", vistas.emparejar, name="emparejar"),
]
