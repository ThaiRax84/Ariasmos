# Referencia técnica de Ariasmos

Detalle de funciones para quien administra o desarrolla el sistema. Para instalar y usar, ver la [guía de instalación](GUIA-INSTALACION.md) y la [guía de uso](GUIA-USO.md).

## Datos de pago y plantillas

- La ficha de pago se arma sola con la cuenta bancaria principal: banco, CLABE agrupada, beneficiario, medios aceptados y la indicación de dónde escribir la matrícula. La CLABE se valida y el banco se reconoce por sus tres primeros dígitos con el catálogo de `datos/bancos.json`, que se carga solo al migrar (o con `python manage.py cargar_bancos`).
- *Configuración → Guardar configuración como plantilla* descarga un JSON con vocabulario, roles, políticas, catálogos y conceptos, sin importes, cuentas, usuarios ni datos de personas. Ese archivo se puede importar en el asistente de otra instalación; se valida contra un esquema estricto (máximo 256 KB).
- **Moneda.** Todos los importes se capturan y se muestran con el símbolo y el código de la moneda del negocio (por ejemplo `$1,250.50 MXN`). Solo se ofrecen monedas de dos decimales. La moneda se cambia en *Ajustes avanzados* mientras no haya ningún cargo ni pago; después queda fija. Las plantillas incluidas traen denominaciones de caja de MXN: con otra moneda no se cargan y el inicio avisa que hay que capturarlas. La plantilla exportada incluye la moneda.
- **Captura guiada.** Cada campo solo deja teclear lo que acepta y hasta el largo que acepta (dígitos en CLABE, teléfono y códigos; importes con el símbolo ya puesto; porcentajes con `%`), también al pegar. Es una ayuda de pantalla con `estaticos/js/captura.js`: sin JavaScript todo funciona igual y el servidor valida todo lo que recibe. En las reglas de recargo se llena el importe fijo o el porcentaje según el tipo.
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

## Cortes

- **Corte diario de caja.** Al cerrar un turno con cobros o devoluciones (después del arqueo ciego) se genera el corte de esa caja: recibos uno por uno, devoluciones, total cobrado, fondo, contado, diferencia, nota y traslados. Cada persona ve solo los suyos; quien tiene «Ver cortes» ve todos. Si a la hora límite (`hora_limite_corte_diario`, 18:00) hay un turno con cobros del día sin cerrar, o uno abierto de un día anterior, quien recibe efectivo ve la alerta «corte diario pendiente»; nada se bloquea y el corte que se hace después queda marcado **tardío**.
- **Corte mayor.** El trabajador lo genera como borrador el día `dia_corte_mayor` (1) del mes siguiente y se pone al día si estuvo apagado. Mientras es borrador se recalcula al abrirlo. Quien tiene «Cerrar cortes» lo cierra con reingreso de contraseña; si pasan `dias_plazo_corte_mayor` (5) días, el trabajador lo cierra marcado **sin revisar**. No se cierra un mes si el anterior sigue en borrador. Al cerrarlo queda como fotografía con su huella y el mes queda **bloqueado**: el libro rechaza cualquier asiento fechado dentro de él; un pago bancario tardío se registra con fecha de hoy y conserva la fecha del banco como referencia.
- **Lista de cobranza.** Cada semana (`dia_semana_cobranza`, 1 = lunes; 0 la apaga) y a demanda: un renglón por cargo vencido con saldo, con los datos de pago del negocio en el encabezado.
- **Entrega a carpeta.** En *Configuración → Destinos de cortes* (o en el asistente) se elige una carpeta y, por tipo de corte, si se entrega y con qué nivel de detalle: `completo`, `solo_nombres` (sin matrícula ni contacto) o `sin_nombres` (solo matrícula). Cada entrega deja PDF, CSV y JSON con nombres generados por el sistema y actualiza un `manifiesto.json` con la huella de cada archivo, el ancla de la bitácora y una firma; `python manage.py verificar_entrega <carpeta>` la comprueba. Si la carpeta no está disponible, la entrega se reintenta con espera creciente y aparece como alerta.
- **Permisos.** «Ver cortes» y «Cerrar cortes». En las plantillas, Operación ya no trae «Ver cortes» (ve sus cortes diarios con «Abrir y cerrar su turno de caja»). No hay instalaciones en producción: los roles de una instalación ya creada no se cambian solos; si los hubiera, se ajustan en *Roles*.

## Respaldo y restauración

