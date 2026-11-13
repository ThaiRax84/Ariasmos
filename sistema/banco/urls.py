from django.urls import path

from . import views

app_name = "banco"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nueva/", views.nueva, name="nueva"),
    path("<int:pk>/", views.editar, name="editar"),
]
