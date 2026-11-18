# Guía de uso de Ariasmos

El sistema se usa con el programa **Ariasmos**, que se abre desde su acceso directo en el escritorio o en el menú Inicio, en la computadora principal o en cualquier computadora adicional (ver la guía de instalación). Cada persona entra con su usuario, su contraseña y, si su rol lo pide, el código de 6 dígitos de su autenticador. Lo que cada quien ve depende de su rol; esta guía sigue los tres roles de las plantillas: **Operación**, **Supervisión** y **Dirección**. Cada negocio puede renombrar sus roles y moverles permisos: donde el programa dice quién puede hacer algo, muestra los nombres de los roles que hoy tienen ese permiso. Los nombres de los menús y de los textos («titulares», «matrícula», «familias», «padrón», «beca» o «descuento», «público en general») salen del vocabulario del negocio; esta guía usa los de fábrica.

## La pantalla

- Al abrir el programa aparece la presentación de Ariasmos con su versión («ver. X.Y.Z») mientras arranca; se desvanece cuando carga la primera pantalla. Si la computadora principal no responde, la ventana lo dice y ofrece **Reintentar**.
- Ariasmos abre una sola ventana por usuario de Windows: si lo abres otra vez, trae al frente la que ya está. Recuerda su tamaño y su posición.
- A la izquierda de la marca están las flechas **Atrás** y **Adelante**. También sirven **Alt + ←**, **Alt + →** y los botones laterales del ratón. Ir atrás, adelante o volver a cargar nunca repite un cobro ni ninguna otra operación: si vuelves a una operación ya hecha, ves su resultado (por ejemplo, el recibo) y el aviso «Esa operación ya se había enviado; no se repitió».
- **Ctrl + rueda del ratón**, **Ctrl + +** y **Ctrl + −** cambian el tamaño de la letra; **Ctrl + 0** lo regresa.
- Las **descargas** (recibos en PDF, cortes, exportaciones) siempre preguntan dónde guardar con la ventana «Guardar como» de Windows; nunca se abren solas. Los recibos se imprimen con el botón **Imprimir** dentro de la ventana.
- Los campos que piden una **carpeta** (destinos de cortes, respaldo, carpeta vigilada del banco) tienen **Examinar…** en la computadora principal, que abre la ventana de Windows para elegirla. En una computadora adicional se escribe la ruta o se elige desde la principal, porque las carpetas son del disco de la principal.
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
- **Todos los roles** ven el aviso **Con atraso** cuando alguien cumple una regla de rezago con aviso o rebasa el límite de adeudo: nombre, matrícula, agrupación, días de atraso y el texto de la regla más grave (por ejemplo «No puede pasar»). Muestra a los 20 más atrasados y enlaza a la lista completa. El adeudo solo lo ve quien tiene el permiso de ver saldos; los demás ven el resto sin importes.

## Operación

### Dar de alta a un titular

1. Menú **Titulares** → **Nueva alta**.
2. Escribe nombre, apellidos, agrupación y el contacto responsable con su teléfono. Si el negocio lo configuró así, los apellidos son opcionales (por ejemplo, para dar de alta empresas) y la constancia de consentimiento de datos no se pide o lleva el texto del negocio.
3. Si paga junto con otros (hermanos, por ejemplo), elige su familia o crea una nueva.
4. Guarda. El alta queda **pendiente** hasta que Supervisión la aprueba; al aprobarse recibe su **matrícula**, que es la referencia para pagar en el banco.
5. Desde la ficha del titular se imprime la **ficha de pago** con los datos bancarios y la matrícula.

### Importar o actualizar desde una hoja

