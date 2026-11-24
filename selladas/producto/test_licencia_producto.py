import base64
import json
import re
import uuid
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Evento
from cobros.models import Pago
from licencias import cliente as cliente_central
from licencias import llaves, reloj, servicios
from licencias.models import Instalacion
from nucleo.licencia import LicenciaInvalida, firmar, huella, serializar, texto_de
from pruebas.conftest import CONTRASENA, cliente, codigo_actual
from pruebas.libro_ayudas import campos_piezas, preparar_conceptos, titular_activo, turno_de
from solicitudes.models import Solicitud
from titulares.models import CampoContacto, Titular

CANDADO = "X-Ariasmos-Licencia"


def crudos(privada):
    return privada.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def huella_nueva():
    return huella(crudos(Ed25519PrivateKey.generate()))


class Reloj:
    def __init__(self, momento):
        self.momento = momento

    def __call__(self):
        return self.momento

    def avanzar(self, **delta):
        self.momento += timedelta(**delta)


@pytest.fixture
def central(tmp_path, monkeypatch):
    privada = Ed25519PrivateKey.generate()
    ruta = tmp_path / "llaves.json"
    ruta.write_text(json.dumps({"licencias": [base64.b64encode(crudos(privada)).decode()]}), encoding="utf-8")
    monkeypatch.setattr(llaves, "RUTA", ruta)
    return privada


@pytest.fixture
def hora(monkeypatch):
    actual = Reloj(timezone.now().replace(microsecond=0))
    monkeypatch.setattr(reloj, "ahora", actual)
    return actual


@pytest.fixture
def local(db, central, hora):
    return servicios.instalacion()


def licencia(privada, instalacion, emitida, dias=30, gracia=14, **cambios):
    carga = {
        "formato": 1,
        "producto": "ariasmos",
        "tipo": "licencia",
        "negocio": str(uuid.uuid4()),
        "instalacion": instalacion,
        "plan": "base",
        "modulos": [],
        "serie": 1,
        "emitida": texto_de(emitida),
        "vence": texto_de(emitida + timedelta(days=dias)),
        "dias_gracia": gracia,
    }
    carga.update(cambios)
    return firmar(carga, privada)


def revocacion(privada, instalacion, emitida):
    carga = {"formato": 1, "producto": "ariasmos", "tipo": "revocacion", "negocio": str(uuid.uuid4()), "instalacion": instalacion, "emitida": texto_de(emitida)}
    return firmar(carga, privada)


def alterar(documento, **cambios):
    carga = json.loads(base64.b64decode(documento["carga"]))
    carga.update(cambios)
    return {"carga": base64.b64encode(serializar(carga)).decode(), "firma": documento["firma"]}


def guardado():
    fila = Instalacion.objects.get()
    return fila.documento, fila.revocacion, fila.mayor_momento


def responder(monkeypatch, resultado, documento):
    monkeypatch.setattr(cliente_central, "enviar", lambda ruta, cuerpo: (200, {"resultado": resultado, "documento": documento}))


def rechazos(motivo):
    return Evento.objects.filter(accion="licencia_rechazada", datos__motivo=motivo).count()


@pytest.mark.parametrize("campo, valor", [
    ("vence", lambda t: texto_de(t + timedelta(days=3650))),
    ("plan", lambda t: "completo"),
    ("modulos", lambda t: ["inventario", "banco"]),
])
def test_licencia_alterada_se_rechaza_y_nada_cambia(central, hora, local, campo, valor):
    buena = licencia(central, local.huella, hora.momento)
    servicios.instalar(buena)
    antes, situacion_antes = guardado(), servicios.situacion()
    alterada = alterar(buena, **{campo: valor(hora.momento)})

    with pytest.raises(LicenciaInvalida) as error:
        servicios.instalar(alterada)
    assert error.value.motivo == "firma"
    assert guardado() == antes and servicios.situacion() == situacion_antes
    assert rechazos("firma") == 1

    Instalacion.objects.update(documento=json.dumps(alterada))
    assert servicios.situacion().estado == "por_activar"
    hora.avanzar(days=60)
    situacion = servicios.situacion()
    assert (situacion.estado, situacion.motivo) == ("solo_consulta", "sin_licencia") and not servicios.permite_escribir()


