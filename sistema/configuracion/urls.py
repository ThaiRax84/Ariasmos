from django.urls import path

from . import views

app_name = "configuracion"

urlpatterns = [
    path("", views.indice, name="indice"),
    path("negocio/", views.negocio, name="negocio"),
    path("vocabulario/", views.textos, name="vocabulario"),
    path("parametros/", views.parametros, name="parametros"),
    path("catalogos/<slug:catalogo>/", views.catalogo, name="catalogo"),
    path("catalogos/<slug:catalogo>/nuevo/", views.catalogo_nuevo, name="catalogo_nuevo"),
    path("catalogos/<slug:catalogo>/<int:pk>/", views.catalogo_editar, name="catalogo_editar"),
]
