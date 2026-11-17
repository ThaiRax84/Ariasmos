from django.urls import path

from . import views

app_name = "actualizaciones"

urlpatterns = [
    path("", views.configurar, name="configurar"),
    path("buscar/", views.buscar, name="buscar"),
    path("descargar/", views.descargar, name="descargar"),
]
