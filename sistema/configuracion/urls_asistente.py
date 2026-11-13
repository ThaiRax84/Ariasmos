from django.urls import path

from . import asistente

app_name = "asistente"

urlpatterns = [
    path("", asistente.inicio, name="inicio"),
    path("revisar/", asistente.revisar, name="revisar"),
    path("personalizar/", asistente.personalizar, name="personalizar"),
    path("conceptos/", asistente.conceptos, name="conceptos"),
    path("pago/", asistente.pago, name="pago"),
    path("cortes/", asistente.cortes, name="cortes"),
    path("usuario/", asistente.usuario, name="usuario"),
    path("codigo/", asistente.codigo, name="codigo"),
]
