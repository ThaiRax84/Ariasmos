import pytest
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from django.utils import timezone

from banco.models import Banco, CargaTemporal, CuentaBancaria, Importacion, MovimientoBancario
from caja import retiros
from caja.models import Caja, MotivoRetiro, Traslado
from caja.servicios import abrir_turno
from cobros import libro
from cobros.models import ConceptoCobro, PlanCobro, ReglaRecargo
from configuracion.models import Parametro
from cortes.models import Corte, Destino, Entrega
from inventario import servicios as inventario
from inventario.models import Articulo, Conteo, Devolucion, Venta
from cuentas.models import CodigoUsado, Delegacion, Dispositivo, Rol
from solicitudes.models import PoliticaAccion, Solicitud
from titulares.models import Agrupacion, Contacto, Familia, LotePadron, Titular
from titulares.servicios import crear_titular

from .conftest import cliente, configurar, nuevo_usuario

ROLES = ("Operación", "Supervisión", "Dirección")

PUBLICAS = {"entrar", "entrar_codigo", "activar", "dispositivo_pendiente", "asistente:inicio", "asistente:revisar", "asistente:personalizar", "asistente:conceptos", "asistente:pago", "asistente:caja", "asistente:cortes", "asistente:usuario", "asistente:codigo"}

SOLO_SESION = {"inicio", "marca_css", "marca_logo", "salir", "confirmar", "totp", "contrasena", "autorizaciones", "revisar_autorizacion", "aviso_enterado", "actualizaciones:descargar"}

