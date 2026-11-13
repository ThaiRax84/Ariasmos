from django.urls import path

from . import views

app_name = "caja"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("abrir/", views.abrir, name="abrir"),
    path("turnos/<int:pk>/", views.turno, name="turno"),
    path("turnos/<int:pk>/cerrar/", views.cerrar, name="cerrar"),
    path("turnos/<int:pk>/reconteo/", views.reconteo, name="reconteo"),
    path("traslados/", views.traslados, name="traslados"),
    path("traslados/entrega/", views.entrega, name="entrega"),
    path("traslados/deposito/", views.deposito, name="deposito"),
    path("traslados/<int:pk>/confirmar/", views.confirmar, name="confirmar"),
    path("traslados/<int:pk>/rechazar/", views.rechazar, name="rechazar"),
    path("custodia/", views.custodia, name="custodia"),
    path("retiros/", views.lista_retiros, name="retiros"),
    path("retiros/nuevo/", views.retiro_nuevo, name="retiro_nuevo"),
    path("retiros/<int:pk>/", views.retiro, name="retiro"),
    path("retiros/<int:pk>/comprobante/", views.retiro_comprobante, name="retiro_comprobante"),
    path("retiros/<int:pk>/sin-comprobante/", views.retiro_sin_comprobante, name="retiro_sin_comprobante"),
    path("retiros/<int:pk>/descargar/", views.retiro_descargar, name="retiro_descargar"),
    path("retiros/<int:pk>/revisar/", views.retiro_revisar, name="retiro_revisar"),
    path("retiros/<int:pk>/revertir/", views.retiro_revertir, name="retiro_revertir"),
    path("motivos-retiro/", views.motivos, name="motivos"),
    path("motivos-retiro/nuevo/", views.motivo_nuevo, name="motivo_nuevo"),
    path("motivos-retiro/<int:pk>/", views.motivo_editar, name="motivo_editar"),
]
