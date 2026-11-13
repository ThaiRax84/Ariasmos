from django.urls import path

from . import views, vistas_cobro

app_name = "cobros"

urlpatterns = [
    path("cobrar/", vistas_cobro.buscar, name="buscar"),
    path("cobrar/<int:pk>/", vistas_cobro.cobrar, name="cobrar"),
    path("recibos/verificar/", vistas_cobro.verificar, name="verificar"),
    path("recibos/<int:pk>/", vistas_cobro.recibo, name="recibo"),
    path("recibos/<int:pk>/pdf/", vistas_cobro.recibo_pdf, name="recibo_pdf"),
    path("titulares/<int:pk>/cargo-manual/", vistas_cobro.cargo_manual, name="cargo_manual"),
    path("titulares/<int:pk>/beca/", vistas_cobro.beca, name="beca"),
    path("cargos/<int:pk>/prorroga/", vistas_cobro.prorroga, name="prorroga"),
    path("cargos/<int:pk>/cancelar/", vistas_cobro.cancelar, name="cancelar"),
    path("pagos/<int:pk>/revertir/", vistas_cobro.revertir, name="revertir"),
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