MATRIZ = {
    "titulares:lista": ("ver_titulares",),
    "titulares:nuevo": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:detalle": ("ver_titulares",),
    "titulares:ficha_pago": ("ver_titulares",),
    "titulares:historial": ("ver_titulares",),
    "titulares:editar": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:contacto_nuevo": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:contacto_editar": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:baja": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:reactivar": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:solicitar_alta": ("solicitar_alta_baja", "alta_baja_directa"),
    "solicitudes:bandeja": ("solicitar_alta_baja", "alta_baja_directa", "aprobar_solicitudes"),
    "solicitudes:detalle": ("solicitar_alta_baja", "alta_baja_directa", "aprobar_solicitudes"),
    "solicitudes:aprobar": ("aprobar_solicitudes",),
    "solicitudes:rechazar": ("aprobar_solicitudes",),
    "solicitudes:codigo": ("solicitar_alta_baja",),
    "solicitudes:politicas": ("administrar_politicas",),
    "solicitudes:politica_editar": ("administrar_politicas",),
    "usuarios": ("administrar_usuarios",),
    "usuario_nuevo": ("administrar_usuarios",),
    "usuario_editar": ("administrar_usuarios",),
    "roles": ("administrar_roles",),
    "rol_nuevo": ("administrar_roles",),
    "rol_editar": ("administrar_roles",),
    "dispositivos": ("aprobar_dispositivos",),
    "conectar": ("aprobar_dispositivos",),
    "conectar_certificado": ("aprobar_dispositivos",),
    "conectar_instalador": ("aprobar_dispositivos",),
    "dispositivos_descartar": ("aprobar_dispositivos",),
    "dispositivo_aprobar": ("aprobar_dispositivos",),
    "dispositivo_revocar": ("aprobar_dispositivos",),
    "delegaciones": ("otorgar_delegaciones",),
    "delegacion_nueva": ("otorgar_delegaciones",),
    "delegacion_revocar": ("otorgar_delegaciones",),
    "cobros:conceptos": ("administrar_conceptos",),
    "cobros:concepto_nuevo": ("administrar_conceptos",),
    "cobros:concepto_editar": ("administrar_conceptos",),
    "cobros:reglas": ("administrar_conceptos",),
    "cobros:regla_nueva": ("administrar_conceptos",),
    "cobros:regla_editar": ("administrar_conceptos",),
    "cobros:planes": ("administrar_conceptos",),
    "cobros:plan_nuevo": ("administrar_conceptos",),
    "cobros:plan_editar": ("administrar_conceptos",),
    "configuracion:indice": ("administrar_configuracion",),
    "configuracion:negocio": ("administrar_configuracion",),
    "configuracion:marca": ("administrar_configuracion",),
    "configuracion:vocabulario": ("administrar_configuracion",),
    "configuracion:parametros": ("administrar_configuracion",),
    "configuracion:catalogo": ("administrar_configuracion",),
    "configuracion:catalogo_nuevo": ("administrar_configuracion",),
    "configuracion:catalogo_editar": ("administrar_configuracion",),
    "configuracion:avanzado": ("administrar_configuracion",),
    "configuracion:moneda": ("administrar_configuracion",),
    "configuracion:exportar": ("administrar_configuracion",),
    "banco:lista": ("administrar_configuracion",),
    "banco:nueva": ("administrar_configuracion",),
    "banco:editar": ("administrar_configuracion",),
    "titulares:familias": ("ver_titulares",),
    "titulares:familia": ("ver_titulares",),
    "titulares:familia_contacto_nuevo": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:familia_contacto_editar": ("solicitar_alta_baja", "alta_baja_directa"),
    "titulares:cambiar_familia": ("solicitar_alta_baja", "alta_baja_directa"),
    "cobros:buscar": ("registrar_pago_efectivo",),
    "cobros:cobrar": ("registrar_pago_efectivo",),
    "cobros:recibo": ("ver_titulares",),
    "cobros:recibo_pdf": ("ver_titulares",),
    "cobros:verificar": ("ver_titulares",),
    "cobros:cargo_manual": ("cargo_manual",),
    "cobros:beca": ("solicitar_ajustes", "aplicar_ajustes"),
    "cobros:prorroga": ("solicitar_ajustes", "aplicar_ajustes"),
    "cobros:cancelar": ("solicitar_ajustes", "aplicar_ajustes"),
    "cobros:revertir": ("solicitar_ajustes", "aplicar_ajustes"),
    "caja:inicio": ("turno_caja",),
    "caja:abrir": ("turno_caja",),
    "caja:turno": ("turno_caja", "recibir_efectivo"),
    "caja:cerrar": ("turno_caja",),
    "caja:traslados": ("turno_caja", "recibir_efectivo"),
    "caja:entrega": ("turno_caja", "recibir_efectivo"),
    "caja:deposito": ("turno_caja", "recibir_efectivo"),
    "caja:confirmar": ("recibir_efectivo",),
    "caja:rechazar": ("recibir_efectivo",),
    "caja:custodia": ("recibir_efectivo",),
    "caja:reconteo": ("turno_caja",),
    "caja:retiros": ("retirar_efectivo", "revisar_retiros"),
    "caja:retiro_nuevo": ("retirar_efectivo",),
    "caja:retiro": ("retirar_efectivo", "revisar_retiros"),
    "caja:retiro_comprobante": ("retirar_efectivo",),
    "caja:retiro_sin_comprobante": ("retirar_efectivo",),
    "caja:retiro_descargar": ("retirar_efectivo", "revisar_retiros"),
    "caja:retiro_revisar": ("revisar_retiros",),
    "caja:retiro_revertir": ("retirar_efectivo", "revisar_retiros"),
    "caja:motivos": ("administrar_motivos_retiro",),
    "caja:motivo_nuevo": ("administrar_motivos_retiro",),
    "caja:motivo_editar": ("administrar_motivos_retiro",),
    "configuracion:caja": ("administrar_configuracion",),
    "configuracion:carpeta_banco": ("administrar_configuracion",),
    "conciliacion:liberar": ("conciliar_banco",),
    "auditoria:lista": ("ver_auditoria",),
    "auditoria:verificar": ("ver_auditoria",),
    "titulares:estado_pdf": ("ver_titulares",),
    "titulares:familia_estado_pdf": ("ver_titulares",),
    "conciliacion:importar": ("conciliar_banco",),
    "conciliacion:columnas": ("conciliar_banco",),
    "conciliacion:previa": ("conciliar_banco",),
    "conciliacion:importaciones": ("conciliar_banco",),
    "conciliacion:importacion": ("conciliar_banco", "ver_auditoria"),
    "conciliacion:revisada": ("ver_auditoria",),
    "conciliacion:cola": ("sugerir_conciliacion", "conciliar_banco"),
    "conciliacion:movimiento": ("sugerir_conciliacion", "conciliar_banco"),
    "conciliacion:proponer": ("sugerir_conciliacion", "conciliar_banco"),
    "conciliacion:confirmar": ("conciliar_banco",),
    "conciliacion:no_cobro": ("conciliar_banco",),
    "conciliacion:emparejar": ("conciliar_banco",),
    "cortes:lista": ("turno_caja", "ver_cortes"),
    "cortes:detalle": ("turno_caja", "ver_cortes"),
    "cortes:descargar": ("turno_caja", "ver_cortes"),
    "cortes:cerrar": ("cerrar_cortes",),
    "cortes:cobranza": ("ver_cortes",),
    "cortes:destinos": ("administrar_configuracion",),
    "cortes:destino_nuevo": ("administrar_configuracion",),
    "cortes:destino_editar": ("administrar_configuracion",),
    "cortes:reintentar": ("administrar_configuracion",),
    "respaldos:panel": ("administrar_respaldos",),
    "respaldos:carpeta": ("administrar_respaldos",),
    "respaldos:respaldar": ("administrar_respaldos",),
    "respaldos:probar": ("administrar_respaldos",),
    "respaldos:clave": ("administrar_respaldos",),
    "respaldos:clave_nueva": ("administrar_respaldos",),
    "configuracion:padron_subir": ("administrar_configuracion",),
    "configuracion:padron_revisar": ("administrar_configuracion",),
    "configuracion:padron_lote": ("administrar_configuracion",),
    "configuracion:padron_matriculas": ("administrar_configuracion",),
    "configuracion:padron_fichas": ("administrar_configuracion",),
    "configuracion:inventario": ("administrar_configuracion",),
    "inventario:indice": ("vender_articulos", "registrar_movimientos_inventario", "subir_conteo_inventario", "devolver_articulos", "revisar_inventario", "administrar_articulos"),
    "inventario:articulos": ("administrar_articulos",),
    "inventario:articulo_nuevo": ("administrar_articulos",),
    "inventario:articulo_editar": ("administrar_articulos",),
    "inventario:vender": ("vender_articulos",),
    "inventario:vender_publico": ("vender_articulos",),
    "inventario:vender_titular": ("vender_articulos",),
    "inventario:ventas": ("vender_articulos", "devolver_articulos", "revisar_inventario"),
    "inventario:venta": ("vender_articulos", "devolver_articulos", "revisar_inventario"),
    "inventario:devolver": ("devolver_articulos",),
    "inventario:devolver_venta": ("devolver_articulos",),
    "inventario:registro_nuevo": ("registrar_movimientos_inventario",),
    "inventario:registro": ("registrar_movimientos_inventario", "revisar_inventario"),
    "inventario:registro_comprobante": ("registrar_movimientos_inventario",),
    "inventario:registro_descargar": ("registrar_movimientos_inventario", "revisar_inventario"),
    "inventario:registro_revisar": ("revisar_inventario",),
    "inventario:devolucion_revisar": ("revisar_inventario",),
    "inventario:renglon_revisar": ("revisar_inventario",),
    "conciliacion:topes": ("configurar_topes_banco",),
    "actualizaciones:configurar": ("administrar_configuracion",),
    "actualizaciones:buscar": ("administrar_configuracion",),
    "inventario:revision": ("revisar_inventario",),
    "inventario:existencias_csv": ("revisar_inventario", "administrar_articulos"),
    "inventario:conteo": ("subir_conteo_inventario",),
    "inventario:conteo_lista": ("subir_conteo_inventario",),
    "inventario:conteo_detalle": ("subir_conteo_inventario", "revisar_inventario", "aprobar_solicitudes"),
}