1. En el padrón elige **Importar o actualizar desde una hoja** (si el padrón está vacío es el botón principal). Sube la lista en Excel (.xlsx) o CSV, hasta 5 MB.
2. El programa propone qué es cada columna; corrígelo si hace falta y elige **Ver vista previa**.
3. Los renglones **sin** matrícula se dan de alta. Los renglones **con** matrícula actualizan a ese registro: contacto, agrupación, responsable y nombre. Nunca cambian desde la hoja la matrícula, los saldos, los cargos, los pagos ni el estado; una matrícula que no existe se marca como error y nunca se busca por nombre.
4. Si tu rol solo puede **pedir** la importación, al confirmar la hoja completa se vuelve **una sola solicitud**: nada cambia hasta que otra persona la aprueba (por la bandeja, con una delegación o con su código por teléfono). Quien aprueba ve cuántas altas y cuántos cambios trae, campo por campo.
5. Al aprobarse, cada renglón se vuelve a comparar con los datos del momento: si alguien cambió ese dato mientras tanto, el renglón se salta y aparece en la lista de **Renglones saltados**.
6. La vista previa solo muestra los datos que tu rol puede ver.

### Ordenar las listas

En el padrón, en los buscadores (cobrar, vender y conciliar un movimiento del banco) y en las listas largas (artículos, usuarios, solicitudes y cortes) aparece **Ordenar por** con el sentido ascendente o descendente. El programa recuerda el orden que elegiste en cada lista, solo para ti.

### Cobrar en efectivo

1. Abre tu turno en **Mi caja**: elige tu caja y di si hay efectivo para dar cambio. Con **No, abro en cero** se abre en un solo paso. Con **Sí, cuento lo que hay**: si el negocio captura piezas por denominación, toca cada billete y moneda del fondo (con **−** quitas una; también puedes escribir el número) y el fondo inicial es la suma, que no se escribe aparte; si no, escribe el importe del fondo. Las piezas del fondo cuentan para el cambio que el sistema te propone al cobrar.
2. Menú **Cobrar** → busca al titular por nombre o matrícula. Con **Ordenar por** eliges el orden de los resultados (nombre, apellidos, matrícula, agrupación o familia, ascendente o descendente).
3. A la izquierda ves los cargos pendientes y arriba a la derecha el adeudo. Escribe el importe (solo el número: el signo y la moneda ya vienen puestos). El sistema muestra en **Así se va a aplicar** cómo se reparte entre los cargos pendientes (y los de su familia).
4. Si se capturan piezas: toca cada billete o moneda que te entregan (con **−** quitas una; también puedes escribir el número) y elige **Calcular el cambio**. Mientras tocas, **Recibido** suma lo que capturaste. El recuadro **Entrega exactamente estas piezas** dice qué piezas dar de cambio para que tu caja cuadre en el corte; si entregas otras, ábrelas con **Di el cambio con otras piezas** y corrígelas antes de confirmar. Si no hay combinación exacta, te lo dice y tú escribes lo que entregas.
5. Elige **Confirmar y dar recibo**. Se emite el recibo foliado con su código de verificación y su **QR**; imprímelo o descárgalo en PDF.

### Retirar efectivo para un gasto

1. Con tu turno abierto, en **Mi caja** elige **Retirar efectivo**.
2. Escribe el importe (si se capturan piezas, toca los billetes y monedas que salen), elige el motivo, anota en qué se gastó y adjunta la foto o el PDF del ticket (JPEG, PNG o PDF de hasta 5 MB). Puedes adjuntarlo después desde el retiro.
3. Si el retiro cabe en los topes del negocio, queda registrado de inmediato con su folio. Si pasa de algún tope, queda como **solicitud** y se registra cuando otra persona lo autoriza (por la bandeja, con una delegación o con su código por teléfono).
4. Solo se puede retirar efectivo cobrado en tu turno. Si no alcanza, el sistema lo dice sin decir cuánto hay; después de los intentos que fije el negocio (tres de fábrica), los retiros de ese turno piden autorización.
5. No puedes cerrar el turno con retiros sin comprobante: adjúntalo o declara que no lo hay con su motivo (recibe el aviso quien revisa retiros).
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
3. **Sin matrícula** (arriba a la derecha) es para quien no es titular (el «público en general» del vocabulario): mismo catálogo; se cobra completa en efectivo en ese momento, con tu turno abierto, y emite su recibo.
4. Junto a cada artículo ves cuántas piezas quedan; si no queda ninguna no se muestra número. Cuando quedan pocas (20 % o menos de lo que había tras la última entrada o conteo, o en su mínimo) aparece **pocas**.
5. Si el sistema cree que no hay suficientes piezas, la venta no se detiene: avisa y Supervisión la revisa.

