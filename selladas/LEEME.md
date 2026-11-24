# Pruebas selladas — fase 1a (licencias)

Pruebas de ataque escritas contra `contrato-1a.md` antes de construir la fase: una por cada uno de los 10 ataques de la sección 4.
`producto/` cubre los ataques 1–5 y la mitad del 7 en el programa; `central/` cubre la otra mitad del 7 y los ataques 6–10 en Ariasmos Central.
No se modifican para que pasen: si una falla, se corrige el código o se reporta el hueco del contrato.
Las llaves de prueba se generan al vuelo; no hay secretos ni datos reales.

    python -m pytest -q selladas/producto
    python -m pytest -q --ds=proyecto_central.ajustes_pruebas selladas/central

## Cambios a pruebas selladas

- 23 nov 2026, vuelta 3. Lo ordenó el arquitecto, con autorización de Máximo para la vuelta 3 (contrato, 9.1).
- `central/test_central.py` (`test_sin_pago_o_revocado_central_no_emite`): las tres aserciones `== {"resultado": "pago_pendiente"}` pasan a exigir claves exactas `{"resultado", "acuse"}` con acuse válido de Central (ayuda nueva `pago_pendiente`).
- `central/test_vuelta2_central.py`: lo mismo en la activación repetida sin pago y en `test_renovada_y_activada_traen_acuse_de_central`; ahí `revocada` pasa de `{"resultado", "documento"}` a `{"resultado", "documento", "acuse"}`, con el documento abriendo como revocación y el acuse como acuse.
- Motivo: sin la hora firmada de Central en esas respuestas, un cliente que no paga y manipula su reloj nunca es corregido.
