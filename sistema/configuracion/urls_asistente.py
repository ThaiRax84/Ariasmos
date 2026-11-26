from django.urls import path

from . import asistente

app_name = "asistente"

urlpatterns = [
    path("", asistente.inicio, name="inicio"),
    path("revisar/", asistente.revisar, name="revisar"),
    path("personalizar/", asistente.personalizar, name="personalizar"),
    path("grupos/", asistente.grupos, name="grupos"),
    path("conceptos/", asistente.conceptos, name="conceptos"),
    path("marca/", asistente.marca, name="marca"),
    path("marca/vista.css", asistente.vista_marca_css, name="vista_marca"),
    path("marca/logo", asistente.logo_asistente, name="logo"),
    path("pago/", asistente.pago, name="pago"),
    path("caja/", asistente.caja, name="caja"),
    path("reglas/", asistente.reglas, name="reglas"),
    path("cortes/", asistente.cortes, name="cortes"),
    path("usuario/", asistente.usuario, name="usuario"),
    path("codigo/", asistente.codigo, name="codigo"),
]
