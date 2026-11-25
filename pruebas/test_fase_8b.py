import importlib
import io
import json
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from django.apps import apps as registro
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image, ImageDraw
from pypdf import PdfReader

from auditoria.models import Evento
from banco import adaptadores, conciliacion
from banco.models import Banco, CuentaBancaria, MedioPago
from caja import retiros
from caja.models import Caja, Denominacion
from cobros import generacion, libro
from cobros.models import Beca, Cargo, ConceptoCobro, ReglaRecargo
from configuracion import colores_logo, esquema, marca, plantillas
from configuracion.models import Negocio, Parametro, Vocabulario, parametro, vocabulario
from cortes import calculo, salida
from cortes import servicios as cortes
from cortes.models import Corte, DefinicionCorte
from cuentas.models import PermisoRol, Rol
from cuentas.permisos import quienes, roles_con
from respaldos import servicios as respaldos
from titulares import contactos
from titulares.models import Titular

from .banco_ayudas import estado, pdf, spei
from .conftest import cliente, nuevo_usuario
from .libro_ayudas import preparar_conceptos, recargos_desde_el_alta, titular_activo
from .test_asistente import paso_inicio, terminar


def fijar(clave, valor):
    Parametro.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})


def png(imagen):
    salida_png = BytesIO()
    imagen.save(salida_png, format="PNG")
    return salida_png.getvalue()


def test_el_menu_de_solicitudes_aparece_a_quien_solo_aprueba(roles):
    solo = Rol.objects.create(nombre="Solo aprueba", requiere_totp=True)
    PermisoRol.objects.create(rol=solo, permiso="aprobar_solicitudes")
    persona = nuevo_usuario("aprobadora", solo)
    pagina = cliente(persona).get(reverse("inicio")).content.decode()
    assert f'href="{reverse("solicitudes:bandeja")}"' in pagina


def test_los_textos_nombran_a_los_roles_que_hoy_tienen_el_permiso(personas):
    assert quienes("revisar_retiros") == "Supervisión o Dirección"
    Rol.objects.filter(nombre="Supervisión").update(nombre="Encargada")
    assert roles_con("revisar_retiros") == ["Encargada", "Dirección"]
    pagina = cliente(personas["op"]).get(reverse("caja:retiro_nuevo")).content.decode()
    assert "Encargada o Dirección" in pagina and "Supervisión" not in pagina
    PermisoRol.objects.filter(permiso="revisar_retiros").delete()
    assert "quien tenga el permiso" in quienes("revisar_retiros")


def _semanal(**cambios):
    datos = {"nombre": "Cuota semanal", "tipo": "recurrente", "periodicidad": "semanal", "aplica_a": "todos", "importe_centavos": 10000, "dia_vencimiento": 5}
    datos.update(cambios)
    return ConceptoCobro.objects.create(**datos)


def _automaticos(concepto, titular=None):
    consulta = Cargo.objects.filter(concepto=concepto, origen=Cargo.AUTOMATICO)
    if titular is not None:
        consulta = consulta.filter(titular=titular)
    return list(consulta.order_by("vencimiento").values_list("periodo", "vencimiento", "importe_final"))


def test_semanal_con_cambio_de_anio_y_semana_53(personas):
    preparar_conceptos()
    concepto = _semanal()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    Titular.objects.filter(pk=ana.pk).update(activo_desde=date(2026, 12, 20))
    Negocio.objects.filter(pk=1).update(cobro_desde=date(2026, 12, 1))
    generacion.generar_recurrentes(date(2027, 1, 12))
    assert _automaticos(concepto, ana) == [
        ("2026-S51", date(2026, 12, 18), 10000),
        ("2026-S52", date(2026, 12, 25), 10000),
        ("2026-S53", date(2027, 1, 1), 10000),
        ("2027-S01", date(2027, 1, 8), 10000),
        ("2027-S02", date(2027, 1, 15), 10000),
    ]
    assert generacion.generar_recurrentes(date(2027, 1, 12)) == 0
    assert len(_automaticos(concepto, ana)) == 5


