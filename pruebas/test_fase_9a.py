import re

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from caja import cambio as cambio_caja
from caja import piezas as control_piezas
from caja import servicios as caja
from caja.models import Caja, MovimientoPiezas, Turno
from cobros import libro
from cobros.formularios import FormularioRegla
from cobros.models import Pago, ReglaRecargo
from configuracion import zonas
from configuracion.formularios import FormularioReglas
from configuracion.models import AvanceAsistente, Negocio, Parametro, Vocabulario, parametro
from cuentas.models import PreferenciaOrden
from proyecto import orden as ordenes
from titulares.models import Titular

from .conftest import cliente
from .libro_ayudas import preparar_conceptos, titular_activo
from .test_asistente import paso_inicio


def apagar_piezas():
    Parametro.objects.update_or_create(clave="control_denominaciones", defaults={"valor": "0"})


def una_caja():
    return Caja.objects.get_or_create(nombre="Caja 1")[0]


def test_zonas_canonicas_con_region_agrupadas_y_con_desfase():
    canonicas = zonas.canonicas()
    assert "America/Mexico_City" in canonicas and "Europe/Madrid" in canonicas
    for rara in ("US/Eastern", "Etc/UTC", "EST", "UTC", "Mexico/General", "America/Buenos_Aires"):
        assert rara not in canonicas
    grupos = dict(zonas.opciones()[1:])
    assert list(grupos)[:2] == ["América", "Europa"]
    etiquetas = dict(grupos["América"])
    assert re.fullmatch(r"Ciudad de México \(UTC[+−]\d\d:\d\d\)", etiquetas["America/Mexico_City"])
    assert re.fullmatch(r"Monterrey \(UTC[+−]\d\d:\d\d\)", etiquetas["America/Monterrey"])
    assert zonas.opciones()[0] == ("", "Elige la zona horaria")


def test_desfase_vigente_cambia_con_el_horario_de_verano():
    from datetime import datetime, timezone

    assert zonas.desfase("Europe/Madrid", datetime(2026, 1, 15, tzinfo=timezone.utc)) == "UTC+01:00"
    assert zonas.desfase("Europe/Madrid", datetime(2026, 7, 15, tzinfo=timezone.utc)) == "UTC+02:00"
    assert zonas.desfase("America/Mexico_City", datetime(2026, 7, 15, tzinfo=timezone.utc)) == "UTC−06:00"


def test_configuracion_elige_la_zona_de_la_lista_y_rechaza_lo_demas(personas):
    d = cliente(personas["dir"])
    ruta = reverse("configuracion:negocio")
    pagina = d.get(ruta).content.decode()
    assert '<select name="zona_horaria" data-buscar-zona=""' in pagina and '<optgroup label="Europa">' in pagina
    assert '<input type="text" name="zona_horaria"' not in pagina
    for mala in ("Marte/Olimpo", "US/Eastern", "../../etc/passwd", ""):
        respuesta = d.post(ruta, {"nombre": "Negocio de prueba", "zona_horaria": mala, "nota_ficha": ""})
        assert respuesta.status_code == 200 and "zona horaria" in respuesta.content.decode()
    assert Negocio.objects.get().zona_horaria == "America/Mexico_City"
    assert d.post(ruta, {"nombre": "Negocio de prueba", "zona_horaria": "America/Monterrey", "nota_ficha": ""}).status_code == 302
    assert Negocio.objects.get().zona_horaria == "America/Monterrey"


def test_una_zona_antigua_guardada_sigue_valiendo(personas):
    Negocio.objects.filter(pk=1).update(zona_horaria="US/Central")
    d = cliente(personas["dir"])
    pagina = d.get(reverse("configuracion:negocio")).content.decode()
    assert '<option value="US/Central" selected>' in pagina
    assert d.post(reverse("configuracion:negocio"), {"nombre": "Negocio de prueba", "zona_horaria": "US/Central", "nota_ficha": ""}).status_code == 302


