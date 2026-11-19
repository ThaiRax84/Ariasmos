from django.urls import path

from . import views

urlpatterns = [
    path("ir/", views.ir, name="ir"),
]