- **Clave de recuperación.** Se genera con la instancia y se muestra una sola vez (en el asistente, o en *Respaldos → Clave de recuperación* para quien tiene «Administrar respaldos»), hasta marcar «ya la guardé». Imprímela y guárdala fuera del equipo: sin ella ningún respaldo se abre. «Generar clave nueva» cambia la clave de los respaldos futuros; los anteriores siguen abriéndose solo con la clave anterior.
- **Respaldo diario** a la hora `hora_respaldo` (02:00) en la carpeta configurada: copia consistente de la base, claves y ancla, cifrada con AES-256-GCM, como `ariasmos-AAAAMMDD-HHMMSS.respaldo`. Se conservan 30 diarios y 12 mensuales. Una vez al mes se abre el último en una carpeta temporal y se comprueban la integridad de la base, los conteos y la bitácora. Si no hay carpeta, si el último respaldo correcto tiene más de 48 horas o si la prueba falla, hay alerta.
- **Restaurar** en un equipo nuevo (con la carpeta de instancia vacía) o sobre una instalación existente (guarda antes una copia):

  ```bash
  python manage.py restaurar --archivo D:\Respaldos\ariasmos-20261112-020000.respaldo --clave "XXXX-XXXX-..."
  python manage.py restaurar --archivo ... --clave "..." --reemplazar
  python manage.py migrate
  ```

- El secreto del autenticador de cada usuario se guarda cifrado con `clave_secretos` de la instancia. `python manage.py inicializar` añade `clave_respaldo` y `clave_secretos` a una instancia existente.

## Cuentas de usuario

Nadie teclea la contraseña de otra persona. Al crear una cuenta (o con «Restablecer acceso» al editarla) el sistema muestra una sola vez un **código de activación** (`XXXXX-XXXXX`) que vence en 72 horas por defecto. La persona entra en «Tengo un código de activación», escribe su usuario y el código y elige su contraseña; si su rol lo exige, después da de alta su autenticador.

## Bitácora

Cada evento queda numerado y sellado con la clave de la bitácora, y el último sello se ancla en `instancia/ancla_auditoria.json`. `python manage.py verificar_auditoria` (o el botón en *Auditoría*) detecta alteraciones, huecos y eventos borrados; un fallo se muestra como alerta en el inicio de quien ve la auditoría. Cada titular tiene su historial en lenguaje llano en su ficha.

## HTTPS y red local

Por defecto las cookies llevan la marca `Secure`, así que fuera de `localhost` el sistema debe servirse con TLS (por ejemplo, Caddy delante de waitress; ver §3 y §10 de la arquitectura). Para probar en una red local sin TLS, crea la instancia con `python manage.py inicializar --sin-https`.

Los nombres de host aceptados y los orígenes de confianza se editan en `instancia/configuracion.json` (`hosts`, `origenes_confiables`). `proxies_confiables` (por defecto `["127.0.0.1", "::1"]`) indica desde qué direcciones se acepta la cabecera `X-Forwarded-For` para conocer la IP real del cliente; con https activo se envía HSTS de un año. Con https activo, `servir` solo escucha en 127.0.0.1 (la red la atiende el servicio TLS); `--permitir-red` lo fuerza. En la instalación de Windows, Caddy atiende `https://<nombre del equipo>` y `https://localhost` en el 443 con una autoridad de certificados interna; `python manage.py generar_caddyfile` escribe su configuración. Con https activo se activan `SECURE_SSL_REDIRECT`, HSTS de un año con subdominios y cookies seguras; `manage.py check --deploy` queda sin avisos salvo `security.W021` (precarga de HSTS), silenciado porque no aplica a nombres de una red local.


## Demostración

En una instalación vacía (después de `migrate`):

```bash
python manage.py demostracion --contrasena "una-contrasena-larga"
```

Crea un negocio de demostración con la plantilla `escuela`, los usuarios `operacion`, `supervision` y `direccion` (imprime los secretos de autenticador), cuatro titulares (dos en una familia) con cargos de los últimos tres meses y sus recargos, un turno de caja abierto para `operacion` y una cuenta bancaria ficticia con tres abonos importados: uno aplicado solo y dos en la cola por identificar; como es un archivo genérico importado por `supervision`, `direccion` la ve pendiente de revisión. También deja un corte diario cerrado, los cortes mayores de los meses anteriores en borrador (con un plazo de cierre de 31 días para que se puedan revisar) y una carpeta temporal de entrega con sus archivos y su manifiesto. Después aprueba tu navegador con `aprobar_dispositivo`.

## Comandos útiles

| Comando | Para qué |
|---|---|
| `inicializar` | Crea `instancia/` con claves aleatorias |
| `servir` | Servidor de producción (waitress) |
| `aprobar_dispositivo CODIGO` | Aprueba un equipo desde el servidor |
| `trabajador` | Tareas periódicas: cargos, recargos, solicitudes, equipos, cortes, entregas, respaldo y bitácora |
| `respaldar` | Hace un respaldo cifrado ahora |
| `probar_respaldo` | Abre el último respaldo en una carpeta temporal y lo verifica |
| `restaurar --archivo ... --clave ...` | Restaura una instalación desde un respaldo |
| `verificar_entrega <carpeta>` | Comprueba la firma del manifiesto y las huellas de una carpeta de entrega |
| `cifrar_secretos` | Cifra los secretos del autenticador que estén en claro |
| `cargar_bancos` | Carga o actualiza el catálogo de bancos sin borrar ni duplicar |
| `verificar_auditoria` | Verifica la cadena de hashes de la auditoría |
| `demostracion` | Configura una instalación de prueba |
| `version` | Muestra la versión instalada |
| `generar_caddyfile --nombre --salida` | Escribe la configuración del servicio TLS |