CARGA_DE_OTRO = {"conciliacion:columnas", "conciliacion:previa", "configuracion:padron_revisar", "conectar_certificado", "conectar_instalador"}

OBJETO_PROPIO = {"solicitudes:codigo": {"Operación"}, "solicitudes:detalle": None, "caja:cerrar": {"Operación"}, "caja:reconteo": {"Operación"}, "cortes:detalle": {"Supervisión", "Dirección"}, "cortes:descargar": {"Supervisión", "Dirección"}}


def nombres_de_rutas(patrones=None, prefijo=""):
    for patron in patrones if patrones is not None else get_resolver().url_patterns:
        if isinstance(patron, URLResolver):
            espacio = f"{patron.namespace}:" if patron.namespace else ""
            yield from nombres_de_rutas(patron.url_patterns, prefijo + espacio)
        elif isinstance(patron, URLPattern) and patron.name:
            yield prefijo + patron.name


def vista_de(nombre, kwargs):
    return get_resolver().resolve(reverse(nombre, kwargs=kwargs)).func


def test_toda_ruta_esta_clasificada():
    todas = set(nombres_de_rutas())
    clasificadas = PUBLICAS | SOLO_SESION | set(MATRIZ)
    assert todas == clasificadas, todas.symmetric_difference(clasificadas)


