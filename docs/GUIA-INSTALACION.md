# Guía de instalación de Ariasmos

Esta guía es para la persona que instala Ariasmos. No hace falta saber programar.

Ariasmos es un programa de Windows con su propia ventana. Se instala con el mismo instalador en cada computadora, de una de dos formas:

- **Computadora principal**: guarda los datos del negocio y da servicio a las demás. Si el negocio usa una sola computadora, es esta.
- **Computadora adicional**: solo instala el programa y se conecta a la principal con un **archivo de conexión**.

## Lo que necesitas

- Una computadora con **Windows 10 u 11 de 64 bits** que se quede encendida mientras se use el sistema. Será la **computadora principal**.
- Una cuenta de **administrador** de cada computadora donde se instale.
- Que las computadoras adicionales estén en la **misma red** que la principal (el mismo módem o la misma red Wi‑Fi).
- Una impresora o una hoja y pluma, para guardar la **clave de recuperación**.

## 1. Descargar y comprobar el instalador

1. Descarga el archivo `Ariasmos-X.Y.Z-instalador.exe` y el archivo `SHA256SUMS.txt` que lo acompaña.
2. Comprueba que el instalador no se dañó ni fue cambiado. Abre **PowerShell** (menú Inicio → escribe «PowerShell») y escribe, cambiando la ruta por la de tu carpeta de descargas:

   ```
   Get-FileHash "$env:USERPROFILE\Downloads\Ariasmos-0.9.0-instalador.exe" -Algorithm SHA256
   ```

3. El texto largo que aparece en la columna **Hash** debe ser **igual** al que viene en `SHA256SUMS.txt` (no importan mayúsculas o minúsculas). Si no es igual, **no instales**: vuelve a descargarlo.

## 2. Instalar la computadora principal

1. Haz doble clic en el instalador.
2. Windows puede mostrar **«Windows protegió su PC»**. Aparece porque el instalador y el programa **no llevan firma de código** (un certificado comercial que el negocio todavía no compra); no significa que tengan un virus si comprobaste el hash en el paso anterior. Haz clic en **Más información** y luego en **Ejecutar de todas formas**. En equipos con **Control inteligente de aplicaciones** (Smart App Control) activo, Windows puede bloquearlo; en ese caso hay que desactivarlo o esperar a que el programa lleve firma.
3. Acepta que el programa haga cambios en el equipo (te pedirá la contraseña de administrador si no la tienes abierta).
4. Lee y acepta la licencia.
5. En **Tipo de computadora** elige **Computadora principal**.
6. En **Puerto** deja el que se propone. Es el puerto por el que las computadoras adicionales se conectan a esta: se propone 443 y, si otro programa ya lo usa, otro libre (por ejemplo 8443). Si eliges uno ocupado, el instalador lo dice.
7. Si este equipo **reemplaza a otro** donde ya usabas el sistema, marca «Restaurar desde un respaldo» y sigue la guía [RESTAURAR.md](RESTAURAR.md). Si es una instalación nueva, déjala sin marcar.
8. Haz clic en **Instalar** y espera. Tarda unos minutos: prepara la base de datos, los tres servicios del sistema, el certificado del servidor, el archivo de conexión de esta computadora y la regla del cortafuegos. Si a Windows le falta el componente **WebView2** de Microsoft (algunos Windows 10 antiguos), el instalador lo instala con el instalador oficial de Microsoft; para eso esa computadora necesita internet.
9. Al terminar, el instalador muestra el **token del asistente**. Haz clic en **Copiar**. Ese token se pide una sola vez y no se guarda en ningún lado.
10. Deja marcada la casilla «Abrir Ariasmos» y haz clic en **Finalizar**.

El instalador deja un acceso directo **Ariasmos** en el escritorio y en el menú Inicio, con el medallón negro del jinete. Abre la ventana del programa: primero aparece la presentación de Ariasmos con su versión mientras arranca y después la primera pantalla. El asistente de los diez pasos muestra a la izquierda la lista de pasos y en cuál vas.

Si perdiste el token antes de terminar el asistente: menú Inicio → **Ariasmos** → **Generar token nuevo del asistente**. Pide permiso de administrador y muestra un token nuevo; el anterior deja de servir.

