from django.urls import path

from . import views

app_name = "inventario"

urlpatterns = [
    path("", views.indice, name="indice"),
    path("articulos/", views.articulos, name="articulos"),
    path("articulos/nuevo/", views.articulo_nuevo, name="articulo_nuevo"),
    path("articulos/<int:pk>/", views.articulo_editar, name="articulo_editar"),
    path("vender/", views.vender, name="vender"),
    path("vender/publico/", views.vender_publico, name="vender_publico"),
    path("vender/<int:pk>/", views.vender_titular, name="vender_titular"),
    path("ventas/", views.ventas, name="ventas"),
    path("ventas/<int:pk>/", views.venta, name="venta"),
    path("ventas/<int:pk>/devolver/", views.devolver_venta, name="devolver_venta"),
    path("devolver/", views.devolver, name="devolver"),
    path("movimientos/nuevo/", views.registro_nuevo, name="registro_nuevo"),
    path("movimientos/<int:pk>/", views.registro, name="registro"),
    path("movimientos/<int:pk>/comprobante/", views.registro_comprobante, name="registro_comprobante"),
    path("movimientos/<int:pk>/descargar/", views.registro_descargar, name="registro_descargar"),
    path("movimientos/<int:pk>/revisar/", views.registro_revisar, name="registro_revisar"),
    path("devoluciones/<int:pk>/revisar/", views.devolucion_revisar, name="devolucion_revisar"),
    path("ventas/renglones/<int:pk>/revisar/", views.renglon_revisar, name="renglon_revisar"),
    path("revision/", views.revision, name="revision"),
    path("existencias.csv", views.existencias_csv, name="existencias_csv"),
    path("conteo/", views.conteo, name="conteo"),
    path("conteo/lista-para-contar.csv", views.conteo_lista, name="conteo_lista"),
    path("conteos/<int:pk>/", views.conteo_detalle, name="conteo_detalle"),
]
