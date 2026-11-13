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
   Get-FileHash "$env:USERPROFILE\Downloads\Ariasmos-0.4.0-instalador.exe" -Algorithm SHA256
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

Si perdiste el token antes de terminar el asistente: menú Inicio → **Ariasmos** → **Generar token nuevo del asistente**. Pide permiso de administrador y muestra un token nuevo; el anterior deja de servir.

## 3. Asistente de primer uso

El navegador se abre en `https://localhost/`. El asistente te lleva paso a paso:

1. **Datos del negocio**: pega el token, escribe el nombre, elige la zona horaria, la moneda y la plantilla («escuela» o «genérico»).
2. **Vocabulario y conceptos**: cómo se llaman las personas a las que se cobra y qué conceptos se cobran. Se puede dejar como viene.
3. **Importes** de cada concepto y, si aplica, el recargo por pago tardío.
4. **Datos de pago**: la cuenta bancaria (CLABE y beneficiario) que aparece en las fichas de pago. Se puede completar después.
5. **Cortes y respaldo**: la carpeta donde se dejan los cortes y la carpeta del respaldo diario. Aquí aparece la **clave de recuperación** (ver abajo).
6. **Primer usuario de Dirección**: tu usuario y contraseña.
7. **Autenticador**: instala en tu teléfono una aplicación gratuita como Google Authenticator, Microsoft Authenticator, Authy o 2FAS, escanea el código QR y escribe el código de 6 dígitos.

## 4. La clave de recuperación

En el paso de cortes y respaldo aparece una clave larga en grupos de 4 letras y números. **Es la única forma de abrir los respaldos.** Sin ella, si el equipo se descompone o se pierde, la información no se puede recuperar.

- Imprímela o cópiala a mano, completa.
- Guárdala **fuera de este equipo**, en un lugar seguro (no en la misma carpeta de los respaldos ni en una foto en el mismo equipo).
- Marca la casilla «Ya la guardé». Después de eso el sistema no la vuelve a mostrar.

Si te saltaste ese paso, Dirección verá un aviso en el inicio hasta que la guarde (menú **Respaldos** → **Clave de recuperación**).

## 5. Conectar las demás computadoras

Las demás computadoras **no instalan nada del programa**: entran con el navegador. Solo necesitan confiar una vez en el certificado del servidor.

1. En el servidor, entra con un usuario de Supervisión o Dirección y abre **Equipos** → **Conectar otra computadora**.
2. Descarga **instalar-certificado.cmd** y pásalo a la otra computadora (por la red o con una memoria USB).
3. En la otra computadora: clic derecho sobre el archivo → **Ejecutar como administrador**. Si Windows avisa que el archivo viene de internet, elige **Más información** → **Ejecutar de todas formas**.
4. Cierra y vuelve a abrir el navegador y entra a `https://NOMBRE-DEL-SERVIDOR/` (el nombre aparece en esa misma pantalla).
5. La primera vez el navegador queda **pendiente**: apruébalo desde el servidor en **Equipos**.

## 6. Dar permiso a una carpeta

El sistema corre con una cuenta de Windows limitada que, por seguridad, no puede escribir en las carpetas personales de los usuarios. Si quieres que los cortes o los respaldos se guarden, por ejemplo, en una carpeta de OneDrive de tu usuario:

1. Menú Inicio → **Ariasmos** → **Dar permiso a una carpeta**.
2. Acepta el permiso de administrador.
3. Escribe o pega la ruta completa de la carpeta y presiona Enter.
4. Vuelve a la pantalla de **Destinos de cortes** o de **Respaldos** y guarda la carpeta otra vez.

Si la pantalla dice que el servicio no tiene permiso para escribir en la carpeta, es este paso el que falta.

## 7. Actualizar

1. Descarga el instalador nuevo y comprueba su hash (paso 1).
2. Ejecútalo en el servidor. Detecta la instalación existente, detiene el sistema, guarda una copia de la carpeta de datos en `C:\ProgramData\Ariasmos\antes-de-actualizar\` y, si hay carpeta de respaldo configurada, hace un respaldo cifrado.
3. Reemplaza el programa, actualiza la base de datos y vuelve a arrancar. No se muestra token: tus usuarios y datos siguen igual.

## 8. Desinstalar

Panel de control → Programas → **Ariasmos** → Desinstalar (o menú Inicio → Ariasmos → Desinstalar Ariasmos).

- Se detienen y quitan los servicios, la regla del cortafuegos y el certificado.
- El instalador pregunta si quieres **borrar también los datos**. La respuesta recomendada es **No**: los datos se conservan en `C:\ProgramData\Ariasmos` y una instalación nueva los vuelve a usar.
- Si eliges **Sí**, se borran la base, las claves y los registros. No se puede deshacer.

## Si algo falla

- El registro de la instalación está en `C:\ProgramData\Ariasmos\registros\instalacion.log`.
- Los registros de los tres servicios (`AriasmosWeb`, `AriasmosTrabajador`, `AriasmosTLS`) están en la misma carpeta.
- Si el puerto 443 está ocupado por otro programa, el instalador lo dice: ciérralo o desinstálalo y vuelve a ejecutar el instalador.