### Instalación sin preguntas

Para instalar sin ventanas (por ejemplo, desde una herramienta de administración):

```
Ariasmos-X.Y.Z-instalador.exe /VERYSILENT /MODO=principal /PUERTO=443
Ariasmos-X.Y.Z-instalador.exe /VERYSILENT /MODO=adicional /CONEXION="D:\ariasmos-conexion.json"
```

Sin `/PUERTO` se usa el que ya tenía la computadora o el propuesto. Una computadora que ya tiene los datos del negocio siempre se actualiza como principal.

## 3. Asistente de primer uso

La primera vez que abres Ariasmos en la computadora principal aparece el asistente. Tiene diez pasos y un paso final opcional. Cada paso dice para qué sirve, trae los valores de fábrica puestos y pliega lo avanzado bajo **Más opciones**. Desde el paso 3, **Atrás** regresa al paso anterior sin perder lo que ya escribiste en el actual, y los pasos ya hechos de la lista de la izquierda se pueden abrir para revisarlos. Los pasos marcados como opcionales se pueden omitir y completar después desde *Configuración*; los valores de fábrica sirven para empezar a trabajar el mismo día.

1. **Datos del negocio**: pega el token, escribe el nombre, elige la zona horaria de la lista (escribe una ciudad en el buscador para encontrarla; cada zona muestra su diferencia con la hora universal y el asistente propone la de esta computadora), la moneda y la plantilla (viene marcada la genérica), y marca si el negocio lleva **inventario** de artículos (se puede cambiar después en *Configuración → Inventario*). Plantillas incluidas: **genérica** (sirve tal cual a la mayoría), **escuela**, **gimnasio o club**, **academia o talleres**, **rentas** y **servicios con cuota**; cada una trae su vocabulario, conceptos y periodicidades (mensual, quincenal o semanal), sin importes. También puedes importar un archivo de plantilla. La plantilla trae además los conceptos que se cobran por cantidad (en escuela, «Libros») y las **reglas de rezago** de arranque con su contexto (por ejemplo, en escuela, «Pago atrasado» a los 10 días y «No puede pasar» a los 30), todas editables después; las reglas solo llegan en una instalación nueva. Los límites de adeudo empiezan en «Ilimitado».
2. **Vocabulario y conceptos**: cómo se llaman las personas a las que se cobra, su número, la lista de todos ellos, el descuento autorizado y la venta sin registro, y qué conceptos se cobran. Se puede dejar como viene.
3. **Importes** de cada concepto y, si aplica, el recargo por pago tardío: elige **Importe fijo** o **Porcentaje** y el campo muestra el signo que corresponde ($ o %). En los conceptos semanales el día de vencimiento es el día de la semana (1 lunes a 7 domingo); en los quincenales, el día de la primera quincena (1 a 15).
4. **Marca** (opcional): sube el logo y el programa te propone los dos colores tomados de él, con una vista previa. Acéptalos, escribe otros u omite el paso.
5. **Datos de pago** (opcional): la cuenta del negocio que aparece en las fichas de pago: CLABE de 18 dígitos u **otra cuenta** (número y banco escritos) si no tienes CLABE.
6. **Caja: cortes y retiros**: qué días de la semana hay corte de caja y la hora límite de cada uno (propone lunes a sábado a las 18:00; deja vacío el día que no tenga corte), si se capturan las piezas de cada billete y moneda (se muestran los mismos mosaicos que verás al abrir el turno, cobrar y cerrar), y los topes de los retiros de caja (importe máximo por retiro, importe y número máximo de retiros por día o por semana y efectivo máximo en caja). Lo que pase de un tope necesita la autorización de otra persona. Si elegiste una moneda distinta a la de la plantilla, aquí escribes sus billetes y monedas.
7. **Reglas del negocio** (opcional): prefijo de país y dígitos del teléfono, tamaño de hoja de los PDF (Carta o A4), si se piden apellidos y si se pide la constancia de consentimiento de datos con su texto.
8. **Entrega y respaldo**: la carpeta donde se dejan los cortes, la carpeta del respaldo diario y, si quieres, la **carpeta vigilada del banco** con el tope por pago y los topes del banco (ver abajo). Si esta copia del programa trae llaves de actualización, también puedes activar aquí las **actualizaciones del programa** (sección 7). Aquí aparece la **clave de recuperación** (ver abajo).
9. **Primer usuario**: tu usuario y contraseña; recibe el rol principal de la plantilla.
10. **Autenticador**: instala en tu teléfono una aplicación gratuita como Google Authenticator, Microsoft Authenticator, Authy o 2FAS, escanea el código QR y escribe el código de 6 dígitos.