@pytest.mark.django_db
def test_asistente_propone_la_zona_y_la_valida(monkeypatch):
    monkeypatch.setattr(zonas, "de_la_computadora", lambda: "America/Tijuana")
    c = Client()
    pagina = c.get(reverse("asistente:inicio")).content.decode()
    assert '<option value="America/Tijuana" selected>' in pagina and "data-proponer-local" in pagina
    assert re.search(r'value="generico"[^>]*checked', pagina)
    datos = paso_inicio(settings.TOKEN_ASISTENTE)
    datos["zona_horaria"] = "Marte/Olimpo"
    assert c.post(reverse("asistente:inicio"), datos).status_code == 200 and not Negocio.objects.exists()
    datos["zona_horaria"] = "Europe/Madrid"
    assert c.post(reverse("asistente:inicio"), datos).url == reverse("asistente:marca")
    assert Negocio.objects.get().zona_horaria == "Europe/Madrid"


def test_zona_de_la_computadora_solo_si_es_canonica(monkeypatch):
    monkeypatch.setenv("TZ", ":America/Merida")
    assert zonas.de_la_computadora() == "America/Merida"
    monkeypatch.setenv("TZ", "Hora/Inventada")
    monkeypatch.setattr(zonas, "_de_enlace", lambda ruta: "")
    monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert zonas.de_la_computadora() == ""


def test_el_signo_sigue_al_tipo_en_reglas_de_recargo(personas):
    d = cliente(personas["dir"])
    pagina = d.get(reverse("cobros:regla_nueva")).content.decode()
    importe = re.search(r'<div class="campo" data-depende-de="tipo" data-mostrar-si="fijo"[^>]*>(.*?)</div>', pagina, re.S).group(1)
    porcentaje = re.search(r'<div class="campo" data-depende-de="tipo" data-mostrar-si="porcentaje"[^>]*>(.*?)</div>', pagina, re.S).group(1)
    assert 'name="valor_importe"' in importe and ">$<" in importe and "%" not in importe
    assert 'name="valor_porcentaje"' in porcentaje and ">%<" in porcentaje and ">$<" not in porcentaje
    assert 'type="radio" name="tipo"' in pagina
    assert d.post(reverse("cobros:regla_nueva"), {"nombre": "Diez por ciento", "tipo": "porcentaje", "valor_porcentaje": "10", "dias_gracia": "0", "activa": "on"}).status_code == 302
    assert ReglaRecargo.objects.get(nombre="Diez por ciento").valor == 1000
    sin_valor = d.post(reverse("cobros:regla_nueva"), {"nombre": "Sin valor", "tipo": "fijo", "valor_porcentaje": "10", "dias_gracia": "0"})
    assert sin_valor.status_code == 200 and not ReglaRecargo.objects.filter(nombre="Sin valor").exists()
    fuera = d.post(reverse("cobros:regla_nueva"), {"nombre": "Fuera", "tipo": "porcentaje", "valor_porcentaje": "150", "dias_gracia": "0"})
    assert fuera.status_code == 200 and "0.01 a 100" in fuera.content.decode()


def test_cada_eleccion_de_porcentaje_o_importe_tiene_sus_dos_campos_dependientes(roles):
    formulario = FormularioRegla()
    assert (formulario.fields["valor_importe"].depende["control"], formulario.fields["valor_importe"].depende["valores"]) == ("tipo", [ReglaRecargo.FIJO])
    assert (formulario.fields["valor_porcentaje"].depende["control"], formulario.fields["valor_porcentaje"].depende["valores"]) == ("tipo", [ReglaRecargo.PORCENTAJE])
    from cobros.models import ConceptoCobro
    from configuracion.formularios import FormularioAsistenteConceptos

    concepto = ConceptoCobro.objects.get(nombre="Colegiatura")
    asistente = FormularioAsistenteConceptos(conceptos=[concepto], con_recargo={concepto.nombre: {"tipo": "fijo"}})
    assert asistente.fields[f"recargo_importe_{concepto.pk}"].depende["valores"] == [ReglaRecargo.FIJO]
    assert asistente.fields[f"recargo_porcentaje_{concepto.pk}"].depende["control"] == f"recargo_tipo_{concepto.pk}"