def test_quincenal_en_febrero_y_alta_a_mitad_de_periodo(personas):
    preparar_conceptos()
    concepto = _semanal(nombre="Cuota quincenal", periodicidad="quincenal", dia_vencimiento=15)
    beto = titular_activo(personas["op"], personas["sup"], "Beto")
    Titular.objects.filter(pk=beto.pk).update(activo_desde=date(2027, 1, 20))
    Negocio.objects.filter(pk=1).update(cobro_desde=date(2027, 1, 1))
    generacion.generar_recurrentes(date(2027, 3, 16))
    assert _automaticos(concepto, beto) == [
        ("2027-01-2", date(2027, 1, 30), 10000),
        ("2027-02-1", date(2027, 2, 15), 10000),
        ("2027-02-2", date(2027, 3, 2), 10000),
        ("2027-03-1", date(2027, 3, 15), 10000),
        ("2027-03-2", date(2027, 3, 30), 10000),
    ]
    assert max(len(p) for p, _, _ in _automaticos(concepto)) <= Cargo._meta.get_field("periodo").max_length


def test_semanal_con_descuento_prorroga_y_recargo(personas):
    preparar_conceptos()
    recargos_desde_el_alta()
    regla = ReglaRecargo.objects.create(nombre="Recargo semanal", tipo="fijo", valor=1500, dias_gracia=0)
    concepto = _semanal(regla_recargo=regla)
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    Titular.objects.filter(pk=ana.pk).update(activo_desde=date(2027, 2, 1))
    Negocio.objects.filter(pk=1).update(cobro_desde=date(2027, 2, 1))
    Beca.objects.create(titular=ana, concepto=concepto, puntos_base=5000, vigente_desde=date(2027, 2, 1), motivo="prueba", creada_por=personas["sup"])
    generacion.generar_recurrentes(date(2027, 2, 9))
    cargos = list(Cargo.objects.filter(concepto=concepto, origen=Cargo.AUTOMATICO).order_by("vencimiento"))
    assert [(c.periodo, c.importe_final, c.descuento) for c in cargos] == [("2027-S05", 5000, 5000), ("2027-S06", 5000, 5000)]
    assert generacion.generar_recargos(date(2027, 2, 10)) == 1
    recargo = Cargo.objects.get(origen=Cargo.RECARGO)
    assert recargo.cargo_base == cargos[0] and recargo.periodo == "2027-S05"


def test_cortes_con_nombre_del_negocio_tramos_y_hoja_a4(personas):
    preparar_conceptos()
    DefinicionCorte.objects.filter(tipo="mayor").update(nombre="Cierre del mes")
    fijar("tramos_cartera", "15,45")
    fijar("tamano_hoja", "a4")
    assert [t[0] for t in calculo.tramos()] == ["1_15", "16_45", "mas_45"]
    titular_activo(personas["op"], personas["sup"], "Ana")
    mayores = cortes.generar_mayores(date(2026, 3, 3))
    corte = mayores[0]
    assert corte.cifras["titulo"] == "Cierre del mes"
    assert salida.nombre_base(corte).startswith("cierre-del-mes-")
    cartera = next(s for s in corte.cifras["secciones"] if s["clave"] == "cartera_vencida")
    assert [f["tramo"] for f in cartera["filas"]] == ["1 a 15 días", "16 a 45 días", "Más de 45 días"]
    contenido = cliente(personas["sup"]).get(reverse("cortes:descargar", args=[corte.pk, "pdf"])).content
    pagina = PdfReader(io.BytesIO(contenido)).pages[0]
    assert round(float(pagina.mediabox.width)) == 842 and round(float(pagina.mediabox.height)) == 595
    assert "Cierre del mes" in pagina.extract_text()
    fijar("tramos_cartera", "no,sirve")
    assert [t[0] for t in calculo.tramos()] == ["1_30", "31_60", "61_90", "mas_90"]


