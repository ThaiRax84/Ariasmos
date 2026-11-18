from django.urls import path

from . import views

app_name = "rezagos"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("exportar/", views.exportar, name="exportar"),
    path("limites/", views.limites, name="limites"),
    path("limites/<int:pk>/", views.excepcion, name="excepcion"),
    path("reglas/", views.reglas, name="reglas"),
    path("reglas/nueva/", views.regla_nueva, name="regla_nueva"),
    path("reglas/<int:pk>/", views.regla_editar, name="regla_editar"),
    path("recargos-tras-el-alta/", views.recargos_alta, name="recargos_alta"),
]