@pytest.fixture
def escenario(db):
    roles = configurar("escuela")
    usuarios = {nombre: nuevo_usuario(f"u{rol.nivel}", rol) for nombre, rol in roles.items()}
    titular = crear_titular(usuarios["Operación"], {"nombre": "Ana", "apellidos": "Prueba"}, contacto={"nombre": "Resp", "valores": {}})
    solicitud = Solicitud.objects.create(accion="alta", titular=titular, solicitante=usuarios["Operación"], caduca_en=timezone.now() + timezone.timedelta(days=1))
    otro = Rol.objects.create(nombre="Extra")
    dispositivo = Dispositivo.objects.create(hash_credencial="x" * 64, codigo="ABCDEF")
    delegacion = Delegacion.objects.create(otorgante=usuarios["Supervisión"], receptor=usuarios["Operación"], permiso="alta_baja_directa", usos_maximos=1)
    regla = ReglaRecargo.objects.create(nombre="Regla")
    plan = PlanCobro.objects.create(titular=titular, concepto=ConceptoCobro.objects.filter(tipo="recurrente").first(), vigente_desde=timezone.now().date())
    agrupacion = Agrupacion.objects.create(nombre="G1")
    familia = Familia.objects.create(nombre="F1")
    contacto_familia = Contacto.objects.create(familia=familia, nombre="Resp", principal=True)
    Titular.objects.filter(pk=titular.pk).update(estado="activo", familia=familia)
    titular.refresh_from_db()
    cargo = libro.crear_cargo(titular, ConceptoCobro.objects.filter(tipo="unico").first(), 100000, timezone.now().date(), "manual")
    turno = abrir_turno(usuarios["Operación"], Caja.objects.get_or_create(nombre="Caja 1")[0], 0)
    pago = libro.registrar_pago(titular, 50000, "efectivo", usuarios["Operación"], turno=turno)
    entrega = Traslado.objects.create(tipo="entrega", origen=usuarios["Operación"], destino=usuarios["Supervisión"], importe=100, estado="pendiente")
    motivo_retiro = MotivoRetiro.objects.create(nombre="Insumos de prueba")
    retiro = retiros.crear(turno, usuarios["Operación"], 1000, motivo_retiro, "", {})
    cuenta = CuentaBancaria.objects.create(banco=Banco.objects.get(clave="002"), clabe="002010077777777771", beneficiario="B", principal=True)
    importacion = Importacion.objects.create(cuenta=cuenta, nombre_archivo="estado.pdf", sha256="0" * 64, adaptador=Importacion.ESTADO_PDF, creada_por=usuarios["Dirección"])
    movimiento = MovimientoBancario.objects.create(cuenta=cuenta, importacion=importacion, fecha=timezone.now().date(), importe=1000, sentido="abono", clase="spei", huella="h-matriz", estado="por_identificar")
    ajeno = nuevo_usuario("ajeno", roles["Dirección"])
    carga_banco = CargaTemporal.objects.create(token="b" * 43, tipo=CargaTemporal.BANCO_PDF, usuario=ajeno, nombre_archivo="x.pdf", sha256="0" * 64, datos={})
    carga_padron = CargaTemporal.objects.create(token="p" * 43, tipo=CargaTemporal.PADRON, usuario=ajeno, nombre_archivo="x.csv", sha256="0" * 64, datos={})
    lote = LotePadron.objects.create(nombre_archivo="x.csv", sha256="0" * 64, creado_por=ajeno, resultado={"titulares": [titular.pk]})
    mayor = Corte.objects.create(tipo="mayor", fecha=timezone.now().date().replace(day=1), periodo_inicio=timezone.now().date().replace(day=1), periodo_fin=timezone.now().date().replace(day=1), cifras={})
    destino = Destino.objects.create(nombre="D", ruta="/tmp")
    entrega_corte = Entrega.objects.create(corte=mayor, destino=destino, nivel="completo")
    Parametro.objects.update_or_create(clave="modulo_inventario", defaults={"valor": "1"})
    Parametro.objects.update_or_create(clave="devoluciones_inventario", defaults={"valor": "1"})
    articulo = Articulo.objects.create(clave="LIB-1", nombre="Libro de prueba", precio=10000, concepto=ConceptoCobro.objects.first())
    venta = inventario.vender(titular, [(articulo.pk, 2)], Venta.ADEUDO, usuarios["Operación"])
    renglon = venta.renglones.get()
    devolucion = inventario.devolver(venta, {str(renglon.pk): [1, True]}, Devolucion.SALDO, usuarios["Operación"], "prueba")
    registro = inventario.registrar_movimiento("entrada", articulo, 5, "Compra", "", usuarios["Operación"])
    conteo = inventario.subir_conteo({articulo.pk: 3}, usuarios["Operación"], Conteo.PANTALLA)
    argumentos = {
        "cortes:detalle": {"pk": mayor.pk},
        "cortes:descargar": {"pk": mayor.pk, "formato": "json"},
        "cortes:cerrar": {"pk": mayor.pk},
        "cortes:destino_editar": {"pk": destino.pk},
        "cortes:reintentar": {"pk": entrega_corte.pk},
        "titulares:estado_pdf": {"pk": titular.pk},
        "titulares:familia_estado_pdf": {"pk": familia.pk},
        "conciliacion:columnas": {"token": carga_banco.token},
        "conciliacion:previa": {"token": carga_banco.token},
        "conciliacion:importacion": {"pk": importacion.pk},
        "conciliacion:revisada": {"pk": importacion.pk},
        "conciliacion:movimiento": {"pk": movimiento.pk},
        "conciliacion:proponer": {"pk": movimiento.pk},
        "conciliacion:confirmar": {"pk": movimiento.pk},
        "conciliacion:no_cobro": {"pk": movimiento.pk},
        "conciliacion:emparejar": {"pk": movimiento.pk},
        "configuracion:padron_revisar": {"token": carga_padron.token},
        "configuracion:padron_lote": {"pk": lote.pk},
        "configuracion:padron_matriculas": {"pk": lote.pk, "formato": "csv"},
        "configuracion:padron_fichas": {"pk": lote.pk},
        "titulares:detalle": {"pk": titular.pk},
        "titulares:ficha_pago": {"pk": titular.pk},
        "titulares:historial": {"pk": titular.pk},
        "titulares:editar": {"pk": titular.pk},
        "titulares:contacto_nuevo": {"pk": titular.pk},
        "titulares:contacto_editar": {"pk": titular.pk, "contacto_pk": Contacto.objects.get(titular=titular).pk},
        "titulares:baja": {"pk": titular.pk},
        "titulares:reactivar": {"pk": titular.pk},
        "titulares:solicitar_alta": {"pk": titular.pk},
        "solicitudes:detalle": {"pk": solicitud.pk},
        "solicitudes:aprobar": {"pk": solicitud.pk},
        "solicitudes:rechazar": {"pk": solicitud.pk},
        "solicitudes:codigo": {"pk": solicitud.pk},
        "solicitudes:politica_editar": {"pk": PoliticaAccion.objects.first().pk},
        "usuario_editar": {"pk": usuarios["Operación"].pk},
        "rol_editar": {"pk": otro.pk},
        "dispositivo_aprobar": {"pk": dispositivo.pk},
        "dispositivo_revocar": {"pk": dispositivo.pk},
        "delegacion_revocar": {"pk": delegacion.pk},
        "cobros:concepto_editar": {"pk": ConceptoCobro.objects.first().pk},
        "cobros:regla_editar": {"pk": regla.pk},
        "cobros:plan_editar": {"pk": plan.pk},
        "configuracion:catalogo": {"catalogo": "agrupaciones"},
        "configuracion:catalogo_nuevo": {"catalogo": "agrupaciones"},
        "configuracion:catalogo_editar": {"catalogo": "agrupaciones", "pk": agrupacion.pk},
        "banco:editar": {"pk": cuenta.pk},
        "titulares:familia": {"pk": familia.pk},
        "titulares:familia_contacto_nuevo": {"pk": familia.pk},
        "titulares:familia_contacto_editar": {"pk": familia.pk, "contacto_pk": contacto_familia.pk},
        "titulares:cambiar_familia": {"pk": titular.pk},
        "cobros:cobrar": {"pk": titular.pk},
        "cobros:recibo": {"pk": pago.recibo.pk},
        "cobros:recibo_pdf": {"pk": pago.recibo.pk},
        "cobros:cargo_manual": {"pk": titular.pk},
        "cobros:beca": {"pk": titular.pk},
        "cobros:prorroga": {"pk": cargo.pk},
        "cobros:cancelar": {"pk": cargo.pk},
        "cobros:revertir": {"pk": pago.pk},
        "caja:turno": {"pk": turno.pk},
        "caja:cerrar": {"pk": turno.pk},
        "caja:confirmar": {"pk": entrega.pk},
        "caja:reconteo": {"pk": turno.pk},
        "caja:retiro": {"pk": retiro.pk},
        "caja:retiro_comprobante": {"pk": retiro.pk},
        "caja:retiro_sin_comprobante": {"pk": retiro.pk},
        "caja:retiro_descargar": {"pk": retiro.pk},
        "caja:retiro_revisar": {"pk": retiro.pk},
        "caja:retiro_revertir": {"pk": retiro.pk},
        "caja:motivo_editar": {"pk": motivo_retiro.pk},
        "conciliacion:liberar": {"pk": importacion.pk},
        "caja:rechazar": {"pk": entrega.pk},
        "inventario:articulo_editar": {"pk": articulo.pk},
        "inventario:vender_titular": {"pk": titular.pk},
        "inventario:venta": {"pk": venta.pk},
        "inventario:devolver_venta": {"pk": venta.pk},
        "inventario:registro": {"pk": registro.pk},
        "inventario:registro_comprobante": {"pk": registro.pk},
        "inventario:registro_descargar": {"pk": registro.pk},
        "inventario:registro_revisar": {"pk": registro.pk},
        "inventario:devolucion_revisar": {"pk": devolucion.pk},
        "inventario:renglon_revisar": {"pk": renglon.pk},
        "inventario:conteo_detalle": {"pk": conteo.pk},
    }
    return usuarios, argumentos


