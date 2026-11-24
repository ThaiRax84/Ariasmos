from django.urls import include, path

handler400 = "emision.views.peticion_invalida"
handler404 = "emision.views.no_encontrada"

urlpatterns = [path("", include("emision.urls"))]
