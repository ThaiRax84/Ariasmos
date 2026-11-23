# Guía de Ariasmos Central

Ariasmos Central es el servidor aparte que da de alta a tus clientes, les entrega un código de activación y les emite la licencia. Todo se hace con comandos, sin pantallas. Los comandos se corren en el servidor donde corra Central, desde la carpeta `central`.

## Ponerlo en marcha

1. Instala lo que pide `central/requirements.txt`.
2. Prepara Central en una carpeta propia (la llave privada vive ahí; guárdala y respáldala como un secreto):

   ```
   python manage.py inicializar_central --carpeta <carpeta>
   ```

   Crea la configuración, la base de datos y el par de llaves. Al final imprime la **llave pública**.
3. Copia esa llave pública dentro de la lista `licencias` del archivo `sistema/licencias/llaves.json` del programa que entregas. Mientras esa lista esté vacía, el programa funciona sin licencia.
4. Antes de los demás comandos, avisa dónde está la carpeta: pon su ruta en la variable de entorno `CENTRAL_INSTANCIA`.

Si corres `inicializar_central` otra vez sobre la misma carpeta, no cambia nada.

## Dar de alta un negocio

```
python manage.py negocio_nuevo --nombre "Nombre del negocio" --contacto "Quien lo atiende" --instalaciones 1
```

Imprime el identificador del negocio. `--instalaciones` es cuántos equipos puede activar. Para ver a todos: `python manage.py negocios` (pago, equipos, última renovación y versión).

## Sacar un código de activación

```
python manage.py codigo_activacion <identificador>
```

El código se muestra una sola vez, sirve una sola vez y vence a los 7 días. Entrégaselo al cliente.

## Registrar un pago

```
python manage.py registrar_pago <identificador> --hasta 2027-01-31
```

La licencia del cliente se renueva sola mientras la fecha de pago no haya pasado. Si no hay pago al corriente, el programa sigue funcionando hasta que termine el plazo de gracia y después queda solo para consultar.

## Cancelar una licencia

```
python manage.py revocar <identificador>
python manage.py revocar <identificador> --instalacion <huella>
python manage.py revocar <identificador> --deshacer
```

Sin `--instalacion` se cancela todo el negocio; con ella, un solo equipo. `--deshacer` restablece lo cancelado. El programa del cliente se entera en su siguiente renovación automática y queda en solo consulta: se puede ver, descargar y respaldar, pero no registrar cobros.

## Activar el programa del cliente

En el `configuracion.json` de la instancia del programa, la clave `central` lleva la dirección `https://` de Central. Después, en el equipo del cliente, con el código que sacaste:

```
python manage.py licencia_activar XXXXX-XXXXX-XXXXX-XXXXX
python manage.py licencia_estado
```

El primero activa la licencia; el segundo cuenta en palabras llanas cómo está. El programa da 14 días desde su primer arranque para activarlo. Después se renueva solo, cada vez que puede hablar con Central.