### Devoluciones, entradas, mermas y conteo

- **Devolución**: busca la venta por su número o por el recibo (código o QR). Lo no pagado se cancela; lo pagado regresa como **saldo a favor** al momento o en **efectivo**, que siempre se solicita y autoriza otra persona (sale de tu turno al aprobarse).
- **Entrada o merma**: artículo, cantidad, motivo y, si lo hay, el comprobante (JPEG, PNG o PDF de hasta 5 MB). No pide permiso; Supervisión la revisa después.
- **Conteo mensual**: descarga la lista para contar (no trae existencias), cuenta y sube el Excel o CSV con clave y cantidad, o captúralo en pantalla. Al guardarlo queda fijo, ves las diferencias y otra persona lo aprueba.

### Cargos por cantidad y titulares sin crédito

- **Cargo manual**: elige el concepto y la **cantidad**. Si el concepto se cobra por cantidad (en la plantilla de escuela, «Libros»), la cantidad va de 1 al máximo configurado y el importe es cantidad × la tarifa de la agrupación del titular (o el importe general del concepto si su agrupación no tiene tarifa). El importe lo calcula el programa; cambiar el importe por unidad requiere el permiso de ajustes. Un concepto que no es por cantidad se carga de uno en uno.
- Si el titular tiene una **marca** (por ejemplo «No puede pasar» o «Sin crédito»), la ves en su ficha, en los buscadores (padrón, cobrar, vender) y al cobrar.
- Un titular **sin crédito** (rebasó su límite de adeudo o una regla le quitó el crédito) se cobra igual: recibir pagos, el estado de cuenta y los cargos automáticos no cambian. Lo que cambia es que su **venta al adeudo**, un **cargo manual** nuevo o una **prórroga** quedan como **solicitud** que autoriza otra persona por cualquiera de las tres vías. La venta que se paga en el momento no cambia. Al ponerse al corriente recupera el crédito sin que nadie haga nada.

### Verificar un recibo

- **Verificar recibo** acepta el código del recibo con su folio, o el texto del QR: con un lector de códigos conectado por USB basta con leer el QR del recibo.
- Responde si el recibo es auténtico, si está cancelado o si no se reconoce. Después de varios intentos fallidos en una hora, la verificación se bloquea un rato para esa persona y esa computadora.

## Supervisión

### Aprobaciones

- En el **Inicio** aparece la bandeja de pendientes: altas, bajas, cancelaciones, becas, prórrogas y cambios de familia que pidió Operación.
- Abre cada una, revisa y elige **Aprobar** o **Rechazar** con un motivo.
- Nadie aprueba lo que él mismo pidió ni revierte un cobro que él mismo hizo.

### Banco

1. Menú **Banco** → **Importar**: sube el estado de cuenta en PDF o el archivo de movimientos del banco. El PDF se lee con el lector del banco de la cuenta; hoy hay uno (Santander PyME). Con otro banco el programa lo dice y pide el archivo de movimientos en Excel o CSV, que sirve para cualquier banco: propone las columnas y recuerda la correspondencia. Si hay carpeta vigilada, basta con dejar ahí el archivo descargado; el sistema lo importa solo y lo muestra en el Inicio.
2. Revisa la vista previa: cuántos pagos se aplican solos, cuántos quedan por identificar y cuántos ya estaban.
3. En la **cola** de movimientos por identificar, confirma a quién pertenece cada uno, o márcalo como «no es un cobro».
4. Los depósitos de efectivo de caja se emparejan con los movimientos del banco.
5. Lo que llega por la carpeta vigilada se aplica solo, salvo los movimientos **retenidos**: un estado en PDF que no continúa al anterior, o los movimientos de un Excel o CSV con una señal de sospecha (o todo el archivo si sus saldos no cuadran o rebasaría el tope de pagos sin respaldo). En el Inicio aparece la importación; ábrela, compara cada movimiento retenido con el banco (se ve su motivo), marca los que existen y elige **Liberar los marcados** o **Liberar todos**. Quien libera no puede marcar la importación como revisada.
6. **Pagos sin respaldo en el estado**: al importar el estado en PDF del mes, cada pago aplicado desde un Excel o CSV que no aparezca en él sale en el Inicio con un enlace para **solicitar su reversión**. El sistema no lo revierte solo. También avisa si un pago así lleva más de 45 días sin un estado que lo cubra.