**Paso final (opcional): tus clientes.** Al terminar, el programa ofrece importar tu lista de clientes desde Excel o CSV (propone las columnas y no guarda nada hasta que confirmas) o darlos de alta uno por uno, y lista lo que omitiste en la instalación con un botón para completarlo.

### Carpeta vigilada del banco

Es una carpeta donde alguien deja el archivo descargado de la banca en línea (estado de cuenta en PDF o archivo de movimientos en Excel o CSV). Cada pocos minutos el sistema la revisa e importa lo nuevo con las mismas revisiones que una importación manual.

- Solo toma archivos `.pdf`, `.xlsx` y `.csv` que ya terminaron de copiarse; un archivo que ya se importó no se vuelve a importar.
- Lo importado pasa a la subcarpeta `procesados`; lo rechazado, a `rechazados`, junto con un archivo `.motivo.txt` que dice por qué.
- Un Excel o CSV solo se reconoce si antes se importó a mano uno con las mismas columnas.
- Un **estado de cuenta en PDF que continúa al anterior** aplica sus pagos de inmediato. Si no continúa (por ejemplo, el primero), sus pagos **no se aplican** hasta que alguien con permiso de conciliar los revise contra el banco y los libere.
- Un **Excel o CSV** aplica sus pagos de inmediato, salvo los movimientos con alguna señal de sospecha, que quedan **retenidos uno por uno** con su motivo: importe mayor que lo que debe la familia, mayor que el **tope por pago**, fecha futura o ya cubierta por un estado en PDF que no lo trae, titular que no está activo o segundo pago de la misma matrícula en el archivo. Todo el archivo queda retenido si sus saldos no cuadran, si no continúan el último saldo conocido, o si con él se rebasaría el **tope acumulado** (la suma de lo aplicado desde Excel o CSV que todavía no confirma un estado en PDF). Además, cada pago se aplica solo mientras quepa en el **tope del día** (uno por día de la semana); el que no cabe queda retenido y se sigue con el siguiente.
- El tope por pago se pide en este paso y en *Configuración → Carpeta vigilada del banco*. Los topes del día y el acumulado se piden en este paso y después viven en **Banco → Topes** (Supervisión y Dirección, con contraseña). Todos empiezan en **0**: con un tope en 0 todo Excel o CSV queda retenido. Aplicar de inmediato es una decisión del negocio al subir los topes. Al actualizar desde una versión anterior los topes del día quedan en 0, así que hay que fijarlos en **Banco → Topes** para que se siga aplicando solo.
- Cuando llega el estado en PDF del mes, cada pago que se aplicó desde un Excel o CSV y no aparece en él queda marcado **«sin respaldo en el estado»** y se avisa a Supervisión y Dirección. No se revierte solo.
- La carpeta no puede estar dentro de la carpeta del programa ni de la de datos. Si es una carpeta de tu usuario, dale permiso como se explica en la sección 6.

En los pasos que piden una carpeta, el botón **Examinar…** abre la ventana de Windows para elegirla y llena el campo. También puedes escribir la ruta.

## 4. La clave de recuperación

En el paso de entrega y respaldo aparece una clave larga en grupos de 4 letras y números. **Es la única forma de abrir los respaldos.** Sin ella, si el equipo se descompone o se pierde, la información no se puede recuperar.

- Imprímela o cópiala a mano, completa.
- Guárdala **fuera de este equipo**, en un lugar seguro (no en la misma carpeta de los respaldos ni en una foto en el mismo equipo).
- Marca la casilla «Ya la guardé». Después de eso el sistema no la vuelve a mostrar.

Si te saltaste ese paso, Dirección verá un aviso en el inicio hasta que la guarde (menú **Respaldos** → **Clave de recuperación**).

