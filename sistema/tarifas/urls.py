from django.urls import path

from . import views

app_name = "tarifas"

urlpatterns = [
    path("", views.indice, name="indice"),
    path("conceptos/<int:pk>/", views.concepto, name="concepto"),
    path("conceptos/<int:pk>/nueva/", views.nueva, name="nueva"),
    path("<int:pk>/", views.editar, name="editar"),
]
