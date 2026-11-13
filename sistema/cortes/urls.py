from django.urls import path, re_path

from . import views

app_name = "cortes"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/", views.detalle, name="detalle"),
    re_path(r"^(?P<pk>\d+)/archivo\.(?P<formato>pdf|csv|json)$", views.descargar, name="descargar"),
    path("<int:pk>/cerrar/", views.cerrar, name="cerrar"),
    path("cobranza/", views.cobranza, name="cobranza"),
    path("destinos/", views.destinos, name="destinos"),
    path("destinos/nuevo/", views.destino_editar, name="destino_nuevo"),
    path("destinos/<int:pk>/", views.destino_editar, name="destino_editar"),
    path("entregas/<int:pk>/reintentar/", views.reintentar, name="reintentar"),
]