def test_nombres_de_archivo_de_fabrica_se_conservan(personas):
    preparar_conceptos()
    corte = cortes.generar_mayores(date(2026, 3, 3))[0]
    assert salida.nombre_base(corte) == f"corte-mensual-{corte.fecha:%Y-%m}"


def test_recibo_y_ficha_en_a4(personas):
    from cobros.models import Pago, Recibo

    from cuentas.models import PermisoRol

    PermisoRol.objects.get_or_create(rol=personas["op"].rol, permiso="ver_ingresos")
    preparar_conceptos()
    fijar("tamano_hoja", "a4")
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    libro.registrar_pago(ana, 10000, Pago.BANCO, personas["dir"])
    recibo = Recibo.objects.get()
    for url in (reverse("cobros:recibo_pdf", args=[recibo.pk]), reverse("titulares:estado_pdf", args=[ana.pk])):
        pagina = PdfReader(io.BytesIO(cliente(personas["op"]).get(url).content)).pages[0]
        assert {round(float(pagina.mediabox.width)), round(float(pagina.mediabox.height))} == {595, 842}


def test_banco_sin_lector_lo_dice_y_ofrece_excel(personas):
    bbva = CuentaBancaria.objects.create(banco=Banco.objects.get(clave="012"), clabe="012180015555555551", beneficiario="Negocio", principal=True)
    lineas = estado([spei(3, 10000)], clabe=bbva.clabe)
    with pytest.raises(conciliacion.ErrorConciliacion) as error:
        conciliacion.movimientos_de_pdf(lineas)
    assert "BBVA" in str(error.value).upper() and "Excel o CSV" in str(error.value)
    with pytest.raises(conciliacion.ErrorConciliacion) as error:
        conciliacion.movimientos_de_pdf(["NADA QUE LEER"], bbva)
    assert "Santander PyME" in str(error.value)
    respuesta = cliente(personas["dir"]).post(reverse("conciliacion:importar"), {"archivo": SimpleUploadedFile("estado.pdf", pdf(lineas))})
    assert "Excel o CSV" in respuesta.content.decode()
    assert adaptadores.para_banco("014").nombre == "Santander PyME" and adaptadores.para_banco("012") is None


def test_cuenta_sin_clabe(personas):
    c = cliente(personas["dir"])
    datos = {"tipo": "otra", "banco_otro": "Banco Ficticio del Sur", "numero_cuenta": "ES91 2100 0418 4502 0005 1332", "beneficiario": "Negocio", "referencia_en": "concepto", "contacto_dudas": "5512345678", "activa": "on"}
    assert c.post(reverse("banco:nueva"), datos).status_code == 302
    cuenta = CuentaBancaria.objects.get()
    assert (cuenta.tipo, cuenta.clabe, cuenta.banco, cuenta.nombre_banco, cuenta.numero_cuenta) == ("otra", "", None, "Banco Ficticio del Sur", "ES9121000418450200051332")
    assert cuenta.etiqueta_numero == "Número de cuenta" and "ES9121000418450200051332" in str(cuenta)
    sin_numero = c.post(reverse("banco:nueva"), dict(datos, numero_cuenta=""))
    assert sin_numero.status_code == 200 and "número de la cuenta" in sin_numero.content.decode()
    titular = titular_activo(personas["op"], personas["sup"], "Ana")
    ficha = c.get(reverse("titulares:ficha_pago", args=[titular.pk])).content.decode()
    assert "Banco Ficticio del Sur" in ficha and "ES9121000418450200051332" in ficha and "CLABE" not in ficha


@pytest.mark.django_db
def test_los_medios_de_pago_vienen_de_la_plantilla():
    assert not MedioPago.objects.exists()
    datos = plantillas.leer("generico")
    datos["medios_pago"] = ["Transferencia", "Tarjeta en terminal"]
    plantillas.cargar_datos(datos, "prueba")
    assert set(MedioPago.objects.values_list("nombre", flat=True)) == {"Transferencia", "Tarjeta en terminal"}