### Topes del banco

**Banco → Topes** (con el permiso «Configurar los topes del banco», que traen Supervisión y Dirección; pide tu contraseña otra vez) fija cuánto puede aplicarse **solo** desde los Excel o CSV que llegan por la carpeta vigilada:

- **Tope del día**, uno por cada día de la semana: lo máximo que se aplica solo ese día. Se cuenta pago por pago, en el orden del archivo, sobre el día en que se aplica (no la fecha del movimiento). El pago que no cabe queda **retenido** con el motivo «Tope del día» y se sigue con el siguiente, que sí puede caber. Un día en 0 retiene todo lo de ese día.
- **Tope acumulado**: lo máximo aplicado desde Excel o CSV que todavía no confirma un estado de cuenta en PDF. Si un archivo lo rebasaría, se retiene completo. Baja cuando llega el estado del mes.
- Lo que tú liberas a mano no gasta el tope del día (sí cuenta en el acumulado) y liberar nunca se bloquea por un tope.
- La pantalla muestra cuánto se ha aplicado hoy contra el tope del día y cuánto hay acumulado contra el tope acumulado. Al instalar todo está en 0: aplicar solo es una decisión del negocio.
- Cada cambio queda en la bitácora con los valores de antes y de después, y Dirección lo ve en su Inicio durante 7 días.

### Tarifas por agrupación y conceptos por cantidad

**Conceptos → Tarifas por agrupación** (permiso «Administrar conceptos de cobro»):

- Cada concepto puede tener una **tarifa por agrupación**: importe y, si es recurrente, periodicidad y día de vencimiento propios, activa o no. Sin tarifa para la agrupación del titular vale lo general del concepto.
- **Por cantidad** (solo conceptos por evento): al cargarlo se pide cuántos, de 1 al máximo que fijes.
- **Solo con tarifa**: a quien no tenga tarifa activa para su agrupación no se le cobra ese concepto (sirve para cargos especiales de ciertas agrupaciones).
- Los cargos automáticos toman la tarifa que corresponde al momento de generarse. Cambiar a alguien de agrupación aplica desde el siguiente periodo; los cargos ya generados no cambian. Si la nueva tarifa tiene otra periodicidad, el primer periodo nuevo empieza después de que termina el último cobrado, sin cobrar dos veces los mismos días.
- Cada cambio queda en la bitácora con antes y después.

### Recargos tras el alta

**Reglas de recargo → Recargos tras el alta** (permiso «Administrar conceptos de cobro»): de fábrica, a quien se acaba de dar de alta **no se le cobran recargos** de lo que vence dentro del periodo de su alta (según la periodicidad de cada concepto; los que no se repiten cuentan por mes). Desde el periodo siguiente, todo normal. Puedes cambiarlo a «Desde el alta». Reactivar una baja cuenta como alta nueva y vale la fecha de activación. El saldo inicial de una migración sí genera recargo.

### Límites de adeudo

**Más → Límites de adeudo** (permiso «Configurar los límites de adeudo», que traen Supervisión y Dirección; pide tu contraseña otra vez):

- Dos límites independientes: **importe máximo** de adeudo vencido y **días máximos** de atraso (desde el vencimiento más antiguo con saldo; una prórroga mueve ese vencimiento). Cada uno es **Ilimitado** (de fábrica) o **Hasta un valor**.
- **Excepciones por titular**: desde su ficha, «Excepción al límite», con su propio «Como el negocio», «Ilimitado» o valor para cada límite, motivo y vigencia opcional. Solo las ve quien configura los límites o quien ve la ficha.
- Quien rebasa cualquiera de los dos aparece en el aviso **Con atraso** del Inicio y queda **sin crédito**. Nunca se bloquea recibir un pago ni consultar el estado de cuenta.
- Cada cambio queda en la bitácora con antes y después, y Dirección lo ve en su Inicio durante 7 días.