def permitido(rol, nombre):
    if nombre in OBJETO_PROPIO and OBJETO_PROPIO[nombre] is not None:
        return rol.nombre in OBJETO_PROPIO[nombre]
    return bool(rol.permisos() & set(MATRIZ[nombre]))


@pytest.mark.parametrize("nombre", sorted(MATRIZ))
def test_matriz_url_por_rol(escenario, nombre):
    usuarios, argumentos = escenario
    url = reverse(nombre, kwargs=argumentos.get(nombre))
    assert set(vista_de(nombre, argumentos.get(nombre)).permisos_requeridos) == set(MATRIZ[nombre])
    anonimo = cliente().get(url)
    assert anonimo.status_code == 302 and reverse("entrar") in anonimo.url
    for nombre_rol in ROLES:
        usuario = usuarios[nombre_rol]
        respuesta = cliente(usuario).get(url)
        if permitido(usuario.rol, nombre):
            esperados = (404,) if nombre in CARGA_DE_OTRO else (200, 302, 405)
            assert respuesta.status_code in esperados, (nombre, nombre_rol, respuesta.status_code)
            if respuesta.status_code == 302:
                assert reverse("entrar") not in respuesta.url
        else:
            assert respuesta.status_code == 403, (nombre, nombre_rol, respuesta.status_code)