@pytest.mark.parametrize("firmante", ["llave_ajena", "llave_de_la_instalacion"])
def test_licencia_firmada_con_otra_llave_se_rechaza(central, hora, local, firmante, monkeypatch):
    privada = Ed25519PrivateKey.generate() if firmante == "llave_ajena" else servicios.identidad()[1]
    falsa = licencia(privada, local.huella, hora.momento, dias=3650, plan="completo")

    with pytest.raises(LicenciaInvalida) as error:
        servicios.instalar(falsa)
    assert error.value.motivo == "firma"
    assert Instalacion.objects.get().documento == "" and rechazos("firma") == 1

    responder(monkeypatch, "renovada", falsa)
    assert servicios.renovar() == "rechazada"
    assert Instalacion.objects.get().documento == ""

    Instalacion.objects.update(documento=json.dumps(falsa))
    hora.avanzar(days=60)
    assert servicios.situacion().estado == "solo_consulta"


@pytest.mark.parametrize("mismo_negocio", [True, False])
def test_licencia_de_otra_instalacion_se_rechaza(central, hora, local, mismo_negocio, monkeypatch):
    negocio = str(uuid.uuid4())
    servicios.instalar(licencia(central, local.huella, hora.momento, negocio=negocio))
    antes = guardado()
    ajena = licencia(central, huella_nueva(), hora.momento + timedelta(minutes=1), dias=3650, plan="completo", negocio=negocio if mismo_negocio else str(uuid.uuid4()))

    with pytest.raises(LicenciaInvalida) as error:
        servicios.instalar(ajena)
    assert error.value.motivo == "ajena"
    assert guardado() == antes and rechazos("ajena") == 1

    responder(monkeypatch, "renovada", ajena)
    assert servicios.renovar() == "rechazada"
    assert guardado() == antes

    Instalacion.objects.update(documento=json.dumps(ajena))
    assert servicios.situacion().estado == "por_activar"


def test_atrasar_el_reloj_no_devuelve_la_escritura(central, hora, local):
    servicios.instalar(licencia(central, local.huella, hora.momento, dias=30, gracia=14))
    hora.avanzar(days=45)
    vencida = servicios.situacion()
    assert (vencida.estado, vencida.motivo) == ("solo_consulta", "vencida")
    mayor = hora.momento

    for atraso in (30, 15):
        hora.avanzar(days=-atraso)
        situacion = servicios.situacion()
        assert (situacion.estado, situacion.motivo) == ("solo_consulta", "vencida")
        assert not servicios.permite_escribir()
        assert servicios.momento_efectivo() >= mayor
    assert Instalacion.objects.get().mayor_momento >= mayor
    assert Evento.objects.filter(accion="reloj_atrasado").exists()


def datos_alta(nombre):
    campo = CampoContacto.objects.get(tipo=CampoContacto.TELEFONO)
    return {"nombre": nombre, "apellidos": "Prueba", "contacto_nombre": "Responsable", campo.clave: "55 1234 5678", "constancia_consentimiento": "on"}


def ficha_de_cobro(c, titular, importe):
    texto = c.post(reverse("cobros:cobrar", args=[titular.pk]), {"importe": importe}).content.decode()
    return re.search(r'name="ficha" value="([^"]+)"', texto).group(1), re.search(r'name="importe" value="(\d+)"', texto).group(1)


def confirmar_cobro(c, titular, ficha, centavos):
    return c.post(reverse("cobros:cobrar", args=[titular.pk]), {"paso": "confirmar", "ficha": ficha, "importe": centavos, **campos_piezas(int(centavos), "r_")})


def bloqueada(respuesta):
    return respuesta.status_code == 403 and respuesta.get(CANDADO) == "solo-consulta" and respuesta.get("Content-Type") == "text/plain; charset=utf-8" and len(respuesta.content) > 0


