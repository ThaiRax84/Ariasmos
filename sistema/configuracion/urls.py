from django.urls import path, re_path

from . import views, vistas_padron

app_name = "configuracion"

urlpatterns = [
    path("", views.indice, name="indice"),
    path("negocio/", views.negocio, name="negocio"),
    path("marca/", views.marca, name="marca"),
    path("vocabulario/", views.textos, name="vocabulario"),
    path("parametros/", views.parametros, name="parametros"),
    path("avanzado/", views.avanzado, name="avanzado"),
    path("caja/", views.caja, name="caja"),
    path("carpeta-banco/", views.carpeta_banco, name="carpeta_banco"),
    path("inventario/", views.inventario, name="inventario"),
    path("avanzado/moneda/", views.cambiar_moneda, name="moneda"),
    path("padron/", vistas_padron.subir, name="padron_subir"),
    path("padron/lotes/<int:pk>/", vistas_padron.lote, name="padron_lote"),
    re_path(r"^padron/lotes/(?P<pk>\d+)/matriculas\.(?P<formato>xlsx|csv)$", vistas_padron.matriculas, name="padron_matriculas"),
    path("padron/lotes/<int:pk>/fichas.pdf", vistas_padron.fichas, name="padron_fichas"),
    path("padron/<str:token>/", vistas_padron.revisar, name="padron_revisar"),
    path("exportar-plantilla/", views.exportar, name="exportar"),
    path("catalogos/<slug:catalogo>/", views.catalogo, name="catalogo"),
    path("catalogos/<slug:catalogo>/nuevo/", views.catalogo_nuevo, name="catalogo_nuevo"),
    path("catalogos/<slug:catalogo>/<int:pk>/", views.catalogo_editar, name="catalogo_editar"),
]
