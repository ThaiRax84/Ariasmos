from django.urls import path

from . import views

urlpatterns = [
    path("entrar/", views.entrar, name="entrar"),
    path("entrar/codigo/", views.entrar_codigo, name="entrar_codigo"),
    path("activar/", views.activar, name="activar"),
    path("salir/", views.salir, name="salir"),
    path("confirmar/", views.confirmar, name="confirmar"),
    path("totp/", views.alta_totp, name="totp"),
    path("contrasena/", views.cambiar_contrasena, name="contrasena"),
    path("autorizaciones/", views.autorizaciones, name="autorizaciones"),
    path("autorizaciones/<int:pk>/revisar/", views.revisar_autorizacion, name="revisar_autorizacion"),
    path("autorizaciones/avisos/<int:pk>/enterado/", views.aviso_enterado, name="aviso_enterado"),
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/nuevo/", views.usuario_nuevo, name="usuario_nuevo"),
    path("usuarios/<int:pk>/", views.usuario_editar, name="usuario_editar"),
    path("roles/", views.roles, name="roles"),
    path("roles/nuevo/", views.rol_nuevo, name="rol_nuevo"),
    path("roles/<int:pk>/", views.rol_editar, name="rol_editar"),
    path("dispositivos/", views.dispositivos, name="dispositivos"),
    path("conectar/", views.conectar, name="conectar"),
    path("conectar/ariasmos-servidor.crt", views.conectar_certificado, name="conectar_certificado"),
    path("conectar/instalar-certificado.cmd", views.conectar_instalador, name="conectar_instalador"),
    path("dispositivos/descartar/", views.dispositivos_descartar, name="dispositivos_descartar"),
    path("dispositivos/<int:pk>/aprobar/", views.dispositivo_aprobar, name="dispositivo_aprobar"),
    path("dispositivos/<int:pk>/revocar/", views.dispositivo_revocar, name="dispositivo_revocar"),
    path("delegaciones/", views.delegaciones, name="delegaciones"),
    path("delegaciones/nueva/", views.delegacion_nueva, name="delegacion_nueva"),
    path("delegaciones/<int:pk>/revocar/", views.delegacion_revocar, name="delegacion_revocar"),
]