def test_consentimiento_y_apellidos_configurables(personas):
    c = cliente(personas["dir"])
    pagina = c.get(reverse("titulares:nuevo")).content.decode()
    assert "constancia_consentimiento" in pagina
    c.post(reverse("configuracion:reglas"), {"prefijo_pais_telefono": 52, "digitos_telefono_nacional": 10, "tamano_hoja": "carta", "texto_consentimiento": ""})
    assert parametro("pedir_consentimiento") == 0 and parametro("apellidos_obligatorios") == 0
    pagina = c.get(reverse("titulares:nuevo")).content.decode()
    assert "constancia_consentimiento" not in pagina
    respuesta = c.post(reverse("titulares:nuevo"), {"nombre": "Comercializadora Ficticia SA", "apellidos": "", "contacto_nombre": "Compras", "campo_1": "5512345678"})
    assert respuesta.status_code == 302, respuesta.content.decode()[-2000:]
    empresa = Titular.objects.get(nombre="Comercializadora Ficticia SA")
    assert empresa.apellidos == "" and empresa.nombre_completo == "Comercializadora Ficticia SA"
    c.post(reverse("configuracion:reglas"), {"prefijo_pais_telefono": 52, "digitos_telefono_nacional": 10, "tamano_hoja": "carta", "pedir_consentimiento": "on", "texto_consentimiento": "Leí el aviso de privacidad del negocio", "apellidos_obligatorios": "on"})
    assert "Leí el aviso de privacidad del negocio" in c.get(reverse("titulares:nuevo")).content.decode()


def test_telefono_con_otro_largo_se_formatea_con_los_parametros(db):
    fijar("prefijo_pais_telefono", 506)
    fijar("digitos_telefono_nacional", 8)
    normalizado = contactos.normalizar_telefono("8888 1234")
    assert normalizado == "50688881234" and contactos.formatear_telefono(normalizado) == "+506 8888 1234"
    fijar("prefijo_pais_telefono", 52)
    fijar("digitos_telefono_nacional", 10)
    assert contactos.formatear_telefono("525512345678") == "+52 55 1234 5678"


def test_respaldos_y_retiros_configurables(personas, tmp_path):
    from datetime import datetime, timedelta

    fijar("respaldos_diarios", 9)
    fijar("respaldos_mensuales", 0)
    inicio = datetime(2026, 11, 12, 2, 0)
    for dias in range(15):
        (tmp_path / respaldos.nombre_archivo(inicio - timedelta(days=dias))).write_bytes(b"x")
    respaldos.retener(tmp_path)
    assert len(list(tmp_path.iterdir())) == 9
    fijar("respaldos_diarios", 3)
    respaldos.retener(tmp_path)
    assert len(list(tmp_path.iterdir())) == respaldos.DIARIOS_MINIMOS == 7
    fijar("horas_alerta_respaldo", 12)
    assert respaldos.horas_alerta() == 12 and respaldos.dias_prueba() == 30
    from .libro_ayudas import turno_de

    turno = turno_de(personas["op"])
    turno.rechazos_retiro = 1
    assert "rechazos" not in retiros.excede(turno, 1)
    fijar("rechazos_antes_de_autorizar", 1)
    assert "rechazos" in retiros.excede(turno, 1)


def test_asistente_pide_denominaciones_si_la_moneda_no_es_la_de_la_plantilla(db):
    c = Client()
    datos = paso_inicio(settings.TOKEN_ASISTENTE, "generico")
    datos["moneda"] = "USD"
    assert c.post(reverse("asistente:inicio"), datos).status_code == 302
    assert not Denominacion.objects.exists()
    pagina = c.get(reverse("asistente:caja")).content.decode()
    assert "moneda-denominaciones" in pagina and "USD" in pagina
    caja = {f"corte_{dia}": "18:00" for dia in range(6)}
    caja.update({"periodo_retiros": "dia", "tope_retiro_individual": "0", "tope_retiros_periodo": "0", "maximo_retiros_periodo": "0", "maximo_efectivo_caja": "0", "dias_retiro_sin_revisar": "3"})
    assert c.post(reverse("asistente:caja"), caja).status_code == 200
    caja["moneda-denominaciones"] = "100, 50, 20, 10, 5, 1, 0.25, 0.10, 0.05, 0.01"
    assert c.post(reverse("asistente:caja"), caja).url == reverse("asistente:reglas")
    assert list(Denominacion.objects.values_list("valor", flat=True)) == [10000, 5000, 2000, 1000, 500, 100, 25, 10, 5, 1]


