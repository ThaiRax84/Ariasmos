import base64
import json
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Evento
from configuracion import trabajador
from configuracion.models import Tarea
from licencias import cliente, llaves, reloj, servicios
from licencias.models import Instalacion
from nucleo import licencia

from .conftest import cliente as cliente_web
from .conftest import nuevo_usuario


class Central:
    def __init__(self, tmp_path, monkeypatch):
        self.privada = Ed25519PrivateKey.generate()
        self.ahora = timezone.now()
        archivo = tmp_path / "llaves.json"
        publica = self.privada.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

        archivo.write_text(json.dumps({"licencias": [base64.b64encode(publica).decode()]}))
        monkeypatch.setattr(llaves, "RUTA", archivo)
        monkeypatch.setattr(reloj, "ahora", lambda: self.ahora)
        self.respuestas = []
        monkeypatch.setattr(cliente, "enviar", lambda ruta, cuerpo: self.respuestas.pop(0))

    def licencia(self, dias=30, gracia=14, firmante=None, huella=None, emitida=None):
        emitida = emitida or self.ahora
        carga = {
            "formato": 1, "producto": "ariasmos", "tipo": "licencia", "negocio": "n", "instalacion": huella or servicios.identidad()[0],
            "plan": "base", "modulos": [], "serie": 1, "emitida": licencia.texto_de(emitida),
            "vence": licencia.texto_de(emitida + timedelta(days=dias)), "dias_gracia": gracia,
        }
        return licencia.firmar(carga, firmante or self.privada)

    def revocacion(self, emitida=None):
        carga = {"formato": 1, "producto": "ariasmos", "tipo": "revocacion", "negocio": "n", "instalacion": servicios.identidad()[0], "emitida": licencia.texto_de(emitida or self.ahora)}
        return licencia.firmar(carga, self.privada)


@pytest.fixture
def central(db, tmp_path, monkeypatch):
    return Central(tmp_path, monkeypatch)


def test_licencia_alterada_ajena_o_de_otra_llave_no_se_instala(central):
    buena = central.licencia()
    carga = json.loads(base64.b64decode(buena["carga"]))
    carga["vence"] = "2099-01-01T00:00:00Z"
    alterada = {"carga": base64.b64encode(licencia.serializar(carga)).decode(), "firma": buena["firma"]}
    intentos = [alterada, central.licencia(firmante=Ed25519PrivateKey.generate()), central.licencia(huella="a" * 64)]
    motivos = []
    for documento in intentos:
        with pytest.raises(licencia.LicenciaInvalida) as error:
            servicios.instalar(documento)
        motivos.append(error.value.motivo)
    assert motivos == ["firma", "firma", "ajena"]
    assert servicios.situacion().estado == "por_activar"
    assert servicios.instalar(buena).estado == "vigente"
    with pytest.raises(licencia.LicenciaInvalida):
        servicios.instalar(central.licencia(emitida=central.ahora - timedelta(days=1)))


def test_atrasar_el_reloj_no_devuelve_el_permiso(central):
    servicios.instalar(central.licencia(dias=1, gracia=1))
    central.ahora += timedelta(days=5)
    assert servicios.situacion().motivo == "vencida"
    central.ahora -= timedelta(days=5)
    assert not servicios.permite_escribir()
    assert Evento.objects.filter(accion="reloj_atrasado").count() == 1


def test_candado_en_solo_consulta_deja_consultar_y_respaldar_pero_no_escribir(central, roles):
    usuario = nuevo_usuario("direccion", roles["Dirección"])
    web = cliente_web(usuario)
    servicios.instalar(central.licencia(dias=1, gracia=0))
    central.ahora += timedelta(days=2)
    bloqueada = web.post(reverse("usuario_nuevo"), {})
    assert bloqueada.status_code == 403
    assert bloqueada["X-Ariasmos-Licencia"] == "solo-consulta"
    assert "X-Ariasmos-Licencia" not in web.get(reverse("inicio"))
    assert "X-Ariasmos-Licencia" not in web.post(reverse("respaldos:probar"))
    central.ahora -= timedelta(days=2)
    servicios.instalar(central.licencia(dias=1, gracia=10, emitida=central.ahora + timedelta(minutes=1)))
    central.ahora += timedelta(days=5)
    assert servicios.situacion().estado == "gracia"
    assert "X-Ariasmos-Licencia" not in web.post(reverse("usuario_nuevo"), {})