def test_el_candado_no_se_salta_y_deja_consultar_entrar_y_respaldar(central, hora, local, personas):
    preparar_conceptos()
    ana = titular_activo(personas["op"], personas["sup"], "Ana")
    turno_de(personas["op"])
    op, sup, direccion = cliente(personas["op"]), cliente(personas["sup"]), cliente(personas["dir"])
    servicios.instalar(licencia(central, local.huella, hora.momento, dias=1, gracia=14))

    hora.avanzar(days=5)
    assert servicios.situacion().estado == "gracia"
    ficha, centavos = ficha_de_cobro(op, ana, "1000")
    cobrado = confirmar_cobro(op, ana, ficha, centavos)
    alta = sup.post(reverse("titulares:nuevo"), datos_alta("Gracia"))
    for respuesta in (cobrado, alta):
        assert respuesta.status_code == 302 and CANDADO not in respuesta
    assert Pago.objects.count() == 1 and Titular.objects.filter(nombre="Gracia").exists()
    ficha_pendiente, centavos_pendientes = ficha_de_cobro(op, ana, "500")

    hora.avanzar(days=20)
    assert servicios.situacion().estado == "solo_consulta"
    pagos, titulares, solicitudes = Pago.objects.count(), Titular.objects.count(), Solicitud.objects.count()
    cobrar = reverse("cobros:cobrar", args=[ana.pk])
    intentos = [
        confirmar_cobro(op, ana, ficha_pendiente, centavos_pendientes),
        op.post(cobrar, {"importe": "300"}),
        op.put(cobrar, "importe=300", content_type="application/x-www-form-urlencoded"),
        op.delete(cobrar),
        sup.post(reverse("titulares:nuevo"), datos_alta("Bloqueada")),
        sup.post(reverse("titulares:editar", args=[ana.pk]), {"nombre": "Cambiado", "apellidos": ana.apellidos, "agrupacion": ana.agrupacion_id or "", "notas": ana.notas}),
        op.post(reverse("titulares:editar", args=[ana.pk]), {"nombre": "Cambiado", "apellidos": ana.apellidos, "agrupacion": ana.agrupacion_id or "", "notas": ana.notas}),
    ]
    assert all(bloqueada(respuesta) for respuesta in intentos)
    ana.refresh_from_db()
    assert (Pago.objects.count(), Titular.objects.count(), Solicitud.objects.count(), ana.nombre) == (pagos, titulares, solicitudes, "Ana")

    detalle = op.get(reverse("titulares:detalle", args=[ana.pk]))
    pdf = op.get(reverse("titulares:estado_pdf", args=[ana.pk]))
    assert detalle.status_code == 200 and CANDADO not in detalle
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf" and CANDADO not in pdf

    entrada = cliente()
    primer_paso = entrada.post(reverse("entrar"), {"usuario": "supervision", "contrasena": CONTRASENA})
    assert primer_paso.status_code == 302 and primer_paso.url == reverse("entrar_codigo") and CANDADO not in primer_paso
    segundo_paso = entrada.post(reverse("entrar_codigo"), {"codigo": codigo_actual(personas["sup"])})
    assert segundo_paso.status_code == 302 and CANDADO not in segundo_paso

    respaldo = direccion.post(reverse("respaldos:respaldar"))
    assert respaldo.status_code != 403 and CANDADO not in respaldo


def test_revocacion_sin_firma_valida_de_central_no_bloquea(central, hora, local, monkeypatch):
    servicios.instalar(licencia(central, local.huella, hora.momento))
    despues = hora.momento + timedelta(minutes=1)
    autentica_ajena = revocacion(central, huella_nueva(), despues)
    falsas = [
        ("firma", revocacion(Ed25519PrivateKey.generate(), local.huella, despues)),
        ("firma", revocacion(servicios.identidad()[1], local.huella, despues)),
        ("firma", alterar(autentica_ajena, instalacion=local.huella)),
        ("ajena", autentica_ajena),
        ("antigua", revocacion(central, local.huella, hora.momento - timedelta(days=1))),
    ]
    for motivo, falsa in falsas:
        with pytest.raises(LicenciaInvalida) as error:
            servicios.anotar_revocacion(falsa)
        assert error.value.motivo == motivo
        assert Instalacion.objects.get().revocacion == "" and servicios.situacion().estado == "vigente"

    responder(monkeypatch, "revocada", falsas[0][1])
    assert servicios.renovar() == "rechazada"
    assert Instalacion.objects.get().revocacion == ""

    for _, falsa in falsas:
        Instalacion.objects.update(revocacion=json.dumps(falsa))
        assert servicios.situacion().estado == "vigente" and servicios.permite_escribir()
