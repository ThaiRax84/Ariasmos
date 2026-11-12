from django.urls import path

from . import asistente

app_name = "asistente"

urlpatterns = [
    path("", asistente.inicio, name="inicio"),
    path("conceptos/", asistente.conceptos, name="conceptos"),
    path("usuario/", asistente.usuario, name="usuario"),
    path("codigo/", asistente.codigo, name="codigo"),
]