def test_renovar_instala_revoca_y_rechaza_lo_falso(central):
    central.respuestas = [(200, {"resultado": "renovada", "documento": central.licencia()})]
    assert servicios.renovar() == "renovada"
    assert servicios.situacion().estado == "vigente"
    central.ahora += timedelta(minutes=1)
    falsa = central.licencia(firmante=Ed25519PrivateKey.generate())
    central.respuestas = [(200, {"resultado": "renovada", "documento": falsa})]
    assert servicios.renovar() == "rechazada"
    central.respuestas = [(200, {"resultado": "revocada", "documento": falsa})]
    assert servicios.renovar() == "rechazada"
    assert servicios.situacion().estado == "vigente"
    central.respuestas = [(200, {"resultado": "revocada", "documento": central.revocacion()})]
    assert servicios.renovar() == "revocada"
    assert servicios.situacion().motivo == "revocada"
    assert Instalacion.objects.get().ultimo_resultado == "revocada"


def test_trabajador_omite_sin_fallar_lo_que_escribe_en_solo_consulta(central):
    servicios.instalar(central.licencia(dias=1, gracia=0))
    central.ahora += timedelta(days=2)
    informe = {nombre: (exito, texto) for nombre, exito, texto in trabajador.ejecutar_ciclo()}
    omitidas = [nombre for nombre, (_, texto) in informe.items() if texto.startswith("omitida")]
    assert sorted(omitidas) == sorted(trabajador.ESCRIBEN_DATOS)
    assert all(informe[nombre][0] for nombre in omitidas)
    assert not Evento.objects.filter(accion="tarea_fallida", datos__tarea__in=omitidas).exists()
    assert not Tarea.objects.filter(nombre__in=omitidas).exists()


def test_llaves_danadas_no_tumban_el_programa_ni_el_acceso(central, roles, tmp_path, monkeypatch):
    web = cliente_web(nuevo_usuario("direccion", roles["Dirección"]))
    rota = tmp_path / "rota.json"
    rota.write_text("{")
    monkeypatch.setattr(llaves, "RUTA", rota)
    assert servicios.situacion().motivo == "llaves"
    assert "X-Ariasmos-Licencia" not in web.post(reverse("respaldos:probar"))
    assert web.post(reverse("usuario_nuevo"), {})["X-Ariasmos-Licencia"] == "solo-consulta"
    assert servicios.renovar() == "apagada"
    informe = {nombre: texto for nombre, _, texto in trabajador.ejecutar_ciclo()}
    assert informe["generar_cargos"].startswith("omitida")


def test_cliente_nunca_deja_salir_una_excepcion_de_red(settings, monkeypatch):
    class Cuerpo:
        def read(self, *_):
            raise TimeoutError("sin cuerpo")

        def close(self):
            pass

    def abrir(self, peticion, timeout=None):
        raise cliente.urllib.error.HTTPError("https://central.invalid/x", 403, "no", {}, Cuerpo())

    monkeypatch.setattr(cliente.urllib.request.OpenerDirector, "open", abrir)
    assert cliente.enviar("/v1/renovar", {}) == (403, {})


def test_firma_valida_con_valores_absurdos_se_rechaza(central):
    for cambio in ({"dias_gracia": 10**9}, {"serie": 2**70}, {"vence": "2000-01-01T00:00:00Z"}, {"vence": "9999-12-31T23:59:59Z"}):
        carga = json.loads(base64.b64decode(central.licencia()["carga"]))
        carga.update(cambio)
        with pytest.raises(licencia.LicenciaInvalida) as error:
            servicios.instalar(licencia.firmar(carga, central.privada))
        assert error.value.motivo == "campos"
