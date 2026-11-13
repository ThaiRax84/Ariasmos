# Guía de uso de Ariasmos

El sistema se usa desde el navegador en `https://NOMBRE-DEL-SERVIDOR/`. Cada persona entra con su usuario, su contraseña y, si su rol lo pide, el código de 6 dígitos de su autenticador. Lo que cada quien ve depende de su rol; esta guía sigue los tres roles de las plantillas: **Operación**, **Supervisión** y **Dirección**. Los nombres de los menús («titulares», «matrícula», «familias») pueden cambiar según cómo se configuró el vocabulario.

## Operación

### Dar de alta a un titular

1. Menú **Titulares** → **Nueva alta**.
2. Escribe nombre, apellidos, agrupación y el contacto responsable con su teléfono.
3. Si paga junto con otros (hermanos, por ejemplo), elige su familia o crea una nueva.
4. Guarda. El alta queda **pendiente** hasta que Supervisión la aprueba; al aprobarse recibe su **matrícula**, que es la referencia para pagar en el banco.
5. Desde la ficha del titular se imprime la **ficha de pago** con los datos bancarios y la matrícula.

### Cobrar en efectivo

1. Abre tu turno en **Mi caja** (el fondo inicial es opcional). Si el negocio captura piezas por denominación, escribe cuántos billetes y monedas de cada valor hay en el fondo.
2. Menú **Cobrar** → busca al titular por nombre o matrícula.
3. Escribe el importe recibido. El sistema muestra cómo se reparte entre los cargos pendientes (y los de su familia).
4. Si se capturan piezas: escribe los billetes y monedas que te entregan y elige **Calcular el cambio**. El sistema propone las piezas del cambio con las que debería haber en tu caja; entrega exactamente esas o corrígelas en pantalla antes de confirmar. Si no hay combinación exacta, te lo dice y tú escribes lo que entregas.
5. Confirma. Se emite el recibo foliado con su código de verificación y su **QR**; imprímelo o descárgalo en PDF.

### Retirar efectivo para un gasto

1. Con tu turno abierto, en **Mi caja** elige **Retirar efectivo**.
2. Escribe el importe, elige el motivo, anota en qué se gastó y adjunta la foto o el PDF del ticket (JPEG, PNG o PDF de hasta 5 MB). Puedes adjuntarlo después desde el retiro.
3. Si el retiro cabe en los topes del negocio, queda registrado de inmediato con su folio. Si pasa de algún tope, queda como **solicitud** y se registra cuando otra persona lo autoriza (por la bandeja, con una delegación o con su código por teléfono).
4. Solo se puede retirar efectivo cobrado en tu turno. Si no alcanza, el sistema lo dice sin decir cuánto hay; después de tres intentos así, los retiros de ese turno piden autorización.
5. No puedes cerrar el turno con retiros sin comprobante: adjúntalo o declara que no lo hay con su motivo (Supervisión recibe el aviso).
6. Un retiro no se borra. Si hubo un error, pide su **reversión**: la resuelve otra persona y el efectivo regresa a tu turno abierto.

### Corte diario

1. Al terminar el día, en **Mi caja** elige **Cerrar turno**.
2. Cuenta el efectivo por billete y moneda y guarda el conteo. No verás lo esperado hasta que el turno quede cerrado, y el conteo guardado ya no se puede cambiar.
3. Si coincide con lo que debe haber, el turno se cierra. Si no coincide, el sistema solo dice que **no coincide** (sin decir cuánto ni si sobra o falta) y te deja **recontar una sola vez** o cerrar con el primer conteo; en los dos casos escribe una nota.
4. Al cerrar ves lo esperado, lo contado y la diferencia, en total y, si se capturan piezas, por denominación. Se genera tu **corte diario**: recibos, devoluciones, retiros, lo contado y la diferencia. Lo ves en **Cortes**.
5. Cada negocio decide qué días hay corte y a qué hora. Un turno abierto en un día con corte debe cerrarse antes de la hora de ese día; si se abrió en un día sin corte, antes de la hora del siguiente día que sí tenga. Si cierras después, el corte queda marcado como **tardío**; no pasa nada más.
6. Entrega el efectivo a Supervisión desde **Mi caja** → **Entregar efectivo**; quien lo recibe lo confirma en su sesión.

