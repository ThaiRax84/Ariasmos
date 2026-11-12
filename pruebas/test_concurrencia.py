import threading

import pytest
from django.db import connection

from auditoria.servicios import verificar_cadena
from configuracion.models import Negocio
from cuentas.models import Usuario
from nucleo.matricula import es_valida
from titulares.models import Titular
from titulares.servicios import crear_titular

from .conftest import configurar, nuevo_usuario

HILOS = 8
POR_HILO = 15


@pytest.mark.django_db(transaction=True)
def test_asignacion_concurrente_de_matriculas():
    roles = configurar("escuela")
    usuario = nuevo_usuario("capturista", roles["Operación"])
    errores = []
    barrera = threading.Barrier(HILOS)

    def trabajar(numero):
        try:
            propio = Usuario.objects.get(pk=usuario.pk)
            barrera.wait()
            for i in range(POR_HILO):
                crear_titular(propio, {"nombre": f"H{numero}", "apellidos": f"N{i}"})
        except Exception as error:
            errores.append(error)
        finally:
            connection.close()

    hilos = [threading.Thread(target=trabajar, args=(n,)) for n in range(HILOS)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert not errores, errores
    matriculas = list(Titular.objects.values_list("matricula", flat=True))
    assert len(matriculas) == HILOS * POR_HILO
    assert len(set(matriculas)) == len(matriculas)
    assert all(es_valida(m, 7) for m in matriculas)
    assert Negocio.objects.get(pk=1).contador_matricula >= HILOS * POR_HILO
    assert verificar_cadena().valida