### Reglas de rezago

**Más → Reglas de rezago** (permiso «Configurar las reglas de rezago»):

- Cada regla tiene **nombre**, **texto** (hasta 60 caracteres, por ejemplo «No puede pasar»), **a quién aplica** (todos, una agrupación o un titular por su matrícula), **cuándo** (a partir de N días de atraso, de un importe vencido o al rebasar el límite; basta una) y **acciones**: aviso en el Inicio de todos, marca en la ficha, buscadores y cobro, sin crédito y lista de cobranza.
- Puedes crear todas las reglas propias que quieras. Si varias aplican, valen todas sus acciones; el aviso muestra el texto de la más grave (más días).
- Una regla para una agrupación o para un titular manda sobre la general en la misma acción: sirve para ser más estricto o más tolerante con alguien. Las reglas para un titular solo las ve quien configura las reglas o quien ve la ficha.
- Las plantillas traen reglas de arranque con su contexto (escuela: «Pago atrasado» a los 10 días y «No puede pasar» a los 30; gimnasio: «Acceso suspendido»; etcétera), sin importes y editables. Solo llegan en una instalación nueva.
- **Con atraso** (enlace del aviso del Inicio) es la lista completa; se ordena por días, nombre, matrícula o agrupación, y quien ve saldos también por adeudo y la exporta a CSV.

### Efectivo

- **Efectivo** muestra quién tiene dinero en custodia, las entregas por confirmar y los depósitos por conciliar. Si tú mismo tienes un turno abierto, tu efectivo no se muestra hasta que lo cierres.
- Confirma las entregas que recibes contando el dinero; si no coincide, recházala.

### Retiros de caja

- **Efectivo** → **Retiros de caja** lista todos los retiros con su comprobante. Cada uno nace «por revisar»: ábrelo, revisa el comprobante y márcalo **Revisado** u **Observado** con una nota. Nadie revisa un retiro propio.
- En el **Inicio** aparecen avisos cuando una caja llega al porcentaje de aviso de un tope del periodo (80 % de fábrica), cuando un retiro se declara sin comprobante y cuando hay retiros sin revisar desde hace varios días.
- **Motivos de retiro** permite agregar o desactivar motivos.

### Inventario

- **Inventario** → **Revisión**: entradas, mermas, devoluciones a saldo a favor y ventas sin existencia por revisar; márcalas **Revisado** u **Observado**. Nadie revisa lo propio.
- Los conteos y las devoluciones en efectivo llegan a la bandeja de **Solicitudes**. Al aprobar un conteo se ajusta cada artículo con la diferencia del momento del conteo.
- **Artículos**: alta, precio, mínimo y concepto de cobro; un artículo no se borra, se desactiva. El Inicio avisa de los artículos en o bajo su mínimo.

### Corte mayor

1. El día 1 de cada mes el sistema prepara el **corte mayor** del mes anterior como borrador. Aparece en el **Inicio** y en **Cortes**.
2. Revísalo: ingresos por medio y por concepto, estado de cada titular, cartera vencida por tramos de antigüedad (de fábrica 1 a 30, 31 a 60, 61 a 90 y más de 90 días; se cambian en Parámetros), caja, banco y, si se lleva, el resumen de inventario. Cada corte lleva el nombre que le dio el negocio, también en sus archivos.
3. Elige **Cerrar el corte** (pide tu contraseña). El mes queda bloqueado: nada puede registrarse con fecha dentro de él.
4. Si nadie lo cierra en 5 días, el sistema lo cierra solo marcado como «sin revisar».

### Lista de cobranza

- Cada lunes se genera la lista de adeudos vencidos; en **Cortes** puedes generarla en cualquier momento.
- Si hay reglas de rezago con la acción de cobranza, la lista trae además la sección «Con atraso según las reglas del negocio», de los más atrasados a los menos, con el texto de la regla.

