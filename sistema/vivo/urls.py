from django.urls import path

from . import views

urlpatterns = [
    path("ir/", views.ir, name="ir"),
]
urlpatterns += [
    path("pulso", views.pulso, name="pulso"),
    path("ultimo/", views.ultimo, name="ultimo"),
]
