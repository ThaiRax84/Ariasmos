from django.urls import path

from . import views

app_name = "titulares"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nuevo/", views.nuevo, name="nuevo"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/historial/", views.ver_historial, name="historial"),
    path("<int:pk>/ficha-pago/", views.ficha_pago, name="ficha_pago"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/contactos/nuevo/", views.contacto_nuevo, name="contacto_nuevo"),
    path("<int:pk>/contactos/<int:contacto_pk>/", views.contacto_editar, name="contacto_editar"),
    path("<int:pk>/baja/", views.baja, name="baja"),
    path("<int:pk>/reactivar/", views.reactivar, name="reactivar"),
    path("<int:pk>/solicitar-alta/", views.solicitar_alta, name="solicitar_alta"),
]