## Todas las personas: versión nueva

- Cuando hay una versión nueva, el Inicio de todos muestra **«Hay una versión nueva: X.Y.Z»** con la lista de cambios.
- **Descargar** la pide al servicio; cualquiera puede pedirla. Se baja una a la vez y como máximo tres intentos por hora. El servicio comprueba que el instalador sea exactamente el del aviso firmado; si no, lo borra y avisa a Dirección.
- Cuando termina, el aviso cambia a **«Lista para instalar»**. La instalación se hace a mano en la computadora del servidor: menú Inicio → Ariasmos → **Instalar actualización** (pide permiso de administrador). Vuelve a comprobar la firma y la huella antes de abrir el instalador y se niega si no coinciden. Antes, haz un respaldo y cierra los turnos de caja abiertos: el aviso dice si hay alguno.
- Si el aviso dice que antes hay que instalar otra versión, pide ese instalador al dueño del programa.
- Sin internet no pasa nada: el aviso simplemente no aparece.

## Dirección

### Usuarios y roles

- **Usuarios** → **Nuevo usuario**: el sistema muestra un **código de activación** que la persona usa para elegir su contraseña (nadie teclea la contraseña de otro).
- **Restablecer acceso** genera un código nuevo si alguien olvidó su contraseña o perdió su teléfono.
- **Roles** permite mover permisos entre roles y renombrarlos. Dos permisos tocan la hoja del padrón: **Importar o actualizar desde una hoja, sin aprobación** (Dirección en las plantillas) y **Pedir que se importe o actualice desde una hoja** (Operación y Supervisión en las plantillas).

### Datos de pago

- La cuenta de depósito puede ser una **CLABE** (18 dígitos con su dígito verificador; el banco se reconoce por los tres primeros) u **otra cuenta**, para negocios o países sin CLABE: número de cuenta y banco escritos.
- Los medios de pago iniciales vienen de la plantilla; se cambian en **Medios de pago**.

### Conceptos con cobro semanal o quincenal

- **Semanal**: un cargo por semana (lunes a domingo), con periodo `AAAA-Sww`. El día de vencimiento del concepto es el día de la semana (1 lunes a 7 domingo).
- **Quincenal**: dos cargos por mes, del 1 al 15 (`AAAA-MM-1`) y del 16 al fin de mes (`AAAA-MM-2`). La primera vence el día del concepto (1 a 15) y la segunda quince días después.
- Becas o descuentos, prórrogas, recargos y cierre de periodo funcionan igual que en los mensuales. Un alta a mitad de periodo genera el cargo del periodo en que se dio de alta. Los recargos que se repiten lo hacen cada mes, también en estos conceptos.

### Configuración

- **Configuración** (cada pantalla dice para qué sirve; lo poco usado está plegado bajo **Más opciones**): datos del negocio (la zona horaria se elige de una lista con buscador: escribe una ciudad), vocabulario (incluye cómo se llama el padrón, el descuento autorizado y la venta sin registro), **Reglas del negocio** (prefijo y dígitos del teléfono, tamaño de hoja de los PDF —Carta o A4—, apellidos obligatorios o no y la constancia de consentimiento con su texto), parámetros (entre otros: tramos de la cartera vencida, cuántos respaldos diarios y mensuales se conservan, horas sin respaldo antes de avisar, días entre pruebas de restauración, intentos de retiro rechazados antes de pedir autorización y porcentaje de aviso del tope de retiros), catálogos, datos de pago, destinos de los cortes, **Caja: cortes y retiros** (días y horas de corte, piezas por denominación y topes de retiros), **Carpeta vigilada del banco** (con el tope por pago), **Actualizaciones del programa** (ver abajo), **Inventario** (encenderlo, devoluciones, plazos y el porcentaje de existencia baja) e importación inicial del padrón.
- **Equipos**: aprueba las computadoras nuevas y abre **Conectar otra computadora**.

### Marca del negocio

**Más → Configuración → Marca del negocio** (pide tu contraseña otra vez):

