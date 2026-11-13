# Sistema de cobro y control de titulares

Sistema local y multiusuario para llevar un padrón de titulares, asignar a cada uno una matrícula única que sirve como referencia de pago y autorizar altas y bajas con tres vías de aprobación (bandeja, delegación temporal y código por teléfono). Todo se configura en un asistente de primer uso: vocabulario, plantilla, conceptos de cobro, roles y políticas. El repositorio no trae datos de ningún negocio.

La especificación está en [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md). Este repositorio contiene la Fase 1.

## Requisitos

- Python 3.12 o posterior.
- Nada más: SQLite viene con Python y todas las dependencias están en `requirements.txt`.

## Instalación

### Windows (PowerShell)

```powershell
cd ruta\al\repositorio
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd sistema
python manage.py inicializar
python manage.py migrate
python manage.py servir
```

### Linux

```bash
cd ruta/al/repositorio
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cd sistema
python manage.py inicializar
python manage.py migrate
python manage.py servir
```

`inicializar` crea la carpeta `instancia/` (fuera de git) con la clave de Django, la clave de matrícula y la clave de la bitácora (32 bytes cada una) y la ruta de la base, e imprime un **token de instalación**. En una instancia que ya existe, `inicializar` solo agrega las claves que falten (por ejemplo, la de la bitácora al actualizar). Guárdalo: el asistente lo pide en el primer paso. Si se pierde, `python manage.py inicializar --nuevo-token` genera otro. Nunca borres ni regeneres `instancia/configuracion.json` ni `instancia/ancla_auditoria.json` en una instalación con datos: sin la clave de matrícula no se reconstruyen las matrículas y sin la clave y el ancla de la bitácora no se puede verificar su integridad.

Para usar otra carpeta de instancia, define la variable de entorno `COBRO_INSTANCIA` con su ruta.

## Primer uso

1. Abre `http://localhost:8000/` en el navegador del servidor. Te lleva al asistente.
2. Captura el token, el nombre del negocio y la plantilla: `generico` (sirve tal cual a la mayoría de negocios con clientes recurrentes), `escuela` o un archivo de plantilla propio. Puedes usarla tal cual o cambiar vocabulario y conceptos; luego captura importes, los **datos de pago** (CLABE, beneficiario, medios aceptados; se puede omitir y completar después en *Configuración → Datos de pago*), el primer usuario de Dirección y activa su autenticador (cualquier app TOTP; la clave se muestra como texto y como enlace `otpauth://`).
3. Al terminar, ese navegador queda como el primer equipo aprobado.

Cada navegador nuevo queda **pendiente** y muestra un código; Supervisión o Dirección lo aprueba en *Equipos*, donde también puede descartar los pendientes. Los pendientes de más de 24 horas se depuran solos y hay un tope de pendientes configurable. Desde la consola del servidor también se puede aprobar: `python manage.py aprobar_dispositivo CODIGO --nombre "Caja 1"`.

## Datos de pago y plantillas

- La ficha de pago se arma sola con la cuenta bancaria principal: banco, CLABE agrupada, beneficiario, medios aceptados y la indicación de dónde escribir la matrícula. La CLABE se valida y el banco se reconoce por sus tres primeros dígitos con el catálogo de `datos/bancos.json`, que se carga solo al migrar (o con `python manage.py cargar_bancos`).
- *Configuración → Guardar configuración como plantilla* descarga un JSON con vocabulario, roles, políticas, catálogos y conceptos, sin importes, cuentas, usuarios ni datos de personas. Ese archivo se puede importar en el asistente de otra instalación; se valida contra un esquema estricto (máximo 256 KB).
- La longitud de la matrícula (7), la sede (0) y las ranuras (10) no se preguntan en el asistente: están en *Configuración → Ajustes avanzados* y solo se pueden cambiar antes de emitir la primera matrícula.

## Cobro y caja