### Vender artículos

Solo si el negocio lleva inventario (menú **Inventario**). Ver también la [guía de inventario](GUIA-INVENTARIO.md).

1. **Inventario** → **Vender a un titular** (o **Vender artículos** desde su ficha): elige artículos y cantidades. El precio lo pone cada artículo.
2. Elige cómo se paga: **Lo paga ahora** pasa al cobro, que se aplica primero a esos artículos y lo que sobre al adeudo normal; **Se va a su adeudo** deja los cargos pendientes para cobrarlos con lo demás.
3. **Vender sin matrícula** es para quien no es titular: se cobra completa en efectivo en ese momento, con tu turno abierto, y emite su recibo.
4. Si el sistema cree que no hay suficientes piezas, la venta no se detiene: avisa y Supervisión la revisa.

### Devoluciones, entradas, mermas y conteo

- **Devolución**: busca la venta por su número o por el recibo (código o QR). Lo no pagado se cancela; lo pagado regresa como **saldo a favor** al momento o en **efectivo**, que siempre se solicita y autoriza otra persona (sale de tu turno al aprobarse).
- **Entrada o merma**: artículo, cantidad, motivo y, si lo hay, el comprobante (JPEG, PNG o PDF de hasta 5 MB). No pide permiso; Supervisión la revisa después.
- **Conteo mensual**: descarga la lista para contar (no trae existencias), cuenta y sube el Excel o CSV con clave y cantidad, o captúralo en pantalla. Al guardarlo queda fijo, ves las diferencias y otra persona lo aprueba.

### Verificar un recibo

- **Verificar recibo** acepta el código del recibo con su folio, o el texto del QR: con un lector de códigos conectado por USB basta con leer el QR del recibo.
- Responde si el recibo es auténtico, si está cancelado o si no se reconoce. Después de varios intentos fallidos en una hora, la verificación se bloquea un rato para esa persona y esa computadora.

## Supervisión

### Aprobaciones

- En el **Inicio** aparece la bandeja de pendientes: altas, bajas, cancelaciones, becas, prórrogas y cambios de familia que pidió Operación.
- Abre cada una, revisa y elige **Aprobar** o **Rechazar** con un motivo.
- Nadie aprueba lo que él mismo pidió ni revierte un cobro que él mismo hizo.

### Banco

1. Menú **Banco** → **Importar**: sube el estado de cuenta en PDF o el archivo de movimientos del banco. Si hay carpeta vigilada, basta con dejar ahí el archivo descargado; el sistema lo importa solo y lo muestra en el Inicio.
2. Revisa la vista previa: cuántos pagos se aplican solos, cuántos quedan por identificar y cuántos ya estaban.
3. En la **cola** de movimientos por identificar, confirma a quién pertenece cada uno, o márcalo como «no es un cobro».
4. Los depósitos de efectivo de caja se emparejan con los movimientos del banco.
5. Lo que llega por la carpeta vigilada se aplica solo, salvo los movimientos **retenidos**: un estado en PDF que no continúa al anterior, o los movimientos de un Excel o CSV con una señal de sospecha (o todo el archivo si sus saldos no cuadran o rebasaría el tope de pagos sin respaldo). En el Inicio aparece la importación; ábrela, compara cada movimiento retenido con el banco (se ve su motivo), marca los que existen y elige **Liberar los marcados** o **Liberar todos**. Quien libera no puede marcar la importación como revisada.
6. **Pagos sin respaldo en el estado**: al importar el estado en PDF del mes, cada pago aplicado desde un Excel o CSV que no aparezca en él sale en el Inicio con un enlace para **solicitar su reversión**. El sistema no lo revierte solo. También avisa si un pago así lleva más de 45 días sin un estado que lo cubra.

### Efectivo