def test_abrir_turno_pide_las_piezas_y_el_fondo_es_la_suma(personas):
    caja_1 = una_caja()
    op = cliente(personas["op"])
    pagina = op.get(reverse("caja:inicio")).content.decode()
    assert 'name="f_50000"' in pagina and 'name="fondo_inicial"' not in pagina and "data-mosaicos" in pagina
    respuesta = op.post(reverse("caja:abrir"), {"caja": caja_1.pk, "apertura": "efectivo", "f_50000": "1", "f_10000": "3", "f_1000": "4", "fondo_inicial": "999999"})
    assert respuesta.status_code == 302 and respuesta.url == reverse("caja:inicio")
    turno = Turno.objects.get()
    assert turno.fondo_inicial == 50000 + 30000 + 4000
    assert set(MovimientoPiezas.objects.filter(turno=turno).values_list("origen", "denominacion", "piezas")) == {("apertura", 50000, 1), ("apertura", 10000, 3), ("apertura", 1000, 4)}
    assert control_piezas.existencias(turno) == {"50000": 1, "10000": 3, "1000": 4}
    assert cambio_caja.proponer(30000, control_piezas.disponibles(turno)) == {10000: 3}


def test_abrir_en_cero_es_un_solo_paso(personas):
    op = cliente(personas["op"])
    assert op.post(reverse("caja:abrir"), {"caja": una_caja().pk, "apertura": "cero", "f_50000": "3"}).status_code == 302
    turno = Turno.objects.get()
    assert turno.fondo_inicial == 0 and not MovimientoPiezas.objects.filter(turno=turno).exists()


def test_sin_control_de_piezas_se_pide_solo_el_importe(personas):
    apagar_piezas()
    op = cliente(personas["op"])
    pagina = op.get(reverse("caja:inicio")).content.decode()
    assert 'name="fondo_inicial"' in pagina and 'name="f_50000"' not in pagina
    assert op.post(reverse("caja:abrir"), {"caja": una_caja().pk, "apertura": "efectivo", "fondo_inicial": "750.50"}).status_code == 302
    turno = Turno.objects.get()
    assert turno.fondo_inicial == 75050 and not MovimientoPiezas.objects.exists()


def test_abrir_con_piezas_invalidas_no_abre_y_conserva_lo_capturado(personas):
    op = cliente(personas["op"])
    respuesta = op.post(reverse("caja:abrir"), {"caja": una_caja().pk, "apertura": "efectivo", "f_50000": "-2", "f_10000": "3"})
    assert respuesta.status_code == 200 and not Turno.objects.exists()
    assert 'name="f_10000" value="3"' in respuesta.content.decode()


