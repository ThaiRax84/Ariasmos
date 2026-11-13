from django.urls import path

from . import views

app_name = "caja"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("abrir/", views.abrir, name="abrir"),
    path("turnos/<int:pk>/", views.turno, name="turno"),
    path("turnos/<int:pk>/cerrar/", views.cerrar, name="cerrar"),
    path("traslados/", views.traslados, name="traslados"),
    path("traslados/entrega/", views.entrega, name="entrega"),
    path("traslados/deposito/", views.deposito, name="deposito"),
    path("traslados/<int:pk>/confirmar/", views.confirmar, name="confirmar"),
    path("traslados/<int:pk>/rechazar/", views.rechazar, name="rechazar"),
    path("custodia/", views.custodia, name="custodia"),
]