## 5. Instalar las computadoras adicionales

Cada computadora adicional instala el programa Ariasmos con el mismo instalador y se conecta a la principal con un **archivo de conexión**. No instala Python, servicios ni reglas del cortafuegos, y no guarda datos del negocio.

El archivo de conexión lleva tres cosas: la **dirección** de la computadora principal (su nombre o su IP), el **puerto** y la **huella SHA-256** de su certificado. La huella es la que permite que el programa compruebe que habla con tu computadora principal y no con otra: Ariasmos se niega a conectarse si el certificado no coincide. No contiene contraseñas ni datos del negocio, pero quien lo cambiara podría apuntar una computadora a otro servidor: **pásalo con una memoria USB o en persona, nunca por correo ni por un chat**.

1. En la computadora principal, entra con un usuario de Supervisión o Dirección y abre **Equipos** → **Conectar otra computadora**.
2. Elige la dirección (de preferencia el nombre del equipo; una IP solo sirve mientras no cambie) y haz clic en **Descargar el archivo de conexión**. Elige dónde guardarlo, por ejemplo la memoria USB. Queda registrado en la bitácora.
3. En la otra computadora, ejecuta el instalador (pasos 1 a 4 de la sección 2), elige **Computadora adicional** y, cuando lo pida, elige el archivo de conexión con **Examinar**. El instalador lo revisa y lo guarda en `C:\ProgramData\Ariasmos\conexion.json`, que solo un administrador puede cambiar.
4. Abre **Ariasmos** desde el escritorio. La primera vez esa computadora queda **pendiente**: apruébala en la computadora principal en **Equipos**.

Ninguna computadora instala el certificado del servidor en Windows: el programa Ariasmos reconoce a la computadora principal por la huella del archivo de conexión, y es la única forma soportada de usar el sistema.

El certificado de la computadora principal vence en **10 años**. Cuando falten 60 días o menos, quienes aprueban equipos verán un aviso en el inicio. Basta con volver a ejecutar el instalador en la computadora principal (sección 7): genera un certificado nuevo y después hay que llevar un archivo de conexión nuevo a cada computadora adicional y volver a ejecutar ahí el instalador. Lo mismo si cambia el nombre de la computadora principal.

Si el programa de una computadora adicional es más viejo que el de la principal, Ariasmos lo avisa en esa computadora: instálale la versión nueva con el mismo instalador.

## 6. Dar permiso a una carpeta

El sistema corre con una cuenta de Windows limitada que, por seguridad, no puede escribir en las carpetas personales de los usuarios. Si quieres que los cortes, los respaldos o la carpeta vigilada del banco estén, por ejemplo, en una carpeta de OneDrive de tu usuario:

1. En la computadora principal, en la pantalla de **Destinos de cortes**, de **Respaldos** o de **Carpeta vigilada del banco**, elige la carpeta con **Examinar…** y guarda.
2. Si la pantalla dice que el servicio no tiene permiso para escribir en la carpeta, aparece el botón **Dar permiso**. Ariasmos muestra qué carpeta es y pide confirmación; después Windows pide la confirmación de un administrador. El permiso se da sobre esa carpeta únicamente.
3. Guarda la carpeta otra vez.

Las carpetas son siempre del disco de la computadora principal, así que **Examinar…** y **Dar permiso** solo aparecen ahí. También puedes usar menú Inicio → **Ariasmos** → **Dar permiso a una carpeta** y escribir la ruta. La herramienta no acepta carpetas de red, enlaces, unidades completas ni carpetas del sistema o del programa.

## 7. Actualizar

### Con el aviso del programa

Si Dirección activó las **actualizaciones del programa** (*Configuración → Actualizaciones del programa*, con el repositorio del canal y la clave de solo lectura que da el dueño), el servicio busca versiones nuevas y las avisa en el Inicio. Solo acepta versiones firmadas con la llave del dueño.