- **Efectivo** muestra quién tiene dinero en custodia, las entregas por confirmar y los depósitos por conciliar. Si tú mismo tienes un turno abierto, tu efectivo no se muestra hasta que lo cierres.
- Confirma las entregas que recibes contando el dinero; si no coincide, recházala.

### Retiros de caja

- **Efectivo** → **Retiros de caja** lista todos los retiros con su comprobante. Cada uno nace «por revisar»: ábrelo, revisa el comprobante y márcalo **Revisado** u **Observado** con una nota. Nadie revisa un retiro propio.
- En el **Inicio** aparecen avisos cuando una caja llega al 80 % de un tope del periodo, cuando un retiro se declara sin comprobante y cuando hay retiros sin revisar desde hace varios días.
- **Motivos de retiro** permite agregar o desactivar motivos.

### Inventario

- **Inventario** → **Revisión**: entradas, mermas, devoluciones a saldo a favor y ventas sin existencia por revisar; márcalas **Revisado** u **Observado**. Nadie revisa lo propio.
- Los conteos y las devoluciones en efectivo llegan a la bandeja de **Solicitudes**. Al aprobar un conteo se ajusta cada artículo con la diferencia del momento del conteo.
- **Artículos**: alta, precio, mínimo y concepto de cobro; un artículo no se borra, se desactiva. El Inicio avisa de los artículos en o bajo su mínimo.

### Corte mayor

1. El día 1 de cada mes el sistema prepara el **corte mayor** del mes anterior como borrador. Aparece en el **Inicio** y en **Cortes**.
2. Revísalo: ingresos por medio y por concepto, estado de cada titular, cartera vencida, caja, banco y, si se lleva, el resumen de inventario.
3. Elige **Cerrar el corte** (pide tu contraseña). El mes queda bloqueado: nada puede registrarse con fecha dentro de él.
4. Si nadie lo cierra en 5 días, el sistema lo cierra solo marcado como «sin revisar».

### Lista de cobranza

- Cada lunes se genera la lista de adeudos vencidos; en **Cortes** puedes generarla en cualquier momento.

## Dirección

### Usuarios y roles

- **Usuarios** → **Nuevo usuario**: el sistema muestra un **código de activación** que la persona usa para elegir su contraseña (nadie teclea la contraseña de otro).
- **Restablecer acceso** genera un código nuevo si alguien olvidó su contraseña o perdió su teléfono.
- **Roles** permite mover permisos entre roles.

### Configuración

- **Configuración**: datos del negocio, vocabulario, parámetros, catálogos, datos de pago, destinos de los cortes, **Caja: cortes y retiros** (días y horas de corte, piezas por denominación y topes de retiros), **Carpeta vigilada del banco** (con el tope de pagos sin respaldo y el tope por pago), **Inventario** (encenderlo, devoluciones y plazos) e importación inicial del padrón.
- **Equipos**: aprueba las computadoras nuevas y abre **Conectar otra computadora**.

### Respaldos

- **Respaldos** muestra el último respaldo y la última prueba de restauración. Si algo falla, aparece un aviso en el Inicio.
- **Respaldar ahora** y **Probar el último respaldo** se pueden hacer en cualquier momento.
- **Generar clave nueva** cambia la clave de los respaldos futuros. Los respaldos anteriores siguen abriéndose solo con la clave anterior: no la tires.

### Revisión de importaciones

- Cuando alguien importa un archivo de banco que no se puede comprobar contra el estado de cuenta anterior y con él se aplicaron pagos, aparece en tu Inicio como **importación por revisar**.
- Ábrela, compárala con el banco y elige **Marcar como revisada**. Quien la importó, o quien liberó alguno de sus movimientos si llegó por la carpeta vigilada, no puede marcarla.
- Si el negocio lleva inventario, el Inicio te avisa cuando un conteo lleva más días de los configurados sin aprobarse.

### Bitácora

- **Auditoría** muestra cada cambio del sistema: quién, cuándo y qué cambió. **Verificar** comprueba que nadie alteró ni borró eventos.
- En la ficha de cada titular está su historial en lenguaje llano.