- **Cargos.** Los conceptos recurrentes generan un cargo por periodo para cada titular activo (el día de generación es un parámetro); los únicos marcados al dar de alta se cargan al aprobarse el alta; los recargos nacen solos según la regla del concepto. Las becas son un porcentaje sobre un concepto recurrente y se aplican al generar cada cargo. Nada del libro se edita ni se borra: cancelar, condonar o revertir crea un asiento de reverso.
- **Familias.** Varios titulares pueden pertenecer a una familia: comparten contacto responsable y estado de cuenta, y lo que sobra de un pago cubre los cargos de los demás miembros antes de quedar como saldo a favor.
- **Cobrar en efectivo.** Quien cobra abre su turno en *Mi caja*, busca al titular, captura el importe, revisa cómo se reparte y confirma; se emite un recibo foliado con código de verificación (vista imprimible y PDF). Al cerrar el turno se cuenta el efectivo por denominación sin ver lo esperado (arqueo ciego). El efectivo se entrega a Supervisión, que confirma lo recibido en su propia sesión, o se registra como depósito bancario.
- **Estado de cuenta en PDF.** Desde la ficha de un titular o de una familia se descarga el estado de cuenta (cargos con su saldo, pagos y cómo pagar). Cada emisión queda en la bitácora.
- **Trabajador.** Genera cargos y recargos, caduca solicitudes, depura equipos pendientes y archivos en revisión vencidos, y verifica la bitácora una vez al día. Si estuvo apagado, se pone al día sin duplicar:

  ```bash
  python manage.py trabajador            # en bucle
  python manage.py trabajador --una-vez  # un ciclo
  ```

## Banco

- **Importar.** En *Banco → Importar* (permiso «Importar banco y conciliar») se sube el estado de cuenta en PDF (lector incluido para el formato PyME de un banco; la CLABE del estado debe ser de una cuenta registrada) o un Excel/CSV de movimientos de cualquier banco. Para el Excel o CSV se propone qué es cada columna (fecha, abonos, cargos o importe con signo, referencia, concepto, saldo); la correspondencia se corrige en pantalla y se recuerda por cuenta. Si hay columna de saldo, los saldos deben cuadrar con los importes. Antes de escribir nada se muestra una vista previa; reimportar el mismo periodo no duplica.
- **Identificación.** Un abono con una sola matrícula válida y aislada en la referencia o el concepto se aplica solo como pago por banco (con la fecha del banco y recibo de la serie `serie_recibos_banco`). Lo dudoso (matrícula incrustada, un dígito mal, varias matrículas, pagador conocido) queda como sugerencia en la cola; con `aplicar_solo_por_pagador = 1`, un pagador confirmado `confirmaciones_pagador_confiable` veces se aplica solo cuando el importe coincide con lo que se debe. Los depósitos en efectivo se emparejan con los depósitos de caja por conciliar de la misma cuenta, importe y fecha (± `dias_tolerancia_deposito`); los cargos y devoluciones quedan informativos.
- **Cola.** Operación puede proponer a quién pertenece un movimiento; Supervisión confirma (el sistema aprende la cuenta del pagador), corrige, empareja un depósito o lo marca como «no es un cobro» con motivo. La cuenta completa del pagador solo la ve quien concilia. Revertir un pago por banco devuelve su movimiento a la cola.
- **Continuidad y revisión.** Cada importación queda clasificada y la clasificación se ve en la vista previa, en el historial y en la bitácora: `primera` (no había estados en PDF de esa cuenta), `verificada` (el periodo empieza al día siguiente del último estado importado y abre con el saldo con que aquel cerró), `con_hueco` (quedan días sin importar, es anterior a lo importado o no trae periodo legible) o `no_verificable` (Excel o CSV). Un PDF que sigue al anterior pero abre con otro saldo, o que repite un periodo ya importado con otros saldos, se rechaza completo sin escribir nada. Las importaciones `con_hueco` o `no_verificable` que aplicaron pagos (al importar o después desde la cola) aparecen en el inicio de quien ve la bitácora hasta que alguien distinto de quien importó las marca como revisadas.
- **Límites de archivos.** PDF hasta 10 MB y 300 páginas, sin cifrar; Excel hasta 5 MB (50 MB descomprimido), 20 000 filas y 60 columnas; CSV hasta 5 MB en UTF-8 o Latin-1. Nunca se evalúan fórmulas ni se guarda el archivo: solo su huella SHA-256 y su nombre.

