# Restaurar en un equipo nuevo

Usa esta guía si el equipo donde estaba instalado el sistema se descompuso, se perdió o lo vas a cambiar por otro.

## Lo que necesitas

- El **archivo de respaldo** más reciente: se llama `ariasmos-AAAAMMDD-HHMMSS.respaldo` y está en la carpeta de respaldo que configuraste (por ejemplo en la nube o en un disco externo).
- La **clave de recuperación** que imprimiste al instalar (grupos de 4 letras y números separados por guiones).
- El instalador de Ariasmos (de preferencia la misma versión o una más nueva) y su `SHA256SUMS.txt`.

Sin la clave de recuperación el respaldo **no se puede abrir**; nadie puede recuperarla.

## Pasos

1. Copia el archivo `.respaldo` al equipo nuevo (por ejemplo al Escritorio).
2. Comprueba el instalador y ejecútalo como se explica en la [guía de instalación](GUIA-INSTALACION.md).
3. En la página **Restaurar desde un respaldo**, marca la casilla, elige el archivo `.respaldo` y escribe la clave de recuperación. Puedes escribirla con o sin guiones, en mayúsculas o minúsculas.
4. Termina la instalación. El sistema:
   - comprueba que la clave corresponde al respaldo y que el archivo no está dañado ni alterado;
   - verifica la base de datos, los conteos y la bitácora;
   - deja la información y las claves en `C:\ProgramData\Ariasmos\instancia`.
5. Abre `https://localhost/` y entra con tus usuarios de siempre, con su contraseña y su autenticador.
6. Vuelve a conectar las demás computadoras (sección 5 de la guía de instalación): el certificado del servidor nuevo es distinto (tiene otra huella), así que hay que instalarlo otra vez en cada una.
7. Revisa en **Respaldos** que la carpeta de respaldo siga siendo válida en este equipo y, si hace falta, dale permiso con **Dar permiso a una carpeta**.

## Si la restauración falla

- «La clave no corresponde a este respaldo, o el respaldo fue alterado o está incompleto»: revisa que escribiste bien la clave y que el archivo terminó de copiarse. Si generaste una clave nueva en algún momento, los respaldos anteriores a ese cambio solo se abren con la clave anterior.
- «Ya hay una instalación con datos en este equipo»: el instalador solo restaura en un equipo sin datos. Desinstala marcando **borrar también los datos** (solo si de verdad no los necesitas) o pide ayuda para restaurar con el comando.

## Restaurar con el comando (avanzado)

Desde una ventana de administrador, en la carpeta `C:\Program Files\Ariasmos\app\sistema`:

```
set COBRO_INSTANCIA=C:\ProgramData\Ariasmos\instancia
..\..\python\python.exe manage.py restaurar --archivo "D:\Respaldos\ariasmos-20261112-020000.respaldo" --clave "XXXX-XXXX-..."
..\..\python\python.exe manage.py migrate
```

Con `--reemplazar` sustituye una instalación existente; antes guarda una copia de lo que había. Después reinicia los servicios `AriasmosWeb`, `AriasmosTrabajador` y `AriasmosTLS`.