@pytest.mark.django_db
def test_asistente_reglas_y_paso_final_de_importacion():
    c = Client()
    c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE, "rentas"))
    assert vocabulario()["titular"] == "Inquilino"
    respuesta = c.post(reverse("asistente:reglas"), {"prefijo_pais_telefono": 57, "digitos_telefono_nacional": 10, "tamano_hoja": "a4", "texto_consentimiento": "x"})
    assert respuesta.url == reverse("asistente:cortes")
    assert (parametro("prefijo_pais_telefono"), parametro("tamano_hoja"), parametro("pedir_consentimiento"), parametro("apellidos_obligatorios")) == (57, "a4", 0, 0)
    assert terminar(c).url == reverse("primeros_pasos")
    pagina = c.get(reverse("primeros_pasos")).content.decode()
    assert reverse("configuracion:padron_subir") in pagina and "Importar desde Excel o CSV" in pagina
    assert "Marca del negocio" in pagina and "Datos de pago" in pagina
    vacio = c.get(reverse("titulares:lista")).content.decode()
    assert "Todavía no hay inquilinos" in vacio and reverse("configuracion:padron_subir") in vacio


@pytest.mark.django_db
@pytest.mark.parametrize("nombre", ["generico", "escuela", "gimnasio", "academia", "rentas", "servicios"])
def test_plantillas_incluidas_pasan_el_esquema_y_se_ofrecen(nombre):
    datos = plantillas.leer(nombre)
    assert set(datos["vocabulario"]) == set(esquema.VOCABULARIO)
    assert not any(isinstance(c.get("importe_centavos"), int) for c in datos["conceptos"])
    assert nombre in plantillas.disponibles()
    texto = (settings.PLANTILLAS_NEGOCIO / f"{nombre}.json").read_text(encoding="utf-8")
    assert "importe" not in texto
    pagina = Client().get(reverse("asistente:inicio")).content.decode()
    assert f'value="{nombre}"' in pagina


def test_plantillas_de_arranque_usan_cobros_semanales_y_quincenales():
    periodicidades = {c.get("periodicidad") for n in ("gimnasio", "academia", "servicios") for c in json.loads((settings.PLANTILLAS_NEGOCIO / f"{n}.json").read_text(encoding="utf-8"))["conceptos"]}
    assert {"semanal", "quincenal"} <= periodicidades


@pytest.mark.django_db
def test_migracion_conserva_lo_que_veia_una_instalacion_existente():
    migracion = importlib.import_module("configuracion.migrations.0015_nada_fijo_de_un_negocio")
    migracion.conservar(registro, None)
    assert not Vocabulario.objects.exists()
    Negocio.objects.create(pk=1, nombre="Negocio existente")
    migracion.conservar(registro, None)
    assert vocabulario()["descuento"] == "Beca" and vocabulario()["padron"] == "Padrón"
    assert json.loads(Parametro.objects.get(clave="calendario_corte").valor) == {str(d): "18:00" for d in range(7)}


@pytest.mark.django_db
def test_migracion_da_los_permisos_de_importacion():
    migracion = importlib.import_module("cuentas.migrations.0008_permisos_de_importacion")
    operacion = Rol.objects.create(nombre="Mostrador")
    PermisoRol.objects.create(rol=operacion, permiso="solicitar_alta_baja")
    jefa = Rol.objects.create(nombre="Jefa", requiere_totp=True)
    PermisoRol.objects.create(rol=jefa, permiso="administrar_configuracion")
    migracion.otorgar(registro, None)
    assert operacion.permisos() == {"solicitar_alta_baja", "solicitar_importacion_padron"}
    assert jefa.permisos() == {"administrar_configuracion", "importar_padron"}


