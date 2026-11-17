# Guía de instalación de Ariasmos

Esta guía es para la persona que instala el sistema en el equipo que hará de servidor. No hace falta saber programar.

## Lo que necesitas

- Una computadora con **Windows 10 u 11 de 64 bits** que se quede encendida mientras se use el sistema. Será el «servidor».
- Una cuenta de **administrador** de esa computadora.
- Que las demás computadoras estén en la **misma red** (el mismo módem o la misma red Wi‑Fi).
- Una impresora o una hoja y pluma, para guardar la **clave de recuperación**.

## 1. Descargar y comprobar el instalador

1. Descarga el archivo `Ariasmos-X.Y.Z-instalador.exe` y el archivo `SHA256SUMS.txt` que lo acompaña.
2. Comprueba que el instalador no se dañó ni fue cambiado. Abre **PowerShell** (menú Inicio → escribe «PowerShell») y escribe, cambiando la ruta por la de tu carpeta de descargas:

   ```
   Get-FileHash "$env:USERPROFILE\Downloads\Ariasmos-0.8.0-instalador.exe" -Algorithm SHA256
   ```

3. El texto largo que aparece en la columna **Hash** debe ser **igual** al que viene en `SHA256SUMS.txt` (no importan mayúsculas o minúsculas). Si no es igual, **no instales**: vuelve a descargarlo.

## 2. Instalar

1. Haz doble clic en el instalador.
2. Windows puede mostrar **«Windows protegió su PC»**. Aparece porque el instalador no está firmado con un certificado comercial; no significa que tenga un virus si comprobaste el hash en el paso anterior. Haz clic en **Más información** y luego en **Ejecutar de todas formas**.
3. Acepta que el programa haga cambios en el equipo (te pedirá la contraseña de administrador si no la tienes abierta).
4. Lee y acepta la licencia.
5. Si este equipo **reemplaza a otro** donde ya usabas el sistema, marca «Restaurar desde un respaldo» y sigue la guía [RESTAURAR.md](RESTAURAR.md). Si es una instalación nueva, déjala sin marcar.
6. Haz clic en **Instalar** y espera. Tarda unos minutos: prepara la base de datos, los tres servicios del sistema, el certificado de seguridad y la regla del cortafuegos.
7. Al terminar, el instalador muestra el **token del asistente**. Haz clic en **Copiar**. Ese token se pide una sola vez y no se guarda en ningún lado.
8. Deja marcada la casilla «Abrir Ariasmos en el navegador» y haz clic en **Finalizar**.

El instalador deja un acceso directo **Ariasmos** en el escritorio y en el menú Inicio, con el medallón negro del jinete; abre el programa en el navegador. Al abrirlo aparece una vez la presentación de Ariasmos con su versión y después el inicio de sesión. El asistente de los ocho pasos muestra a la izquierda la lista de pasos y en cuál vas.

Si perdiste el token antes de terminar el asistente: menú Inicio → **Ariasmos** → **Generar token nuevo del asistente**. Pide permiso de administrador y muestra un token nuevo; el anterior deja de servir.

## 3. Asistente de primer uso

El navegador se abre en `https://localhost/`. El asistente te lleva paso a paso:

1. **Datos del negocio**: pega el token, escribe el nombre, elige la zona horaria, la moneda y la plantilla («escuela» o «genérico»), y marca si el negocio lleva **inventario** de artículos (se puede cambiar después en *Configuración → Inventario*).
2. **Vocabulario y conceptos**: cómo se llaman las personas a las que se cobra y qué conceptos se cobran. Se puede dejar como viene.
3. **Importes** de cada concepto y, si aplica, el recargo por pago tardío.
4. **Datos de pago**: la cuenta bancaria (CLABE y beneficiario) que aparece en las fichas de pago. Se puede completar después.
5. **Caja: cortes y retiros**: qué días de la semana hay corte de caja y la hora límite de cada uno (propone lunes a sábado a las 18:00; deja vacío el día que no tenga corte), si se capturan las piezas de cada billete y moneda, y los topes de los retiros de caja (importe máximo por retiro, importe y número máximo de retiros por día o por semana y efectivo máximo en caja). Lo que pase de un tope necesita la autorización de otra persona.
6. **Entrega y respaldo**: la carpeta donde se dejan los cortes, la carpeta del respaldo diario y, si quieres, la **carpeta vigilada del banco** con el tope por pago y los topes del banco (ver abajo). Si esta copia del programa trae llaves de actualización, también puedes activar aquí las **actualizaciones del programa** (sección 7). Aquí aparece la **clave de recuperación** (ver abajo).
7. **Primer usuario de Dirección**: tu usuario y contraseña.
8. **Autenticador**: instala en tu teléfono una aplicación gratuita como Google Authenticator, Microsoft Authenticator, Authy o 2FAS, escanea el código QR y escribe el código de 6 dígitos.

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

