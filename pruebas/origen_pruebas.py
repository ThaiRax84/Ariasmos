from banco.llegadas import Origen

PENDIENTES = []


class OrigenDePruebas(Origen):
    def __init__(self):
        super().__init__(clave="pruebas", nombre="Origen de pruebas")

    def consultar(self):
        avisos = list(PENDIENTES)
        PENDIENTES.clear()
        return avisos
