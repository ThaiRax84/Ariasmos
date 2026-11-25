from django.urls import path, re_path

from . import views

urlpatterns = [
    path("v1/mensajes/estado", views.estado),
    path("v1/mensajes/plantilla", views.plantilla),
    path("v1/mensajes/tope", views.tope),
    path("v1/mensajes/enviar", views.enviar),
    path("v1/mensajes/consultar", views.consultar),
    re_path(r"^v1/documentos/(?P<token>[A-Za-z0-9_-]{43})\.pdf$", views.documento),
    path("v1/twilio/estado/<uuid:identificador>", views.estado_twilio),
    path("v1/twilio/entrante/<uuid:identificador>", views.entrante_twilio),
]