def test_con_fondo_en_piezas_el_cierre_sigue_siendo_ciego(personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    op = cliente(personas["op"])
    op.post(reverse("caja:abrir"), {"caja": una_caja().pk, "apertura": "efectivo", "f_20000": "3"})
    turno = Turno.objects.get()
    libro.registrar_pago(ana, 12345, Pago.EFECTIVO, personas["op"], turno=turno)
    esperado = caja.esperado_de(turno)
    for ruta in (reverse("caja:inicio"), reverse("caja:cerrar", args=[turno.pk]), reverse("caja:turno", args=[turno.pk])):
        texto = op.get(ruta).content.decode()
        assert "723.45" not in texto and str(esperado) not in texto
    assert op.post(reverse("caja:cerrar", args=[turno.pk]), {"d_20000": "3"}).url == reverse("caja:reconteo", args=[turno.pk])
    pagina = op.get(reverse("caja:reconteo", args=[turno.pk])).content.decode()
    assert "no coincide" in pagina and "723.45" not in pagina and "123.45" not in pagina and "Debe haber" not in pagina
    op.post(reverse("caja:reconteo", args=[turno.pk]), {"accion": "primero", "nota": "Sin reconteo"})
    resultado = op.get(reverse("caja:turno", args=[turno.pk])).content.decode()
    assert "Resultado del conteo" in resultado and "$723.45" in resultado and "Fondo inicial" in resultado and "Debe haber" in resultado


def test_retiro_con_mosaicos_y_topes_a_la_vista(personas):
    op = cliente(personas["op"])
    op.post(reverse("caja:abrir"), {"caja": una_caja().pk, "apertura": "efectivo", "f_20000": "3"})
    pagina = op.get(reverse("caja:retiro_nuevo")).content.decode()
    assert "data-mosaicos" in pagina and 'name="p_20000"' in pagina and "Tus topes" in pagina and 'type="radio" name="motivo"' in pagina


def titulares_ordenables(personas):
    from titulares.models import Agrupacion

    grupo_a, _ = Agrupacion.objects.get_or_create(nombre="Grupo A")
    grupo_b, _ = Agrupacion.objects.get_or_create(nombre="Grupo B")
    nombres = [("Beatriz", "Zamora", grupo_a), ("Carlos", "Arenas", grupo_b), ("Alma", "Mendez", grupo_b)]
    creados = []
    for nombre, apellidos, grupo in nombres:
        titular = titular_activo(personas["op"], personas["sup"], nombre)
        Titular.objects.filter(pk=titular.pk).update(apellidos=apellidos, agrupacion=grupo)
        creados.append(titular)
    return creados


def posiciones(texto, nombres):
    return [texto.index(n) for n in nombres]


def test_el_padron_se_ordena_y_el_orden_se_recuerda_por_persona(personas):
    preparar_conceptos()
    titulares_ordenables(personas)
    d = cliente(personas["dir"])
    ruta = reverse("titulares:lista")
    pagina = d.get(ruta).content.decode()
    assert 'name="orden"' in pagina and 'name="sentido"' in pagina
    a, b, c = posiciones(pagina, ["Arenas", "Mendez", "Zamora"])
    assert a < b < c
    pagina = d.get(ruta, {"orden": "nombre", "sentido": "desc"}).content.decode()
    a, b, c = posiciones(pagina, ["Carlos", "Beatriz", "Alma"])
    assert a < b < c
    assert PreferenciaOrden.objects.get(usuario=personas["dir"], lista="padron").clave == "nombre"
    pagina = d.get(ruta).content.decode()
    a, b, c = posiciones(pagina, ["Carlos", "Beatriz", "Alma"])
    assert a < b < c
    otra = cliente(personas["sup"]).get(ruta).content.decode()
    a, b, c = posiciones(otra, ["Arenas", "Mendez", "Zamora"])
    assert a < b < c
    assert not PreferenciaOrden.objects.filter(usuario=personas["sup"]).exists()


def test_el_servidor_solo_acepta_claves_de_la_lista(personas):
    preparar_conceptos()
    titulares_ordenables(personas)
    d = cliente(personas["dir"])
    for mala in ("password", "-nombre", "nombre; DROP TABLE x", "creado_por__password", "familia__nombre"):
        respuesta = d.get(reverse("titulares:lista"), {"orden": mala})
        assert respuesta.status_code == 200
    assert not PreferenciaOrden.objects.exclude(clave__in=["nombre", "apellidos", "matricula", "agrupacion", "familia"]).exists()
    for lista, (construir, defecto, _) in ordenes.LISTAS.items():
        opciones = construir({"matricula": "M", "agrupacion": "A", "familia": "F"})
        assert defecto in opciones
        for etiqueta, campos in opciones.values():
            assert all(re.fullmatch(r"-?[a-z_]+", campo) for campo in campos)


def test_el_orden_usa_el_vocabulario_del_negocio(personas):
    Vocabulario.objects.update_or_create(clave="agrupacion", defaults={"texto": "Cuadrilla"})
    Vocabulario.objects.update_or_create(clave="matricula", defaults={"texto": "Folio de socio"})
    preparar_conceptos()
    titular_activo(personas["op"], personas["sup"], "Ana")
    pagina = cliente(personas["dir"]).get(reverse("titulares:lista")).content.decode()
    assert '<option value="agrupacion">Cuadrilla</option>' in pagina and '<option value="matricula">Folio de socio</option>' in pagina


def test_buscar_para_cobrar_se_ordena_por_agrupacion(personas):
    preparar_conceptos()
    titulares_ordenables(personas)
    op = cliente(personas["op"])
    pagina = op.get(reverse("cobros:buscar"), {"q": "a", "orden": "agrupacion", "sentido": "desc"}).content.decode()
    assert pagina.index("Beatriz") > max(pagina.index("Carlos"), pagina.index("Alma"))
    assert PreferenciaOrden.objects.get(usuario=personas["op"], lista="cobrar").descendente
    assert not PreferenciaOrden.objects.filter(usuario=personas["op"], lista="padron").exists()


def test_otras_listas_ofrecen_su_orden(personas):
    d = cliente(personas["dir"])
    for ruta, lista in ((reverse("usuarios"), "usuarios"), (reverse("cortes:lista"), "cortes")):
        pagina = d.get(ruta, {"orden": "fecha" if lista == "cortes" else "usuario", "sentido": "desc"}).content.decode()
        assert 'name="orden"' in pagina
        assert PreferenciaOrden.objects.get(usuario=personas["dir"], lista=lista).descendente


@pytest.mark.django_db
def test_asistente_atras_no_pierde_lo_capturado_y_pliega_lo_avanzado():
    c = Client()
    assert c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE)).url == reverse("asistente:marca")
    personalizar = c.get(reverse("asistente:personalizar")).content.decode()
    assert 'name="atras"' not in personalizar
    caja_pagina = c.get(reverse("asistente:caja")).content.decode()
    assert 'name="atras"' in caja_pagina and "Más opciones" in caja_pagina and "muestra-piezas" in caja_pagina and 'class="mosaico"' in caja_pagina
    assert caja_pagina.index('name="tope_retiro_individual"') < caja_pagina.index("Más opciones") < caja_pagina.index('name="dias_retiro_sin_revisar"')
    respuesta = c.post(reverse("asistente:reglas"), {"atras": "1", "prefijo_pais_telefono": "57", "digitos_telefono_nacional": "", "tamano_hoja": "a4", "token": "no-se-guarda"})
    assert respuesta.status_code == 302 and respuesta.url == reverse("asistente:caja")
    assert parametro("prefijo_pais_telefono") == 52
    vuelta = c.get(reverse("asistente:reglas")).content.decode()
    assert 'name="prefijo_pais_telefono" value="57"' in vuelta and re.search(r'value="a4"[^>]*checked', vuelta)
    assert "no-se-guarda" not in str(AvanceAsistente.objects.get().estado)
    assert c.post(reverse("asistente:reglas"), {"prefijo_pais_telefono": "57", "digitos_telefono_nacional": "10", "tamano_hoja": "a4", "texto_consentimiento": ""}).url == reverse("asistente:cortes")
    assert parametro("prefijo_pais_telefono") == 57
    assert "reglas" not in (AvanceAsistente.objects.get().estado.get("borradores") or {})
    assert 'name="prefijo_pais_telefono" value="57"' in c.get(reverse("asistente:reglas")).content.decode()


