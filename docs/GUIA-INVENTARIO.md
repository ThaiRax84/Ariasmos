# Guía de inventario

El inventario es opcional y está pensado para inventarios pequeños (libros, útiles, uniformes y similares). Se enciende en el paso 1 del asistente o en *Configuración → Inventario*; apagado, el menú **Inventario** no aparece. Los nombres de los menús («titular», «matrícula») pueden cambiar según el vocabulario del negocio.

## Quién hace qué

| Acción | Operación | Supervisión | Dirección |
|---|:-:|:-:|:-:|
| Vender artículos | ✓ | ✓ | ✓ |
| Registrar devoluciones | ✓ | ✓ | ✓ |
| Registrar entradas y mermas | ✓ | ✓ | ✓ |
| Subir el conteo | ✓ | ✓ | ✓ |
| Ver cuántas piezas quedan al vender | ✓ | ✓ | ✓ |
| Ver existencias y revisar movimientos | — | ✓ | ✓ |
| Administrar artículos | — | ✓ | ✓ |
| Aprobar conteos y devoluciones en efectivo | — | ✓ | ✓ |
| Encender el inventario y sus plazos | — | — | ✓ |

Los permisos se pueden mover en **Roles**. Nadie revisa ni aprueba lo que él mismo registró.

## Artículos

**Inventario → Artículos → Artículo nuevo**: clave (letras mayúsculas, números, punto o guion), nombre, precio, existencia mínima y el concepto de cobro al que pertenece (por ejemplo, «Libros»). Un artículo no se borra: se desactiva.

La existencia no se escribe a mano. Resulta de los movimientos: carga inicial, entradas, ventas, devoluciones, mermas y ajustes por conteo. Nadie puede editar ni borrar un movimiento.

## Carga inicial

La primera vez se hace un conteo (ver abajo). Cuando otra persona lo aprueba, cada artículo queda con lo contado como carga inicial.

## Vender

1. **Inventario → Vender**, busca a la persona y elige su nombre. Arriba a la derecha cambias entre **A un titular** y **Sin matrícula**.
2. La pantalla muestra todos los artículos activos con su precio y lo que queda. Escribe arriba parte del nombre o de la clave para filtrar la lista. En cada artículo usa **+** y **−** (o escribe la cantidad) para decir cuántos se lleva; los que quedan en 0 no entran en la venta. El precio lo pone el artículo; no se teclea. **+** no se detiene en la existencia: si el sistema cree que no alcanza, la venta sigue y queda para revisión.
3. A la derecha, **Resumen** suma lo elegido y el **Total**. Es solo una ayuda en pantalla: al continuar, el sistema vuelve a calcular todo con los precios guardados. Si el navegador no ejecuta el programa de la pantalla, el resumen dice que el total se calcula al continuar.
4. Elige **¿Cómo se paga?**:
   - **Lo paga ahora**: se crean los cargos y pasas al cobro (**Continuar al cobro**). El pago se aplica primero a los artículos de esta venta y lo que sobre, al adeudo normal.
   - **Se va a su adeudo**: los cargos quedan pendientes y se cobran después junto con lo demás (**Registrar la venta**).
5. **Sin matrícula** es para quien no es titular: mismo catálogo con **+** y **−**. Necesita tu turno de caja abierto; al continuar ves lo que se lleva y el total, y se cobra completa en efectivo en ese momento contra la cuenta interna «Público en general», que nunca queda con adeudo. Si se capturan piezas por denominación, el cambio se calcula igual que en un cobro.
6. Al vender ves cuántas piezas quedan de cada artículo; cuando no queda ninguna no se muestra número. Si la existencia está en 20 % o menos de su nivel de referencia (lo que había justo después de su última entrada o de su último conteo aprobado), o en su mínimo si se le fijó uno, el artículo se marca **pocas** y Supervisión ve el aviso de **existencia baja** en su inicio. El porcentaje se cambia en **Configuración → Inventario**.
7. Si el sistema cree que no hay suficientes piezas, la venta no se detiene: avisa y Supervisión la revisa.
8. Si algo no es válido (una cantidad negativa o un artículo que ya no está activo), la pantalla lo dice y conserva las cantidades que habías puesto.

## Devolver

Solo si el negocio acepta devoluciones y dentro del plazo configurado.

1. **Inventario → Devolución**: busca la venta por su número (`V-12`) o por su recibo (código de verificación o lector de QR).
2. Escribe cuántas piezas regresan de cada artículo (nunca más de lo vendido y no devuelto) y marca si alguna viene en mal estado: esa regresa y sale como merma en el mismo acto.
3. Lo que todavía no se pagó de esos artículos se cancela. Lo que ya se pagó regresa:
   - como **saldo a favor**, al momento, y Supervisión lo revisa después; o
   - en **efectivo**, que siempre queda como solicitud y autoriza otra persona (ni quien la pidió ni quien cobró la venta). Al aprobarse, el efectivo sale del turno abierto de quien la pidió y solo si ese turno lo tiene. Entra en el corte diario y en el esperado del arqueo.
4. Una venta sin matrícula solo se devuelve en efectivo.

Si se revierte por completo el pago de una venta, el sistema pregunta artículo por artículo si regresó: lo que regresó vuelve a existencias y se cancela de su cargo; lo que no, queda como adeudo (en una venta sin matrícula se cancela, porque esa cuenta nunca queda con adeudo).

## Entradas y mermas

**Inventario → Entrada o merma**: tipo, artículo, cantidad, motivo y, si lo hay, la foto o el PDF del comprobante (JPEG, PNG o PDF de hasta 5 MB; se guarda sin metadatos). No piden permiso previo: nacen «por revisar» y otra persona las marca revisadas u observadas.

## Conteo mensual

1. **Inventario → Conteo mensual → Descargar la lista para contar**. La lista trae clave y nombre, sin existencias.
2. Cuenta en físico y escribe la cantidad de cada artículo.
3. Sube el Excel (`.xlsx`) o CSV con las columnas `clave` y `cantidad`, o captura el conteo en pantalla (deja en blanco lo que no contaste).
4. Al guardarlo el conteo queda fijo y se muestran las diferencias contra lo que el sistema esperaba en ese momento.
5. Otra persona lo aprueba desde **Solicitudes** (bandeja, delegación o código por teléfono). Al aprobarse se ajusta cada artículo exactamente con la diferencia del momento del conteo; las ventas y entradas posteriores no se tocan.

Solo puede haber un conteo en espera. Si lleva más de los días configurados sin aprobarse, Dirección ve un aviso en su Inicio.

El archivo se revisa antes de usarlo: hasta 1 MB y 5 000 renglones; se rechaza con su número de renglón cualquier clave desconocida o repetida, cantidad que no sea un número entero de 0 en adelante, y cualquier fórmula.

## Revisión

**Inventario → Revisión** (Supervisión) reúne lo pendiente: entradas y mermas, devoluciones a saldo a favor y ventas que se hicieron sin existencia, además de los artículos en o bajo su mínimo. **Descargar existencias (CSV)** entrega el resumen actual.

## Cortes

El corte mayor incluye, por artículo, la existencia al cierre del mes y las ventas, devoluciones, entradas, mermas y ajustes del periodo. El corte diario de caja lista las devoluciones de artículos pagadas en efectivo.
