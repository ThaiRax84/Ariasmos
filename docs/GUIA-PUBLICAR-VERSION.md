# Guía para publicar una versión de Ariasmos

Esta guía es para el dueño del programa. Explica cómo crear las llaves que firman las versiones, cómo publicar una versión nueva para que las instalaciones la vean en su Inicio y qué hacer si se pierde una llave. Todo se hace en **tu computadora**, nunca en la computadora de un negocio ni en la integración continua.

## Cómo funciona, en corto

- El código vive en su repositorio privado. Las versiones se publican en un **canal** aparte: otro repositorio privado que solo tiene publicaciones (*releases*), sin código.
- Cada publicación lleva el instalador, el **aviso de versión** (`version.json`) y su **firma** (`version.json.firma`). El programa solo acepta un aviso firmado con tu **llave de uso**.
- Hay una segunda llave, la **llave de recuperación**, que solo sirve para cambiar la llave de uso si la pierdes o te la roban.
- Cada instalación lee el canal con una **clave de solo lectura** propia que tú le das. Esa clave no permite publicar nada.
- La integración continua del repositorio compila el instalador y **no firma ni publica nada**.

## Lo que necesitas

- Tu computadora, con Python 3.12 y la biblioteca `cryptography` (`python -m pip install cryptography`).
- Una copia del repositorio del código (las herramientas están en `herramientas/firma/`).
- Dos memorias USB o lugares seguros distintos para guardar las llaves privadas.
- Una cuenta de GitHub con permiso para crear repositorios privados.

## 1. Generar las llaves (una sola vez)

1. Crea una carpeta **fuera** del repositorio, de preferencia en una memoria USB cifrada. Por ejemplo `E:\llaves-ariasmos`.
2. En una terminal, dentro de la carpeta del repositorio:

   ```
   python herramientas/firma/generar-llaves.py E:\llaves-ariasmos
   ```

3. Te pide dos contraseñas, una para cada llave: de al menos 16 caracteres y **distintas** entre sí. Anótalas en papel; sin ellas las llaves no sirven.
4. En la carpeta quedan:
   - `uso.llave-privada` y `recuperacion.llave-privada`: las llaves privadas, cifradas con su contraseña.
   - `llaves.json`: las dos llaves **públicas**.
5. Copia el contenido de `llaves.json` a `sistema/actualizaciones/llaves.json` del repositorio, haz un commit y compila un instalador nuevo. Esa versión es la primera que puede actualizarse sola. Las instalaciones que ya existen reciben las llaves solo cuando instalas ese instalador **a mano** (guía de instalación, sección 7, «A mano»).

Las llaves privadas **nunca** van al repositorio, a los secretos de GitHub Actions ni a la computadora de un negocio. El `.gitignore` excluye los archivos `*.llave-privada`, `*.pem` y `*.key`, pero no confíes solo en eso: guárdalas fuera de la carpeta del repositorio.

## 2. Guardar aparte la llave de recuperación

1. Copia `recuperacion.llave-privada` a una segunda memoria o lugar seguro, **en otro sitio** que la de uso (por ejemplo, en casa y en la oficina).
2. Bórrala de la memoria que usas para firmar versiones. La llave de recuperación solo se usa para cambiar la llave de uso (sección 6).
3. Guarda la contraseña de la llave de recuperación separada de la memoria donde está la llave.

Si alguien consigue tu llave de uso, la de recuperación te deja reemplazarla. Si las guardas juntas, quien se lleve una se lleva las dos.

## 3. Crear el canal

1. En GitHub crea un repositorio **privado** nuevo para las versiones, por ejemplo `ariasmos-versiones`. No subas código: solo tendrá publicaciones.
2. No le des acceso de escritura a nadie más.

## 4. Dar a cada instalación su clave de solo lectura

Cada negocio recibe una clave propia, para poder quitársela sin afectar a los demás.

1. En GitHub: **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Nombre: el de la instalación (por ejemplo «Sede centro»). Vencimiento: el que prefieras; anota la fecha para renovarla.
3. **Repository access → Only select repositories** → elige solo el canal (`ariasmos-versiones`).
4. **Permissions → Repository permissions → Contents: Read-only**. Nada más.
5. Genera la clave, cópiala y entrégala en persona o por un medio seguro a Dirección de esa instalación.
6. Dirección la pega en **Configuración → Actualizaciones del programa** junto con el repositorio del canal (`tu-usuario/ariasmos-versiones`) y activa la casilla. El programa la guarda cifrada y no la vuelve a mostrar.

Si una computadora se pierde o un negocio deja de usar el programa, revoca su clave en esa misma pantalla de GitHub.

## 5. Publicar una versión

1. **Consigue el instalador.** Sube `VERSION`, abre el PR y, con GitHub Actions en verde, descarga el artefacto `ariasmos-instalador` de la ejecución. Comprueba el instalador contra su `SHA256SUMS.txt`:

   ```
   Get-FileHash .\Ariasmos-0.9.0-instalador.exe -Algorithm SHA256
   ```

2. **Escribe los cambios** en un archivo de texto, una línea por cambio, hasta 20 líneas de 200 caracteres, sin formato. Por ejemplo `cambios.txt`:

   ```
   Topes del banco por día de la semana
   Aviso de versiones nuevas en el inicio
   ```

