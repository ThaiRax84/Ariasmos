# Guía de uso de Ariasmos

El sistema se usa desde el navegador en `https://NOMBRE-DEL-SERVIDOR/`. Cada persona entra con su usuario, su contraseña y, si su rol lo pide, el código de 6 dígitos de su autenticador. Lo que cada quien ve depende de su rol; esta guía sigue los tres roles de las plantillas: **Operación**, **Supervisión** y **Dirección**. Los nombres de los menús («titulares», «matrícula», «familias») pueden cambiar según cómo se configuró el vocabulario.

## La pantalla

- Al abrir el programa aparece una vez la presentación de Ariasmos con su versión («ver. 0.7.0»); se quita sola en un par de segundos o con un clic o cualquier tecla, y no vuelve a salir hasta que cierres el navegador. Si tu equipo tiene activado «reducir movimiento», no aparece.
- Arriba está la marca de Ariasmos y, a su lado, el logo y el nombre del negocio. Las entradas más usadas del menú se ven siempre (Inicio, Cobrar, el padrón, Inventario, Mi caja, Banco, Efectivo, Solicitudes y Cortes, según tu rol); las demás (familias, conceptos, usuarios, roles, configuración, respaldos, bitácora y otras) están en **Más**. **Más** se abre con un clic o con Enter y se recorre con las flechas; Esc lo cierra.
- A la derecha ves tu nombre, tu rol y, si tienes turno abierto, la caja y la hora en que lo abriste.
- Las acciones que mueven dinero o no se deshacen piden confirmación en un recuadro propio del programa; los avisos de que algo salió bien aparecen abajo unos segundos.

## El Inicio

Cada rol ve un Inicio distinto:

- **Operación**: tu turno abierto con el **número** de cobros (nunca importes ni el efectivo esperado), el buscador del padrón, el aviso de la hora límite de tu corte, los accesos rápidos y tus solicitudes en espera.
- **Supervisión**: cuatro cuadros (cobrado hoy, efectivo sin entregar, banco por identificar y corte diario pendiente), la lista **Por autorizar** y la lista **Por revisar** con los avisos de control.
- **Dirección**: cuatro cuadros (cobrado en el mes con su reparto entre efectivo y banco, por cobrar vencido, efectivo en custodia y retiros de la semana), **Salud del sistema** (bitácora, respaldo, prueba de restauración, certificado y equipos por aprobar) y **Avisos de control**.
- Cada cuadro aparece solo si tu rol tiene el permiso correspondiente. Si tienes un turno de caja abierto, los cuadros de cobrado y de efectivo dicen «Se muestra al cerrar tu turno»: el arqueo sigue siendo ciego.
- Cada aviso lleva una etiqueta (**Revisar**, **Por hacer**, **Por revisar**, **Bien**…) y un enlace a donde se atiende.

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
3. A la izquierda ves los cargos pendientes y arriba a la derecha el adeudo. Escribe el importe (solo el número: el signo y la moneda ya vienen puestos). El sistema muestra en **Así se va a aplicar** cómo se reparte entre los cargos pendientes (y los de su familia).
4. Si se capturan piezas: toca cada billete o moneda que te entregan (con **−** quitas una; también puedes escribir el número) y elige **Calcular el cambio**. Mientras tocas, **Recibido** suma lo que capturaste. El recuadro **Entrega exactamente estas piezas** dice qué piezas dar de cambio para que tu caja cuadre en el corte; si entregas otras, ábrelas con **Di el cambio con otras piezas** y corrígelas antes de confirmar. Si no hay combinación exacta, te lo dice y tú escribes lo que entregas.
5. Elige **Confirmar y dar recibo**. Se emite el recibo foliado con su código de verificación y su **QR**; imprímelo o descárgalo en PDF.

### Retirar efectivo para un gasto

1. Con tu turno abierto, en **Mi caja** elige **Retirar efectivo**.
2. Escribe el importe, elige el motivo, anota en qué se gastó y adjunta la foto o el PDF del ticket (JPEG, PNG o PDF de hasta 5 MB). Puedes adjuntarlo después desde el retiro.
3. Si el retiro cabe en los topes del negocio, queda registrado de inmediato con su folio. Si pasa de algún tope, queda como **solicitud** y se registra cuando otra persona lo autoriza (por la bandeja, con una delegación o con su código por teléfono).
4. Solo se puede retirar efectivo cobrado en tu turno. Si no alcanza, el sistema lo dice sin decir cuánto hay; después de tres intentos así, los retiros de ese turno piden autorización.
5. No puedes cerrar el turno con retiros sin comprobante: adjúntalo o declara que no lo hay con su motivo (Supervisión recibe el aviso).
6. Un retiro no se borra. Si hubo un error, pide su **reversión**: la resuelve otra persona y el efectivo regresa a tu turno abierto.

