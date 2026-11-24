from django.urls import path

from . import views

urlpatterns = [
    path("v1/salud", views.salud),
    path("v1/activar", views.activar),
    path("v1/renovar", views.renovar),
]