3. **Elige el contador.** Es un número entero que **siempre sube**: cada aviso que publiques debe llevar uno mayor que el anterior, aunque la versión sea la misma. Lleva una nota con el último que usaste. Un aviso con un contador igual o menor se rechaza.
4. **Elige el mínimo**: la versión más vieja desde la que se puede llegar a esta. Si una instalación tiene una versión menor, el aviso le dice que primero instale la versión mínima y no le ofrece la descarga.
5. **Firma**, con la memoria de la llave de uso conectada:

   ```
   mkdir salida-0.9.0
   python herramientas/firma/firmar-version.py --instalador .\Ariasmos-0.9.0-instalador.exe --version 0.9.0 --contador 7 --cambios .\cambios.txt --minimo 0.8.0 --llave E:\llaves-ariasmos\uso.llave-privada --salida .\salida-0.9.0
   ```

   Te pide la contraseña de la llave de uso, escribe `version.json` y `version.json.firma` y comprueba que el programa los aceptaría. Abre `version.json` y revisa versión, tamaño y cambios.
6. **Publica en el canal** una publicación nueva con exactamente estos tres archivos: el instalador, `version.json` y `version.json.firma` (y, si cambiaste la llave, también los dos archivos del cambio; ver sección 6). En la web: **Releases → Draft a new release**, etiqueta `v0.9.0`, adjunta los archivos y publica como **Latest** (no como borrador ni *pre-release*: el programa solo lee la última publicación). Con la herramienta de GitHub:

   ```
   gh release create v0.9.0 --repo tu-usuario/ariasmos-versiones --title "Ariasmos 0.9.0" --notes-file cambios.txt .\Ariasmos-0.9.0-instalador.exe .\salida-0.9.0\version.json .\salida-0.9.0\version.json.firma
   ```

7. **Comprueba** en una instalación: Dirección elige **Buscar ahora** en *Configuración → Actualizaciones del programa*; en unos minutos el Inicio muestra «Hay una versión nueva». Si no aparece, la misma pantalla dice el resultado de la última búsqueda y la bitácora tiene el motivo de un rechazo (`actualizacion_rechazada`).

No reutilices un número de versión ni un contador, y no edites `version.json` después de firmarlo: cualquier cambio, aunque sea un espacio, invalida la firma.

## 6. Si pierdes una llave

### Perdiste la llave de uso, su contraseña, o crees que alguien la tiene

1. Con la memoria de la llave de recuperación conectada:

   ```
   mkdir cambio-1
   python herramientas/firma/cambiar-llave.py --recuperacion F:\recuperacion.llave-privada --contador 1 --carpeta-llave E:\llaves-ariasmos --salida .\cambio-1
   ```

   El contador del cambio de llave es otro, propio, que también siempre sube (1 la primera vez, 2 la siguiente…). Te pide la contraseña de la llave de recuperación y una contraseña nueva para la llave de uso nueva, que queda como `uso-1.llave-privada`.
2. Firma la siguiente versión con la llave **nueva** (sección 5) y publícala con cinco archivos: instalador, `version.json`, `version.json.firma`, `cambio-de-llave.json` y `cambio-de-llave.json.firma`.
3. Cada instalación acepta primero el cambio de llave y luego la versión. Dirección ve en su Inicio que la llave cambió.
4. Vuelve a adjuntar los dos archivos del cambio en las publicaciones siguientes hasta que todas las instalaciones hayan buscado al menos una vez: una instalación que estuvo apagada solo lee la última publicación.
5. Desde ese momento la llave anterior ya no vale. Si alguien la robó, solo pudo usarla mientras las instalaciones no vieran el cambio, y además habría necesitado poder publicar en tu canal.

### Perdiste la llave de recuperación (pero tienes la de uso)

1. Genera un par nuevo de llaves (sección 1) en otra carpeta.
2. Copia el `llaves.json` nuevo al repositorio y compila la versión siguiente.
3. Firma **esa** versión con la llave de uso **actual** (la vieja) y publícala normal. Al instalarla, cada instalación queda con las llaves nuevas.
4. De ahí en adelante firma con la llave de uso nueva y guarda la de recuperación nueva como en la sección 2.

### Perdiste las dos llaves

El programa ya no puede actualizarse solo. Genera llaves nuevas (sección 1), compila un instalador con el `llaves.json` nuevo e instálalo **a mano** en el servidor de cada negocio (guía de instalación, sección 7, «A mano»).

### Se filtró la clave de solo lectura de una instalación

Revócala en GitHub, genera otra (sección 4) y entrégala a Dirección de esa instalación para que la reemplace. Esa clave solo permite leer el canal: no permite publicar ni firmar.

## Lo que nunca hay que hacer

- Subir una llave privada a un repositorio, a un correo o a un chat.
- Guardar llaves o contraseñas en los secretos de GitHub Actions o en la computadora de un negocio.
- Agregar a la integración continua un paso que firme o publique versiones.
- Bajar el contador o reutilizar uno.
- Dar a una instalación una clave con permiso de escritura.