1. Alguien elige **Descargar** en el aviso. El servicio baja el instalador a `C:\ProgramData\Ariasmos\instancia\actualizaciones\` (no se sirve por la red) y comprueba su tamaño y su huella contra el aviso firmado.
2. Cuando el aviso dice **«Lista para instalar»**, haz un respaldo (menú **Respaldos**) y pide que se cierren los turnos de caja.
3. En el servidor: menú Inicio → **Ariasmos** → **Instalar actualización**. Acepta el permiso de administrador. La herramienta vuelve a comprobar la firma y la huella, copia el instalador a una carpeta propia, te pide escribir `SI` y abre el instalador. Si algo no coincide, no ejecuta nada.
4. Sigue los pasos del instalador como en la actualización a mano (abajo, desde el paso 2).

Si esta copia del programa no trae llaves de actualización, la opción no se puede activar y se actualiza a mano.

### A mano

1. Descarga el instalador nuevo y comprueba su hash (paso 1).
2. Ejecútalo en el servidor. Detecta la instalación existente, detiene el sistema, guarda una copia de la carpeta de datos en `C:\ProgramData\Ariasmos\antes-de-actualizar\` y, si hay carpeta de respaldo configurada, hace un respaldo cifrado.
3. Reemplaza el programa, actualiza la base de datos y vuelve a arrancar. No se muestra token: tus usuarios y datos siguen igual.
4. El certificado del servidor y el puerto se conservan, así que las computadoras adicionales siguen funcionando sin hacer nada. Solo se genera un certificado nuevo si cambió el nombre del equipo o faltan menos de 60 días para que venza; en ese caso el registro de la instalación lo indica y hay que llevar un archivo de conexión nuevo a cada computadora adicional (sección 5).
5. Las computadoras adicionales se actualizan a mano con el mismo instalador nuevo; el aviso del programa les indica cuándo. Conservan su archivo de conexión si no eliges otro.

### Al actualizar a la versión con tarifas, límites de adeudo y rezagados

La base de datos se actualiza sola y todo sigue funcionando igual, con un cambio a propósito:

- **Recargos tras el alta**: el valor de fábrica nuevo es «hasta el siguiente periodo», así que a quien se dé de alta (o se reactive) **no** se le generan recargos de lo que vence en el periodo de su alta. Si tu negocio quiere el comportamiento anterior, elige «Desde el alta» en *Conceptos → Reglas de recargo → Recargos tras el alta*.
- No hay tarifas por agrupación: se sigue cobrando el importe general de cada concepto. Los conceptos por evento siguen aceptando cualquier cantidad de 1 a 1000 hasta que se configuren en *Tarifas*.
- Los dos límites de adeudo quedan en «Ilimitado» y no hay reglas de rezago: nadie aparece como rezagado ni pierde el crédito hasta que el negocio las cree.
- Los permisos nuevos «Configurar los límites de adeudo» y «Configurar las reglas de rezago» se dan a los roles que ya administraban conceptos o configuración, y se crean las políticas de las solicitudes de cargo y venta sin crédito.

## 8. Desinstalar

Panel de control → Programas → **Ariasmos** → Desinstalar (o menú Inicio → Ariasmos → Desinstalar Ariasmos).

- En la computadora principal se detienen y quitan los servicios y la regla del cortafuegos. Si una versión anterior había instalado el certificado del servidor en Windows, también se quita.
- En una computadora adicional se quitan el programa y su archivo de conexión.
- El instalador pregunta si quieres **borrar también los datos**. La respuesta recomendada es **No**: los datos se conservan en `C:\ProgramData\Ariasmos` y una instalación nueva los vuelve a usar.
- Si eliges **Sí**, se borran la base, las claves y los registros. No se puede deshacer.

## Si algo falla

- El registro de la instalación está en `C:\ProgramData\Ariasmos\registros\instalacion.log`.
- Los registros de los tres servicios (`AriasmosWeb`, `AriasmosTrabajador`, `AriasmosTLS`) están en la misma carpeta.
- Si el puerto elegido está ocupado por otro programa, el instalador lo dice: elige otro.
- Si Ariasmos dice que no puede conectarse con el servidor, revisa que la computadora principal esté encendida y en la misma red, y usa **Reintentar**. Si dice que el certificado es distinto, la computadora principal cambió de certificado: lleva un archivo de conexión nuevo.
- El registro de la ventana de Ariasmos de cada usuario está en `%LOCALAPPDATA%\Ariasmos\registro.log`.
