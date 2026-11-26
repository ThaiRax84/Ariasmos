from django.urls import path

from . import views

app_name = "mensajes"

urlpatterns = [
    path("", views.panel, name="panel"),
    path("tope/", views.tope, name="tope"),
    path("avisos/", views.avisos, name="avisos"),
    path("avisos/nuevo/", views.aviso_nuevo, name="aviso_nuevo"),
    path("avisos/faltan/", views.faltan, name="faltan"),
    path("avisos/<int:pk>/", views.aviso, name="aviso"),
    path("plantillas/nueva/", views.plantilla_nueva, name="plantilla_nueva"),
    path("plantillas/<slug:clave>/", views.plantilla, name="plantilla"),
    path("recibo/<int:pk>/enviar/", views.enviar_recibo, name="enviar_recibo"),
]