## Importación inicial del padrón

*Configuración → Importar padrón inicial* (Dirección, con reingreso de contraseña) acepta el Excel o CSV que ya se tenga. Se proponen las columnas (nombre y apellidos o nombre completo, agrupación, responsable, teléfono, correo y saldo por concepto o total) y se muestra una vista previa con los errores de cada renglón, los duplicados (mismo nombre y teléfono, en el padrón o dentro del archivo) y las familias propuestas (mismo responsable y teléfono), que se pueden desmarcar. Nada se escribe hasta confirmar; entonces, en una sola operación, se dan de alta los titulares activos con su matrícula, sus contactos, las familias y el saldo inicial (cargo si debe, pago de la serie `serie_recibos_saldo_inicial` si tiene a favor). Al final se descargan las matrículas asignadas (Excel y CSV) y todas las fichas de pago en un PDF. Si el nombre completo viene en una sola columna, las dos últimas palabras se toman como apellidos.

## Cuentas de usuario

Nadie teclea la contraseña de otra persona. Al crear una cuenta (o con «Restablecer acceso» al editarla) el sistema muestra una sola vez un **código de activación** (`XXXXX-XXXXX`) que vence en 72 horas por defecto. La persona entra en «Tengo un código de activación», escribe su usuario y el código y elige su contraseña; si su rol lo exige, después da de alta su autenticador.

## Bitácora

Cada evento queda numerado y sellado con la clave de la bitácora, y el último sello se ancla en `instancia/ancla_auditoria.json`. `python manage.py verificar_auditoria` (o el botón en *Auditoría*) detecta alteraciones, huecos y eventos borrados; un fallo se muestra como alerta en el inicio de quien ve la auditoría. Cada titular tiene su historial en lenguaje llano en su ficha.

## HTTPS y red local

Por defecto las cookies llevan la marca `Secure`, así que fuera de `localhost` el sistema debe servirse con TLS (por ejemplo, Caddy delante de waitress; ver §3 y §10 de la arquitectura). Para probar en una red local sin TLS, crea la instancia con `python manage.py inicializar --sin-https`.

Los nombres de host aceptados y los orígenes de confianza se editan en `instancia/configuracion.json` (`hosts`, `origenes_confiables`). `proxies_confiables` (por defecto `["127.0.0.1", "::1"]`) indica desde qué direcciones se acepta la cabecera `X-Forwarded-For` para conocer la IP real del cliente; con https activo se envía HSTS de un año. Para escuchar en la red: `python manage.py servir --host 0.0.0.0 --puerto 8000`.

## Demostración

En una instalación vacía (después de `migrate`):

```bash
python manage.py demostracion --contrasena "una-contrasena-larga"
```

Crea un negocio de demostración con la plantilla `escuela`, los usuarios `operacion`, `supervision` y `direccion` (imprime los secretos de autenticador), cuatro titulares (dos en una familia) con cargos de los últimos tres meses y sus recargos, un turno de caja abierto para `operacion` y una cuenta bancaria ficticia con tres abonos importados: uno aplicado solo y dos en la cola por identificar; como es un archivo genérico importado por `supervision`, `direccion` la ve pendiente de revisión. Después aprueba tu navegador con `aprobar_dispositivo`.

## Pruebas

```bash
pip install -r requirements-pruebas.txt
python -m pytest
```

Se corren desde la raíz del repositorio. No necesitan `instancia/`.

## Comandos útiles

| Comando | Para qué |
|---|---|
| `inicializar` | Crea `instancia/` con claves aleatorias |
| `servir` | Servidor de producción (waitress) |
| `aprobar_dispositivo CODIGO` | Aprueba un equipo desde el servidor |
| `trabajador` | Tareas periódicas: cargos, recargos, solicitudes, equipos y bitácora |
| `cargar_bancos` | Carga o actualiza el catálogo de bancos sin borrar ni duplicar |
| `verificar_auditoria` | Verifica la cadena de hashes de la auditoría |
| `demostracion` | Configura una instalación de prueba |

## Licencia

Este programa es propietario: todos los derechos reservados. Consulta el archivo [`LICENSE`](LICENSE).
