from django.urls import path

from . import views

app_name = "cobros"

urlpatterns = [
    path("conceptos/", views.conceptos, name="conceptos"),
    path("conceptos/nuevo/", views.concepto_nuevo, name="concepto_nuevo"),
    path("conceptos/<int:pk>/", views.concepto_editar, name="concepto_editar"),
    path("recargos/", views.reglas, name="reglas"),
    path("recargos/nuevo/", views.regla_nueva, name="regla_nueva"),
    path("recargos/<int:pk>/", views.regla_editar, name="regla_editar"),
    path("planes/", views.planes, name="planes"),
    path("planes/nuevo/", views.plan_nuevo, name="plan_nuevo"),
    path("planes/<int:pk>/", views.plan_editar, name="plan_editar"),
]