1. **Colores tomados del logo**: al subir el logo, el programa propone el color principal y el de acento a partir de él y los muestra en una **vista previa**; elige **Usar estos colores** o escribe otros. **Usar los colores del logo** vuelve a proponerlos cuando quieras. El mismo logo da siempre los mismos colores, y ya vienen ajustados para leerse bien.
2. **Colores**: escribe el color principal y el de acento como `#` y seis dígitos hexadecimales (por ejemplo `#1F1A4E` y `#F58634`) y guarda. El principal pinta los botones y el menú activo; el acento, la franja de arriba, los subrayados y los fondos suaves. Si el principal es demasiado claro para leer texto blanco encima, los botones usan un tono oscuro y la pantalla te lo indica en **Lectura**. **Usar los colores de Ariasmos** quita los del negocio.
3. **Logo**: sube una imagen JPEG o PNG de hasta 1 MB. El programa revisa el contenido real del archivo y lo vuelve a dibujar solo con sus píxeles; cualquier otra cosa se rechaza. **Quitar logo** deja solo el nombre del negocio.
4. El logo y el nombre aparecen en la barra y en el recibo (en pantalla, impreso y en PDF); Ariasmos queda solo en la línea del pie del recibo. Cada cambio queda en la bitácora.
5. Sin colores se usan los de Ariasmos; sin logo, solo el nombre. El asistente de instalación siempre usa los colores de Ariasmos; su paso de marca muestra la vista previa con los colores del negocio.

### Respaldos

- **Respaldos** muestra el último respaldo y la última prueba de restauración. Si algo falla, aparece un aviso en el Inicio.
- **Respaldar ahora** y **Probar el último respaldo** se pueden hacer en cualquier momento.
- **Generar clave nueva** cambia la clave de los respaldos futuros. Los respaldos anteriores siguen abriéndose solo con la clave anterior: no la tires.

### Revisión de importaciones

- Cuando alguien importa un archivo de banco que no se puede comprobar contra el estado de cuenta anterior y con él se aplicaron pagos, aparece en tu Inicio como **importación por revisar**.
- Ábrela, compárala con el banco y elige **Marcar como revisada**. Quien la importó, o quien liberó alguno de sus movimientos si llegó por la carpeta vigilada, no puede marcarla.
- Si el negocio lleva inventario, el Inicio te avisa cuando un conteo lleva más días de los configurados sin aprobarse.

### Cambios en los topes del banco

Quien tiene «Ver auditoría» ve en su Inicio los cambios de topes del banco de los últimos 7 días que hizo **otra** persona: quién, cuándo y de cuánto a cuánto. Quien concilia también libera pagos, así que conviene revisar que los topes sean los acordados.

### Cambios en los límites de adeudo

Quien tiene «Ver auditoría» ve en su Inicio los cambios del límite de adeudo del negocio y de las excepciones por titular de los últimos 7 días hechos por **otra** persona, con quién, cuándo y de cuánto a cuánto.

### Actualizaciones del programa

- **Configuración → Actualizaciones del programa** (pide tu contraseña otra vez): actívalas, escribe el repositorio del canal (`propietario/nombre`) y la clave de solo lectura que te dio el dueño del programa. La clave se guarda cifrada y no se vuelve a mostrar; para cambiarla escribe otra. Si la pantalla dice que esta copia no trae llaves de actualización, no se pueden activar: se actualiza a mano con un instalador nuevo.
- El servicio busca una versión nueva al arrancar y una vez al día. **Buscar ahora** pide una búsqueda en el siguiente ciclo del servicio (como máximo una cada 10 minutos).
- Tu Inicio te avisa cuando se descargó una versión, cuando una descarga no coincidió con el aviso firmado (se borra sola) y cuando cambió la llave de uso de las actualizaciones. Si no esperabas un cambio de llave, apaga las actualizaciones y avisa al dueño del programa.

### Bitácora

- **Auditoría** muestra cada cambio del sistema: quién, cuándo y qué cambió. **Verificar** comprueba que nadie alteró ni borró eventos.
- En la ficha de cada titular está su historial en lenguaje llano.
