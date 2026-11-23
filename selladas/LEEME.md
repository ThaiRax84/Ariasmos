# Pruebas selladas — fase 1a (licencias)

Pruebas de ataque escritas contra `contrato-1a.md` antes de construir la fase: una por cada uno de los 10 ataques de la sección 4.
`producto/` cubre los ataques 1–5 y la mitad del 7 en el programa; `central/` cubre la otra mitad del 7 y los ataques 6–10 en Ariasmos Central.
No se modifican para que pasen: si una falla, se corrige el código o se reporta el hueco del contrato.
Las llaves de prueba se generan al vuelo; no hay secretos ni datos reales.

    python -m pytest -q selladas/producto
    python -m pytest -q --ds=proyecto_central.ajustes_pruebas selladas/central
