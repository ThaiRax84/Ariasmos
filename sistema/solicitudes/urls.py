from django.urls import path

from . import views

app_name = "solicitudes"

urlpatterns = [
    path("", views.bandeja, name="bandeja"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/aprobar/", views.aprobar, name="aprobar"),
    path("<int:pk>/rechazar/", views.rechazar, name="rechazar"),
    path("<int:pk>/codigo/", views.codigo, name="codigo"),
    path("politicas/", views.politicas, name="politicas"),
    path("politicas/<int:pk>/", views.politica_editar, name="politica_editar"),
]