@pytest.mark.django_db
def test_cada_paso_del_asistente_dice_para_que_sirve():
    c = Client()
    c.post(reverse("asistente:inicio"), paso_inicio(settings.TOKEN_ASISTENTE))
    for paso in ("marca", "personalizar", "grupos", "conceptos", "pago", "caja", "reglas", "cortes", "usuario"):
        pagina = c.get(reverse(f"asistente:{paso}")).content.decode()
        assert re.search(r'<p class="subtitulo">[^<]{20,}</p>', pagina), paso


def test_consentimiento_oculto_no_borra_el_texto_guardado(roles):
    formulario = FormularioReglas({"prefijo_pais_telefono": "52", "digitos_telefono_nacional": "10", "tamano_hoja": "carta"}, valores={"texto_consentimiento": "Texto propio del negocio"})
    assert formulario.is_valid()
    assert formulario.valores()["texto_consentimiento"] == "Texto propio del negocio"
    assert (formulario.fields["texto_consentimiento"].depende["control"], formulario.fields["texto_consentimiento"].depende["valores"]) == ("pedir_consentimiento", ["on"])


def test_configuracion_explica_y_pliega(personas):
    d = cliente(personas["dir"])
    for ruta in ("configuracion:negocio", "configuracion:reglas", "configuracion:carpeta_banco", "configuracion:parametros", "configuracion:vocabulario"):
        pagina = d.get(reverse(ruta)).content.decode()
        assert '<p class="subtitulo">' in pagina, ruta
    assert "Más opciones" in d.get(reverse("configuracion:carpeta_banco")).content.decode()
    caja_pagina = d.get(reverse("configuracion:caja")).content.decode()
    assert "Más opciones" in caja_pagina and "muestra-piezas" in caja_pagina and "dias-corte" in caja_pagina