### Corte diario

1. Al terminar el día, en **Mi caja** elige **Cerrar turno**.
2. Cuenta el efectivo por billete y moneda; mientras escribes, el recuadro **Contado** suma lo que capturaste (solo lo tuyo, nunca lo esperado). Guarda el conteo. No verás lo esperado hasta que el turno quede cerrado, y el conteo guardado ya no se puede cambiar.
3. Si coincide con lo que debe haber, el turno se cierra. Si no coincide, el sistema solo dice que **no coincide** (sin decir cuánto ni si sobra o falta) y te deja **recontar una sola vez** o cerrar con el primer conteo; en los dos casos escribe una nota.
4. Al cerrar ves lo esperado, lo contado y la diferencia, en total y, si se capturan piezas, por denominación. Se genera tu **corte diario**: recibos, devoluciones, retiros, lo contado y la diferencia. Lo ves en **Cortes**.
5. Cada negocio decide qué días hay corte y a qué hora. Un turno abierto en un día con corte debe cerrarse antes de la hora de ese día; si se abrió en un día sin corte, antes de la hora del siguiente día que sí tenga. Si cierras después, el corte queda marcado como **tardío**; no pasa nada más.
6. Entrega el efectivo a Supervisión desde **Mi caja** → **Entregar efectivo**; quien lo recibe lo confirma en su sesión.

### Vender artículos

Solo si el negocio lleva inventario (menú **Inventario**). Ver también la [guía de inventario](GUIA-INVENTARIO.md).

1. **Inventario** → **Vender** (o **Vender artículos** desde su ficha) y elige al titular. Verás todos los artículos activos; filtra escribiendo parte del nombre o la clave y usa **+** y **−** en cada uno (o escribe la cantidad). El precio lo pone cada artículo; el **Resumen** de la derecha suma lo elegido, y el sistema lo vuelve a calcular al continuar.
2. Elige cómo se paga: **Lo paga ahora** pasa al cobro (**Continuar al cobro**), que se aplica primero a esos artículos y lo que sobre al adeudo normal; **Se va a su adeudo** deja los cargos pendientes para cobrarlos con lo demás (**Registrar la venta**).
3. **Sin matrícula** (arriba a la derecha) es para quien no es titular: mismo catálogo; se cobra completa en efectivo en ese momento, con tu turno abierto, y emite su recibo.
4. Junto a cada artículo ves cuántas piezas quedan; si no queda ninguna no se muestra número. Cuando quedan pocas (20 % o menos de lo que había tras la última entrada o conteo, o en su mínimo) aparece **pocas**.
5. Si el sistema cree que no hay suficientes piezas, la venta no se detiene: avisa y Supervisión la revisa.

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

- **Configuración**: datos del negocio, vocabulario, parámetros, catálogos, datos de pago, destinos de los cortes, **Caja: cortes y retiros** (días y horas de corte, piezas por denominación y topes de retiros), **Carpeta vigilada del banco** (con el tope de pagos sin respaldo y el tope por pago), **Inventario** (encenderlo, devoluciones, plazos y el porcentaje de existencia baja) e importación inicial del padrón.
- **Equipos**: aprueba las computadoras nuevas y abre **Conectar otra computadora**.

### Marca del negocio

**Más → Configuración → Marca del negocio** (pide tu contraseña otra vez):

1. **Colores**: escribe el color principal y el de acento como `#` y seis dígitos hexadecimales (por ejemplo `#1F1A4E` y `#F58634`) y guarda. El principal pinta los botones y el menú activo; el acento, la franja de arriba, los subrayados y los fondos suaves. Si el principal es demasiado claro para leer texto blanco encima, los botones usan un tono oscuro y la pantalla te lo indica en **Lectura**. **Usar los colores de Ariasmos** quita los del negocio.
2. **Logo**: sube una imagen JPEG o PNG de hasta 1 MB. El programa revisa el contenido real del archivo y lo vuelve a dibujar solo con sus píxeles; cualquier otra cosa se rechaza. **Quitar logo** deja solo el nombre del negocio.
3. El logo y el nombre aparecen en la barra y en el recibo (en pantalla, impreso y en PDF); Ariasmos queda solo en la línea del pie del recibo. Cada cambio queda en la bitácora.
4. Sin colores se usan los de Ariasmos; sin logo, solo el nombre. El asistente de instalación siempre usa los colores de Ariasmos.

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
