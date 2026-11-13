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

1. Abre tu turno en **Mi caja** (el fondo inicial es opcional).
2. Menú **Cobrar** → busca al titular por nombre o matrícula.
3. Escribe el importe recibido. El sistema muestra cómo se reparte entre los cargos pendientes (y los de su familia).
4. Confirma. Se emite el recibo foliado; imprímelo o descárgalo en PDF.

### Corte diario

1. Al terminar el día, en **Mi caja** elige **Cerrar turno**.
2. Cuenta el efectivo por billete y moneda. No verás lo esperado hasta después de contar.
3. Al cerrar se genera tu **corte diario**: los recibos del día, las devoluciones, lo contado y la diferencia. Lo ves en **Cortes**.
4. Si cierras después de la hora límite (18:00 de inicio), el corte queda marcado como **tardío**; no pasa nada más.
5. Entrega el efectivo a Supervisión desde **Mi caja** → **Entregar efectivo**; quien lo recibe lo confirma en su sesión.

## Supervisión

### Aprobaciones

- En el **Inicio** aparece la bandeja de pendientes: altas, bajas, cancelaciones, becas, prórrogas y cambios de familia que pidió Operación.
- Abre cada una, revisa y elige **Aprobar** o **Rechazar** con un motivo.
- Nadie aprueba lo que él mismo pidió ni revierte un cobro que él mismo hizo.

### Banco

1. Menú **Banco** → **Importar**: sube el estado de cuenta en PDF o el archivo de movimientos del banco.
2. Revisa la vista previa: cuántos pagos se aplican solos, cuántos quedan por identificar y cuántos ya estaban.
3. En la **cola** de movimientos por identificar, confirma a quién pertenece cada uno, o márcalo como «no es un cobro».
4. Los depósitos de efectivo de caja se emparejan con los movimientos del banco.

### Efectivo

- **Efectivo** muestra quién tiene dinero en custodia, las entregas por confirmar y los depósitos por conciliar.
- Confirma las entregas que recibes contando el dinero; si no coincide, recházala.

### Corte mayor

1. El día 1 de cada mes el sistema prepara el **corte mayor** del mes anterior como borrador. Aparece en el **Inicio** y en **Cortes**.
2. Revísalo: ingresos por medio y por concepto, estado de cada titular, cartera vencida, caja y banco.
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

- **Configuración**: datos del negocio, vocabulario, parámetros, catálogos, datos de pago, destinos de los cortes e importación inicial del padrón.
- **Equipos**: aprueba las computadoras nuevas y abre **Conectar otra computadora**.

### Respaldos

- **Respaldos** muestra el último respaldo y la última prueba de restauración. Si algo falla, aparece un aviso en el Inicio.
- **Respaldar ahora** y **Probar el último respaldo** se pueden hacer en cualquier momento.
- **Generar clave nueva** cambia la clave de los respaldos futuros. Los respaldos anteriores siguen abriéndose solo con la clave anterior: no la tires.

### Revisión de importaciones

- Cuando alguien importa un archivo de banco que no se puede comprobar contra el estado de cuenta anterior y con él se aplicaron pagos, aparece en tu Inicio como **importación por revisar**.
- Ábrela, compárala con el banco y elige **Marcar como revisada**. Quien la importó no puede marcarla.

### Bitácora

- **Auditoría** muestra cada cambio del sistema: quién, cuándo y qué cambió. **Verificar** comprueba que nadie alteró ni borró eventos.
- En la ficha de cada titular está su historial en lenguaje llano.
