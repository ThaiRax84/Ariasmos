from django.urls import path

from . import views

app_name = "respaldos"

urlpatterns = [
    path("", views.panel, name="panel"),
    path("carpeta/", views.carpeta, name="carpeta"),
    path("respaldar/", views.respaldar, name="respaldar"),
    path("probar/", views.probar, name="probar"),
    path("clave/", views.clave, name="clave"),
    path("clave/nueva/", views.clave_nueva, name="clave_nueva"),
]