@pytest.mark.parametrize("nombre", sorted(SOLO_SESION - {"revisar_autorizacion", "aviso_enterado", "salir"}))
def test_rutas_de_sesion_piden_sesion(escenario, nombre):
    usuarios, _ = escenario
    respuesta = cliente().get(reverse(nombre))
    assert respuesta.status_code == 302 and reverse("entrar") in respuesta.url
    assert cliente(usuarios["Operación"]).get(reverse(nombre)).status_code in ((200, 302, 404) if nombre == "marca_logo" else (200, 302))


def test_revision_de_codigo_ajeno_no_permitida(escenario):
    usuarios, _ = escenario
    usado = CodigoUsado.objects.create(autorizador=usuarios["Supervisión"], paso=1, proposito=CodigoUsado.AUTORIZACION, revision=CodigoUsado.POR_REVISAR)
    url = reverse("revisar_autorizacion", args=[usado.pk])
    assert cliente(usuarios["Dirección"]).post(url, {"decision": "confirmar"}).status_code == 404
    assert cliente(usuarios["Supervisión"]).post(url, {"decision": "confirmar"}).status_code == 302
    usado.refresh_from_db()
    assert usado.revision == CodigoUsado.CONFIRMADO


def test_solicitud_ajena_no_visible_para_operacion(escenario):
    usuarios, argumentos = escenario
    otro = nuevo_usuario("otro_op", usuarios["Operación"].rol)
    url = reverse("solicitudes:detalle", kwargs=argumentos["solicitudes:detalle"])
    assert cliente(otro).get(url).status_code == 403
    assert cliente(usuarios["Operación"]).get(url).status_code == 200
    assert cliente(usuarios["Supervisión"]).get(url).status_code == 200


def test_quitar_permiso_en_base_bloquea_al_momento(escenario):
    usuarios, _ = escenario
    rol = usuarios["Operación"].rol
    rol.asignaciones.filter(permiso="ver_titulares").delete()
    assert cliente(usuarios["Operación"]).get(reverse("titulares:lista")).status_code == 403


def test_csrf_activo(escenario):
    from django.test import Client

    from .conftest import equipo_aprobado

    usuarios, _ = escenario
    c = Client(enforce_csrf_checks=True)
    c.cookies["dispositivo"] = equipo_aprobado()
    c.force_login(usuarios["Dirección"], backend="django.contrib.auth.backends.ModelBackend")
    assert c.post(reverse("auditoria:verificar")).status_code == 403