@pytest.fixture
def limpio():
    cache.clear()
    yield
    cache.clear()


def _logo_transparente():
    imagen = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rectangle([20, 20, 120, 80], fill=(31, 26, 78, 255))
    dibujo.ellipse([130, 30, 180, 70], fill=(245, 134, 52, 255))
    return png(imagen)


def _logo_fondo_blanco():
    imagen = Image.new("RGB", (200, 100), (255, 255, 255))
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rectangle([20, 20, 120, 80], fill=(200, 30, 40))
    dibujo.ellipse([130, 30, 180, 70], fill=(30, 120, 200))
    return png(imagen)


def _logo_un_color():
    imagen = Image.new("RGB", (120, 120), (255, 255, 255))
    ImageDraw.Draw(imagen).ellipse([10, 10, 110, 110], fill=(20, 140, 60))
    return png(imagen)


def _logo_dos_tonos():
    imagen = Image.new("RGBA", (120, 60), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rectangle([0, 0, 59, 59], fill=(30, 60, 160, 255))
    dibujo.rectangle([60, 0, 119, 59], fill=(110, 150, 230, 255))
    return png(imagen)


def _logo_blanco_y_negro():
    imagen = Image.new("RGB", (100, 100), (255, 255, 255))
    ImageDraw.Draw(imagen).rectangle([20, 20, 80, 80], fill=(0, 0, 0))
    return png(imagen)


def _legible(propuesta):
    fondo = marca.mezclar(propuesta["acento"], marca.PROPORCION_FONDO)
    assert marca.contraste(marca.BLANCO, propuesta["principal"]) >= marca.CONTRASTE_TEXTO
    assert marca.contraste(propuesta["principal"], fondo) >= marca.CONTRASTE_TEXTO
    marca.validar_color(propuesta["acento"])


def _tono(color):
    import colorsys

    return colorsys.rgb_to_hls(*(c / 255 for c in marca.componentes(color)))[0] * 360


def test_colores_de_un_logo_transparente():
    propuesta = colores_logo.proponer(_logo_transparente())
    assert propuesta["origen"] == "logo" and propuesta["principal"] == "#1F1A4E"
    assert 15 <= _tono(propuesta["acento"]) <= 35
    _legible(propuesta)


def test_colores_de_un_logo_con_fondo_blanco_descartan_el_fondo():
    propuesta = colores_logo.proponer(_logo_fondo_blanco())
    assert propuesta["origen"] == "logo"
    tonos = sorted([_tono(propuesta["principal"]), _tono(propuesta["acento"])])
    assert tonos[0] < 10 or tonos[0] > 350 or 195 <= tonos[0] <= 215
    assert any(195 <= t <= 215 for t in tonos) and any(t < 10 or t > 350 for t in tonos)
    _legible(propuesta)


def test_colores_de_un_logo_de_un_solo_color_usan_su_tono_en_el_acento():
    propuesta = colores_logo.proponer(_logo_un_color())
    assert propuesta["origen"] == "logo"
    assert abs(_tono(propuesta["principal"]) - _tono(propuesta["acento"])) < 3
    _legible(propuesta)


def test_colores_de_un_logo_de_dos_tonos_del_mismo_color():
    propuesta = colores_logo.proponer(_logo_dos_tonos())
    assert propuesta["origen"] == "logo" and abs(_tono(propuesta["principal"]) - _tono(propuesta["acento"])) < 25
    _legible(propuesta)


def test_colores_de_un_logo_en_blanco_y_negro():
    propuesta = colores_logo.proponer(_logo_blanco_y_negro())
    assert propuesta == {"principal": "#000000", "acento": colores_logo.ACENTO_FABRICA, "origen": "neutro"}


def test_el_mismo_logo_da_siempre_los_mismos_colores():
    for fabrica in (_logo_transparente, _logo_fondo_blanco, _logo_un_color, _logo_dos_tonos, _logo_blanco_y_negro):
        contenido = fabrica()
        primera = colores_logo.proponer(contenido)
        assert all(colores_logo.proponer(contenido) == primera for _ in range(3))
        _, limpio_png = marca.preparar_logo(contenido)
        assert colores_logo.proponer(limpio_png) == colores_logo.proponer(marca.preparar_logo(contenido)[1])


def test_configuracion_usa_los_colores_del_logo_con_vista_previa(personas, limpio):
    c = cliente(personas["dir"])
    respuesta = c.post(reverse("configuracion:marca"), {"accion": "logo", "archivo": SimpleUploadedFile("logo.png", _logo_transparente(), content_type="image/png")})
    assert respuesta.status_code == 302
    pagina = c.get(reverse("configuracion:marca")).content.decode()
    assert 'value="#1F1A4E"' in pagina and "Usar estos colores" in pagina and "vista-previa" in pagina
    assert f'{reverse("marca_vista_css")}?p=1F1A4E&amp;a=' in pagina
    assert not marca.actual().con_colores
    otra = c.post(reverse("configuracion:marca"), {"accion": "colores_logo"}).content.decode()
    assert 'value="#1F1A4E"' in otra and "Usar los colores del logo" in otra
    assert Evento.objects.filter(accion="marca_colores_propuestos").exists()
    hoja = c.get(reverse("marca_vista_css") + "?p=1F1A4E&a=E66709")
    assert hoja["Content-Type"].startswith("text/css") and "--primario: #1F1A4E;" in hoja.content.decode() and hoja.content.decode().startswith(".vista-previa {")
    assert c.get(reverse("marca_vista_css") + "?p=1F1A4E;}body{x&a=E66709").content.decode() == ".vista-previa {}\n"


@pytest.mark.django_db
def test_paso_de_marca_del_asistente(limpio):
    c = Client()
    c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE, "generico"))
    assert c.post(reverse("asistente:marca"), {"accion": "logo", "archivo": SimpleUploadedFile("logo.png", _logo_fondo_blanco(), content_type="image/png")}).url == reverse("asistente:marca")
    pagina = c.get(reverse("asistente:marca")).content.decode()
    assert "Colores tomados del logo" in pagina and reverse("asistente:vista_marca") in pagina and reverse("asistente:logo") in pagina
    assert c.get(reverse("asistente:logo")).status_code == 200
    propuesta = colores_logo.proponer(_logo_fondo_blanco())
    assert c.post(reverse("asistente:marca"), {"accion": "colores", "color_principal": propuesta["principal"], "color_acento": propuesta["acento"]}).url == reverse("asistente:pago")
    actual = marca.actual()
    assert (actual.color_principal, actual.color_acento) == (propuesta["principal"], propuesta["acento"]) and actual.logo
    assert "--primario" in c.get(reverse("asistente:vista_marca") + "?p=112233&a=445566").content.decode()


def test_vocabulario_nuevo_en_pantallas_de_escuela_y_generica(personas):
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    pagina = cliente(personas["sup"]).get(reverse("titulares:detalle", args=[ana.pk])).content.decode()
    assert ">Beca</a>" in pagina
    Vocabulario.objects.filter(clave="descuento").delete()
    assert vocabulario()["descuento"] == "Descuento"
    plantillas.cargar("generico")
    assert vocabulario()["padron"] == "Lista de clientes"


def test_pagina_de_marca_respeta_la_politica_de_contenido(personas, limpio):
    from .test_interfaz import _ofensas

    c = cliente(personas["dir"])
    c.post(reverse("configuracion:marca"), {"accion": "logo", "archivo": SimpleUploadedFile("logo.png", _logo_transparente(), content_type="image/png")})
    assert _ofensas(c.get(reverse("configuracion:marca")).content.decode()) == []
    for ruta in (reverse("primeros_pasos"), reverse("configuracion:reglas"), reverse("configuracion:padron_subir")):
        assert _ofensas(c.get(ruta).content.decode()) == [], ruta