## 4. La clave de recuperación

En el paso de entrega y respaldo aparece una clave larga en grupos de 4 letras y números. **Es la única forma de abrir los respaldos.** Sin ella, si el equipo se descompone o se pierde, la información no se puede recuperar.

- Imprímela o cópiala a mano, completa.
- Guárdala **fuera de este equipo**, en un lugar seguro (no en la misma carpeta de los respaldos ni en una foto en el mismo equipo).
- Marca la casilla «Ya la guardé». Después de eso el sistema no la vuelve a mostrar.

Si te saltaste ese paso, Dirección verá un aviso en el inicio hasta que la guarde (menú **Respaldos** → **Clave de recuperación**).

## 5. Conectar las demás computadoras

Las demás computadoras **no instalan nada del programa**: entran con el navegador. Solo necesitan confiar una vez en el certificado del servidor.

Ese certificado (`ariasmos-servidor.crt`) es como una credencial del servidor: **solo sirve para que las demás computadoras reconozcan a este servidor** y sepan que hablan con él y no con otro. No contiene contraseñas ni datos del negocio, no permite reconocer a ningún otro sitio de internet y **vence en 10 años**. El instalador lo crea solo; su parte secreta nunca sale del servidor (se queda en `C:\ProgramData\Ariasmos\caddy\`).

1. En el servidor, entra con un usuario de Supervisión o Dirección y abre **Equipos** → **Conectar otra computadora**.
2. En esa pantalla aparecen la **huella SHA-256** y la **fecha de vencimiento** del certificado. Descarga **instalar-certificado.cmd** y pásalo a la otra computadora (por la red o con una memoria USB).
3. En la otra computadora: clic derecho sobre el archivo → **Ejecutar como administrador**. Si Windows avisa que el archivo viene de internet, elige **Más información** → **Ejecutar de todas formas**.
4. Cierra y vuelve a abrir el navegador y entra a `https://NOMBRE-DEL-SERVIDOR/` (el nombre aparece en esa misma pantalla).
5. La primera vez el navegador queda **pendiente**: apruébalo desde el servidor en **Equipos**.

Si prefieres hacerlo a mano, descarga `ariasmos-servidor.crt` desde la misma pantalla, comprueba que su huella coincide con la que se muestra y agrégalo en la otra computadora a **Entidades de certificación raíz de confianza** del **equipo local**.

Cuando falten 60 días o menos para el vencimiento, quienes aprueban equipos verán un aviso en el inicio. Basta con volver a ejecutar el instalador en el servidor (paso 7): genera un certificado nuevo y después hay que repetir esta sección en cada computadora.

## 6. Dar permiso a una carpeta

El sistema corre con una cuenta de Windows limitada que, por seguridad, no puede escribir en las carpetas personales de los usuarios. Si quieres que los cortes, los respaldos o la carpeta vigilada del banco estén, por ejemplo, en una carpeta de OneDrive de tu usuario:

1. Menú Inicio → **Ariasmos** → **Dar permiso a una carpeta**.
2. Acepta el permiso de administrador.
3. Escribe o pega la ruta completa de la carpeta y presiona Enter.
4. Vuelve a la pantalla de **Destinos de cortes**, de **Respaldos** o de **Carpeta vigilada del banco** y guarda la carpeta otra vez.

Si la pantalla dice que el servicio no tiene permiso para escribir en la carpeta, es este paso el que falta.

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
4. El certificado del servidor se conserva, así que las demás computadoras siguen funcionando sin hacer nada. Solo se genera uno nuevo si cambió el nombre del equipo o faltan menos de 60 días para que venza; en ese caso el registro de la instalación lo indica y hay que volver a conectar las demás computadoras (sección 5).

## 8. Desinstalar

Panel de control → Programas → **Ariasmos** → Desinstalar (o menú Inicio → Ariasmos → Desinstalar Ariasmos).

- Se detienen y quitan los servicios, la regla del cortafuegos y el certificado del servidor de las raíces de confianza de este equipo. En las demás computadoras puedes quitarlo a mano desde «Administrar certificados de equipo» (aparece como «Ariasmos NOMBRE-DEL-SERVIDOR»).
- El instalador pregunta si quieres **borrar también los datos**. La respuesta recomendada es **No**: los datos se conservan en `C:\ProgramData\Ariasmos` y una instalación nueva los vuelve a usar.
- Si eliges **Sí**, se borran la base, las claves y los registros. No se puede deshacer.

## Si algo falla

- El registro de la instalación está en `C:\ProgramData\Ariasmos\registros\instalacion.log`.
- Los registros de los tres servicios (`AriasmosWeb`, `AriasmosTrabajador`, `AriasmosTLS`) están en la misma carpeta.
- Si el puerto 443 está ocupado por otro programa, el instalador lo dice: ciérralo o desinstálalo y vuelve a ejecutar el instalador.
