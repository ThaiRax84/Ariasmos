# Arquitectura — Sistema de cobro y control de titulares

Versión 0.16 · 13/11/2026 · Estado: fases 1 a 4b construidas; fase 5a (cambios de motor, §15) en construcción; fase 5b (interfaz) en diseño.

Este documento es la especificación. Quien construye sigue lo que dice aquí; cualquier cambio de diseño se propone primero y se implementa después.

## 1. Qué es

Un sistema local, multiusuario y configurable que:

1. Lleva el padrón de **titulares** (en una escuela: alumnos) y le da a cada uno una **matrícula única** que sirve como referencia de pago.
2. Genera **cargos** (inscripción, mensualidad, recargos, extras…) según categorías que el negocio define.
3. Registra **pagos** en efectivo y por banco, y los aplica solos a la cuenta del titular cuando la matrícula viene en la transferencia.
4. Controla el **efectivo** con caja, arqueo ciego y cadena de custodia.
5. Emite **cortes** periódicos (diario de caja y mayor) y los entrega a los destinos configurados.

No es específico de una escuela: vocabulario, categorías, roles, frecuencias y destinos se definen en un asistente de configuración. El repo incluye una plantilla «escuela» como punto de partida y nunca incluye datos de ningún negocio.

## 2. Principios

| Principio | Consecuencia |
|---|---|
| Local primero | Todo funciona sin internet. Internet solo se usa para respaldo y, si se configura, correo. |
| Nada se borra | Los movimientos de dinero son inmutables; se corrige con un contra-asiento. Las bajas son un estado, no un borrado. |
| Dos personas para lo delicado, cero esperas para lo normal | Solo las excepciones piden aprobación, y hay tres vías para darla (§6). |
| Configurable, no programado | Ningún nombre, monto, categoría, rol, frecuencia ni ruta vive en el código. |
| El servidor decide | Todo permiso se valida en el servidor en cada petición; la interfaz solo esconde lo que no aplica. |
| Simple para quien lo usa | Español, botones grandes, una tarea por pantalla, usable en pantalla chica. |

## 3. Stack

| Capa | Elección | Motivo |
|---|---|---|
| Lenguaje | Python 3.12+ | Ya instalado en el equipo destino. |
| Framework | Django (LTS vigente) | Autenticación, sesiones, CSRF, migraciones y ORM probados; menos seguridad escrita a mano. |
| Base de datos | SQLite en modo WAL, un archivo | Gratis, sin servicio aparte, respaldo trivial. El ORM permite pasar a PostgreSQL si se centralizan sedes. |
| Servidor | waitress detrás de Caddy (TLS) | Ambos corren como servicio en Windows sin dependencias de pago. |
| Interfaz | Plantillas del servidor + htmx incluido en el repo | Sin paso de compilación, sin CDN, funciona sin internet. |
| Tareas | Comando `trabajador` (bucle con tabla de tareas) | Idempotente; si la máquina estuvo apagada, se pone al día. |
| Archivos | reportlab (PDF), openpyxl (Excel) | Ligeros y ya presentes. |
| Cifrado | `cryptography` (AES-256-GCM), Argon2id para contraseñas | Estándar, sin binarios externos. |

Dinero siempre en **centavos enteros**. Zona horaria configurable (por defecto `America/Mexico_City`). El código va sin comentarios; la documentación vive en `docs/`.

## 4. Matrícula

### 4.1 Requisitos

- Numérica y de **7 dígitos**, porque la referencia numérica de un SPEI admite hasta 7. El asistente no pregunta la longitud; es un ajuste avanzado (5 a 12) que solo puede cambiarse antes de emitir la primera matrícula.
- Única, nunca reutilizada, sin cero inicial (los bancos lo recortan).
- Con dígito verificador que detecte los errores de captura comunes.
- No secuencial: no revela cuántos titulares hay ni permite adivinar la siguiente.
- Varias sedes pueden emitir sin conexión entre sí y sin chocar.

### 4.2 Construcción

Sea `L` la longitud total y `d = L − 1` los dígitos del cuerpo.

1. **Espacio.** `M = 9·10^(d−1)` cuerpos posibles (900 000 con `L = 7`).
2. **Índice.** Cada instalación tiene `ranuras` (por defecto 10) y un número de `sede` entre 0 y `ranuras − 1`. Con un contador local `n = 0, 1, 2…`, el índice global es `i = n·ranuras + sede`. Sedes distintas con la misma clave nunca producen el mismo índice. Cada sede dispone de `M / ranuras` matrículas (90 000).
3. **Permutación con clave.** `y = P_k(i)` donde `P_k` es una red de Feistel balanceada de 8 rondas sobre `Z_m × Z_m`, con `m = 10^⌈d/2⌉`:
   - `x = izq·m + der`
   - en cada ronda `r`: `(izq, der) ← (der, (izq + F_k(r, der)) mod m)`
   - `F_k(r, v) = HMAC-SHA256(k, "matricula-v1|" ‖ r ‖ v ‖ m)` tomando 128 bits `mod m`
   - si el resultado cae fuera de `[0, M)`, se vuelve a aplicar la red (*cycle-walking*) hasta que caiga dentro.

   Una red de Feistel es biyectiva para cualquier `F`, y el *cycle-walking* conserva la biyección al restringir el dominio. Por eso **no hay colisiones por construcción**: no se sortea ni se reintenta.
4. **Cuerpo.** `cuerpo = 10^(d−1) + y`, así el primer dígito nunca es 0.
5. **Dígito verificador.** Algoritmo de **Damm** (cuasigrupo totalmente antisimétrico de orden 10) sobre el cuerpo. La matrícula es `cuerpo ‖ dígito`; es válida si al procesar todos sus dígitos el estado final es 0.
6. **Filtro.** Se descartan matrículas triviales (menos de 3 dígitos distintos, o escaleras como 1234567); el contador simplemente avanza.

La clave `k` (32 bytes aleatorios) se genera al instalar y vive fuera del repo. La matrícula no es un secreto: la clave solo evita que sea predecible. Además la base tiene restricción `UNIQUE` como segunda barrera.

### 4.3 Propiedades verificadas

Probado con `pruebas/test_matricula.py` (22 pruebas):

| Propiedad | Resultado |
|---|---|
| Biyección sobre los 900 000 índices (L = 7) | Completa, sin colisiones |
| Error en un solo dígito | Detectado 100 % |
| Dos dígitos vecinos intercambiados | Detectado 100 % |
| Dos dígitos erróneos, salto o gemelos | Detectado ≈ 90 % |
| Sedes 0–9 con la misma clave | Sin intersección |
| Matrículas triviales | ≈ 0.06 %, descartadas |

Riesgo residual: para que un pago caiga en la cuenta equivocada, el error debe pasar el dígito verificador (≈ 10 % de los errores complejos) **y** coincidir con otra matrícula activa. Con 200 titulares activos eso es 200 / 900 000 ≈ 0.02 %, es decir, cerca de 1 de cada 45 000 errores complejos. La conciliación (§8) además contrasta el importe y el historial del pagador.

### 4.4 Referencia bancaria

La matrícula es la identidad permanente. La **referencia bancaria** se deriva de ella mediante un esquema enchufable:

- `directa` (por defecto): la referencia es la matrícula. Sirve para SPEI y depósitos sin convenio.
- `convenio`: si el negocio contrata cobranza referenciada, el banco puede exigir su propio dígito verificador y longitud. El esquema calcula `matrícula ‖ dígito del banco` sin cambiar la matrícula.

### 4.5 Presentación

Se muestra agrupada (`482 9173`) y se acepta con espacios, guiones o puntos. `nucleo/matricula.py` es la única implementación; nadie más calcula dígitos.

## 5. Modelo de datos

Módulos (apps de Django) y entidades principales:

| Módulo | Entidades | Notas |
|---|---|---|
| `nucleo` | — | Matrícula, dinero, cadena de auditoría. Python puro, sin Django. |
| `configuracion` | Negocio, Parametro, Vocabulario | Un solo negocio por instalación; `sede` y `ranuras`. |
| `cuentas` | Usuario, Rol, PermisoRol, Dispositivo, Delegacion, CodigoUsado, CodigoActivacion | §6. |
| `titulares` | Titular, Familia, Contacto, CampoContacto, Agrupacion, MotivoBaja | Estados: `pendiente`, `activo`, `baja`, `rechazado`. Contacto en §5.2, familias en §5.3. |
| `solicitudes` | Solicitud, PoliticaAccion | Motor genérico de aprobación. |
| `cobros` | ConceptoCobro, ReglaRecargo, PlanCobro, Beca, Prorroga, Cargo, Pago, Aplicacion, Recibo | Libro inmutable. |
| `caja` | Caja, Turno, Arqueo, Traslado | Custodia del efectivo. |
| `banco` | CuentaBancaria, Banco, Importacion, MovimientoBancario, ReglaPagador | Datos de pago en §5.4; adaptadores de entrada en §8. |
| `reportes` | DefinicionCorte, Corte, Destino | Frecuencias y destinos configurables. |
| `auditoria` | Evento | Solo inserción, encadenado por hash. |
| `respaldo` | Respaldo | Bitácora de copias y pruebas de restauración. |

### 5.1 Libro de cobros

- **ConceptoCobro** (categoría): nombre, tipo (`unico`, `recurrente`, `por_evento`), importe por defecto, periodicidad, día de vencimiento, regla de recargo, a quién aplica (`nuevos`, `todos`, `agrupacion`, `manual`), prioridad de aplicación, activo.
- **ReglaRecargo**: fijo o porcentaje, días de gracia, se repite o no, tope.
- **PlanCobro**: liga un concepto recurrente a un titular, con importe propio y vigencia.
- **Cargo**: titular, concepto, periodo, importe, vencimiento, origen (`automatico`, `manual`, `recargo`), estado derivado (`pendiente`, `parcial`, `pagado`, `cancelado`).
- **Pago**: titular, importe, medio (`efectivo`, `banco`, otros configurables), fecha, origen (turno de caja o movimiento bancario), estado (`aplicado`, `revertido`).
- **Aplicacion**: reparte un pago entre cargos. Lo que sobra queda como saldo a favor.
- **Recibo**: folio consecutivo por serie, inalterable, con código de verificación.

Orden de aplicación por defecto (configurable): recargos, luego cargos por vencimiento más antiguo, luego por prioridad del concepto.

Nada se edita ni se borra: una cancelación crea el asiento inverso y deja ambos visibles.

**Reglas de cálculo.** Viven en `nucleo/recargos.py` y `nucleo/reparto.py`, Python puro con sus pruebas; nadie más calcula recargos, becas ni repartos.

- *Generación.* Un concepto recurrente produce un cargo por titular activo con plan vigente y por periodo, el día configurado. Es idempotente por (titular, concepto, periodo). Los conceptos únicos para titulares nuevos se cargan al aprobarse el alta.
- *Recargo.* El primero nace el día siguiente a `máx(vencimiento, prórroga) + días de gracia` si el cargo base sigue con saldo. Si la regla se repite, nace otro cada mes en ese mismo día. Fijo: el importe de la regla. Porcentaje: sobre el saldo pendiente del cargo base en ese momento, redondeado al centavo más cercano. El tope limita la suma de recargos de un mismo cargo. Un recargo nunca genera recargo. Si el equipo estuvo apagado, los recargos atrasados se generan al volver, sin duplicar.
- *Beca.* Se descuenta al generar el cargo; el cargo guarda importe original, descuento e importe final. Nunca baja de cero.
- *Saldo a favor.* No es una cuenta aparte: es la parte de un pago que todavía no se aplica a ningún cargo. Cuando nace un cargo nuevo se le aplica primero el saldo a favor más antiguo del titular o de su familia.
- *Reversos.* Cancelar un cargo, condonar un recargo o revertir un pago crea un asiento de reverso ligado al original, con motivo y autorización. El saldo de un cargo es `importe − cancelado − aplicado por pagos vigentes`.
- *Cargo manual.* Operación lo crea con el importe del concepto; cambiar el importe exige el permiso de ajustes o una solicitud.

**Becas.** Una beca es un descuento **en porcentaje** (de 1 a 100, con hasta dos decimales) sobre un concepto recurrente de un titular, con vigencia y motivo. No hay becas de importe fijo. Se aplica sola al generar cada cargo y queda visible en él. Sustituye al descuento suelto del plan.

**Prórrogas.** Una prórroga mueve la fecha a partir de la cual un cargo genera recargo. No cambia el importe ni borra recargos ya generados.

Becas y prórrogas son acciones del motor de aprobaciones (`beca`, `prorroga`), con el mismo flujo que el alta: Operación las solicita y Supervisión las otorga directamente o aprueba la solicitud por cualquiera de las tres vías. Cada política decide qué permiso aprueba, así que un negocio puede reservar las becas a Dirección.

**Saldo inicial.** Al migrar desde otro control, lo que cada titular debía o tenía a favor entra como un cargo o un pago de tipo `saldo_inicial`, fechado al día de la migración.

### 5.2 Contacto

Cada titular tiene al menos un **Contacto**: nombre, relación con el titular (catálogo configurable; puede ser «el mismo titular»), y los datos que el negocio decida pedir.

- Los **campos de contacto** se definen en configuración: tipo (`telefono`, `correo`, `texto`), etiqueta, si es obligatorio en el alta y si es el medio principal para avisos.
- El teléfono se guarda normalizado (solo dígitos, con el prefijo de país configurado; 10 dígitos nacionales por defecto) y se valida al capturar.
- Un titular puede tener varios contactos; uno se marca como principal y es el que aparece en la ficha y en la cobranza.
- Ver contactos requiere el permiso de ver titulares; editarlos queda en auditoría. Solo los destinos de reporte con detalle `completo` incluyen datos de contacto.

La plantilla «escuela» pide un contacto responsable con **teléfono obligatorio**.

### 5.3 Familias

Una **familia** (nombre configurable; en la plantilla genérica, «cuenta») liga a varios titulares que paga la misma persona.

- Cada titular se da de alta por separado y conserva **su propia matrícula**. La familia no tiene matrícula: es solo el vínculo entre titulares ya existentes.
- Tiene un contacto responsable, compartido por sus miembros, y un **estado de cuenta único** que suma los cargos de todos.
- Reparto de un pago hecho con la matrícula de cualquier miembro: primero a los cargos de ese titular, en el orden de §5.1; lo que sobre pasa solo a los cargos pendientes de los demás miembros, en el mismo orden (recargos, luego vencimiento más antiguo, luego prioridad); y solo si no queda nada pendiente en la familia se guarda como saldo a favor de la familia, que se usa en el siguiente cargo de cualquiera de ellos.
- Un titular pertenece a lo sumo a una familia. Ligar, cambiar o desligar es una acción del motor de aprobaciones (`cambio_familia`), porque cambia a dónde va el dinero que sobra: Supervisión lo hace directo y Operación lo solicita.
- Desligar no mueve pagos ya aplicados; el saldo a favor de la familia se reparte según indique quien aprueba.
- Un titular sin familia funciona exactamente igual que antes.

### 5.4 Datos de pago

Lo que la ficha de pago le dice a quien paga sale de **campos**, no de un texto libre. Cada **CuentaBancaria** del negocio tiene:

| Campo | Regla |
|---|---|
| Banco | Se elige del catálogo de bancos; se propone solo a partir de los tres primeros dígitos de la CLABE |
| CLABE | 18 dígitos; se valida su dígito verificador y que su prefijo corresponda al banco elegido |
| Beneficiario | Nombre del titular de la cuenta tal como lo pide el banco |
| Número de cuenta | Opcional |
| Convenio | Opcional, para cobranza referenciada |
| Medios aceptados | Casillas: transferencia, depósito en ventanilla, efectivo en caja y los que el negocio agregue |
| Dónde va la referencia | Casillas: referencia numérica, concepto o ambos (por defecto ambos) |
| Contacto para dudas | Teléfono o correo |
| Principal | Una sola cuenta aparece en la ficha por defecto |

La ficha arma sola las instrucciones con esos campos y con la matrícula del titular. Un campo opcional de «nota adicional» queda para lo que no quepa en los anteriores.

**Catálogo de bancos.** Viene dentro del programa (`datos/bancos.json`), no se consulta por internet: clave de tres dígitos, nombre y **nivel de soporte** para traer movimientos (`archivo verificado`, `archivo genérico`, `convenio`, `sin probar`). Cualquier banco que reciba SPEI sirve para identificar pagos por matrícula, porque la identificación la hace este sistema; lo que cambia de un banco a otro es el formato del archivo de movimientos. El catálogo se actualiza con cada versión.

### 5.5 Plantilla «escuela»

Viene en `plantillas/escuela.json` y el asistente la carga si se elige:

| Concepto | Tipo | Aplica a | Recargo |
|---|---|---|---|
| Inscripción | único | titulares nuevos | no |
| Examen de ubicación | único / por evento | nuevos o cuando se pida | no |
| Colegiatura | recurrente mensual | todos los activos | sí, tras el día de vencimiento |
| Libros | por evento | manual | no |
| Extras | por evento | manual | no |

Importes, día de vencimiento y recargo se capturan en el asistente; la plantilla no trae cifras.

## 6. Usuarios, roles y aprobaciones

### 6.1 Permisos

Los permisos son átomos fijos en el código; qué rol tiene cuáles se guarda en la base y se edita desde configuración.

| Permiso | Operación (nivel 1) | Supervisión (nivel 2) | Dirección (nivel 3) |
|---|:-:|:-:|:-:|
| Ver titulares y saldos | ✓ | ✓ | ✓ |
| Solicitar alta / baja | ✓ | ✓ | ✓ |
| Alta / baja directa | — | ✓ | ✓ |
| Aprobar solicitudes | — | ✓ | ✓ |
| Otorgar delegaciones | — | ✓ | ✓ |
| Registrar pago en efectivo | ✓ | ✓ | ✓ |
| Abrir y cerrar su turno de caja | ✓ | ✓ | ✓ |
| Cancelar recibo, condonar recargo, descuento | solicita | ✓ | ✓ |
| Cargo manual (libros, extras) | ✓ | ✓ | ✓ |
| Recibir efectivo y revisar arqueos | — | ✓ | ✓ |
| Importar banco y conciliar | sugiere | ✓ | ✓ |
| Administrar conceptos de cobro | — | ✓ | ✓ |
| Corte diario de su propia caja | ✓ | ✓ | ✓ |
| Ver todos los cortes / cerrar el corte mayor | — | ✓ | ✓ |
| Aprobar dispositivos | — | ✓ | ✓ |
| Cambiar nombre de un titular aprobado | solicita | ✓ | ✓ |
| Beca, prórroga, cambio de familia | solicita | ✓ | ✓ |
| Importación inicial del padrón | — | — | ✓ |
| Usuarios, roles, políticas, configuración | — | — | ✓ |
| Auditoría y respaldos | — | — | ✓ |

Los nombres de los roles y esta matriz son los valores por defecto de la plantilla; Dirección puede crear roles y mover permisos.

### 6.2 Tres vías para autorizar sin cuello de botella

Cada acción delicada tiene una **política** (`PoliticaAccion`): quién la ejecuta directo, quién debe solicitarla, quién la aprueba y en cuánto caduca.

1. **Bandeja.** Operación captura todo y envía. Cualquier usuario con permiso de aprobar la resuelve con un clic. Las pendientes se ven en la pantalla de inicio y se resaltan al pasar el plazo configurado.
2. **Delegación temporal.** Supervisión le da a una persona un permiso concreto por un plazo o un número de usos («altas directas durante 7 días»). Caduca sola y cada uso queda registrado.
3. **Código por teléfono.** Si quien aprueba no está frente a una computadora autorizada, dicta el código de 6 dígitos de su app autenticadora (TOTP). Operación lo captura en la solicitud; el sistema lo valida, lo quema (un solo uso) y registra «autorizado por X con código». Quien autorizó ve esas autorizaciones resaltadas en su siguiente inicio de sesión para confirmarlas o reportarlas.

Reglas fijas, no configurables: nadie aprueba su propia solicitud; toda aprobación deja rastro en auditoría; un código no se acepta dos veces.

### 6.3 Alta

1. Operación llena el formulario (datos mínimos, contacto, agrupación, conceptos iniciales).
2. Al guardar se asigna la **matrícula** y el titular queda `pendiente`. Se imprime o envía la **ficha de pago** (matrícula, cuenta del negocio, instrucciones). La familia ya puede pagar.
3. Supervisión aprueba por cualquiera de las tres vías → `activo`. Si rechaza → `rechazado`; la matrícula se retira y cualquier pago recibido se marca para devolver o reasignar.

### 6.4 Baja

Solicitud con motivo (catálogo configurable) → aprobación → `baja`. Se detienen los cargos recurrentes futuros, el adeudo se conserva y la matrícula sigue reconociendo pagos tardíos. Una reactivación conserva la misma matrícula. El borrado real (derecho de cancelación) es una anonimización que solo Dirección ejecuta y solo pasado el plazo de conservación configurado.

### 6.5 Corrección de nombre

Cambiar el nombre o los apellidos de un titular `activo` o en `baja` es una acción del motor de aprobaciones (`correccion_nombre`), con las mismas tres vías y su propia política. Evita que un registro ya aprobado se convierta en otra persona sin que nadie lo vea.

- Mientras el titular está `pendiente`, el nombre se edita libremente: el alta todavía no se aprueba.
- Agrupación, notas y contactos se editan sin aprobación.
- Todo cambio, con o sin aprobación, queda en la bitácora (§10.1).

### 6.6 Cuentas y código de activación

Nadie teclea la contraseña de otra persona.

1. Quien administra usuarios crea la cuenta con nombre, usuario y rol. El sistema genera un **código de activación** de un solo uso, lo muestra una vez y guarda solo su hash. Caduca en el plazo configurado (72 horas por defecto).
2. La persona entra con su usuario y ese código, elige su propia contraseña y, si su rol lo exige, da de alta su autenticador. No requiere aprobación de nadie.
3. **Restablecer acceso** hace lo mismo: invalida la contraseña y las sesiones abiertas y genera un código nuevo.

Los intentos fallidos con un código cuentan para el bloqueo de la cuenta. Quién generó cada código y desde qué equipo se activó queda en la bitácora; si alguien usa un código ajeno, la persona lo nota porque el suyo ya no funciona.

## 7. Efectivo

Objetivo: que Operación cobre sin esperar a nadie y que cada billete tenga dueño en todo momento.

1. **Turno.** Quien cobra abre un turno en su caja. Un turno, una persona.
2. **Cobro.** Registra el pago; el sistema lo aplica al titular de inmediato y emite un recibo foliado. El pago queda como «efectivo en caja».
3. **Arqueo ciego.** Al cerrar, captura lo que contó por denominación **sin ver** lo esperado. El sistema calcula la diferencia. Si supera el umbral configurado, pide una nota y avisa a Supervisión. No bloquea el cierre. Desde la versión 0.16 el arqueo admite un reconteo y lleva piezas por denominación (§15.2).
4. **Traslado.** El efectivo sale de la caja de dos formas:
   - **Entrega** a Supervisión: quien recibe confirma el importe con su propia sesión (doble firma).
   - **Depósito** bancario: se registra con su importe y fecha; la conciliación lo cierra cuando aparece en el banco.
5. **Alertas.** Efectivo que lleva más días de los configurados sin entregar o depositar, depósitos que no aparecen en el banco, cancelaciones de recibos y diferencias repetidas aparecen en el tablero de Supervisión.

Cadena de custodia: `caja → resguardo → banco`. En todo momento el sistema sabe cuánto efectivo debería tener cada persona.

Reglas fijas del efectivo, para cualquier rol:

- **Nadie revierte solo un pago que él mismo cobró.** Aunque tenga permiso de ajustes, su reversión queda como solicitud y la resuelve otra persona.
- **Solo se devuelve efectivo que se tiene.** La devolución de un pago revertido sale del turno abierto de quien la ejecuta, y solo si ese turno tiene cobrado al menos ese importe. La custodia de una persona nunca queda negativa.
- **Un depósito registrado no desaparece de la vista.** Queda «por conciliar» a nombre de quien lo registró, visible en la pantalla de custodia, hasta que aparece en el banco. Si pasa del plazo configurado sin aparecer, es una alerta.

## 8. Banco y conciliación

### 8.1 Entrada de movimientos

Hoy no existe en México una API bancaria abierta y gratuita para leer los movimientos de una cuenta propia. Por eso la entrada es por **adaptadores**:

| Adaptador | Costo | Cómo llega | Estado |
|---|---|---|---|
| `archivo` | Gratis | Se sube el archivo de movimientos de la banca en línea, o se deja en una carpeta vigilada | Fase 3 |
| `estado_pdf` | Gratis | Estado de cuenta en PDF | Fase 3. Formato de Santander PyME documentado en `docs/formatos/` |
| `correo` | Gratis | Avisos de abono leídos del buzón | Posterior, si el banco los envía con concepto |
| `convenio` | De pago | Archivo diario de cobranza referenciada | Posterior |
| `clabe_virtual` | De pago | Una CLABE por titular vía proveedor, por consulta periódica | Posterior |

El adaptador `archivo` no depende de un formato fijo: detecta encabezados y columnas por nombre y contenido (fecha, descripción, referencia, cargo, abono, saldo) y guarda la correspondencia aprendida por cuenta. Subir el archivo es el único paso manual; todo lo demás es automático.

Toda importación debe **cuadrar al centavo** (saldo inicial + depósitos − retiros = saldo final) o se rechaza completa. El sentido de cada movimiento se decide por el saldo, no por la posición de la columna.

Lo que un movimiento trae para identificar a quien paga depende de cómo pagó:

| Forma de pago | Referencia numérica | Concepto | Cuenta y nombre del pagador |
|---|:-:|:-:|:-:|
| SPEI desde otro banco | ✓ | ✓ | ✓ |
| Transferencia desde el mismo banco | — | ✓ | — |
| Depósito en efectivo | — | — | — |

Por eso la ficha pide siempre la matrícula en referencia **y** en concepto, y la matrícula nunca empieza en cero.

Cada movimiento lleva una **huella** (cuenta, fecha, importe, referencia, descripción normalizada y ordinal dentro del día) para que reimportar el mismo archivo no duplique nada.

### 8.2 Identificación

Para cada abono:

Las reglas viven en `nucleo/identificacion.py`, Python puro con sus pruebas.

1. **Extraer.** Se buscan en referencia y concepto todas las secuencias de `L` dígitos (también partidas por espacios o guiones) que pasen el dígito verificador.
2. **Decidir.**
   - Una sola matrícula válida y existente, escrita **aislada** (no pegada a otros dígitos) → **aplicación automática**. Si viene incrustada en un número más largo, solo se sugiere.
   - Si esa matrícula contradice a un pagador ya conocido y confiable, tampoco se aplica sola.
   - Ninguna válida → se buscan matrículas existentes a un error de distancia (dígito cambiado, faltante, sobrante o intercambiado) y se ordenan por coincidencia de importe con lo que debe el titular y por historial del pagador. Va a la cola «por identificar» como sugerencia.
   - Varias válidas o ninguna pista → cola «por identificar» sin sugerencia.
3. **Aprender.** Cuando una persona confirma a quién pertenece un abono, se guarda una `ReglaPagador` (CLABE del pagador → titular o familia). Tras el número de confirmaciones configurado, los siguientes abonos de ese pagador se sugieren en primer lugar; solo se aplican solos si la política lo permite.
4. **Aplicar.** El pago se reparte según §5.1.

Operación puede sugerir la identificación; Supervisión la confirma. Los depósitos de efectivo de §7 se emparejan contra los traslados registrados (mismo importe y fecha cercana), no contra titulares; el que no empareja va a la cola.

Otras reglas de la importación:

- El archivo debe ser de una cuenta bancaria registrada del negocio (misma CLABE); si no, se rechaza.
- Un movimiento nunca produce dos pagos: la huella es única y la aplicación va dentro de la misma transacción.
- Un mismo movimiento real que llega por dos vías (primero en un archivo descargado durante el mes y después en el estado de cuenta oficial) es **un solo movimiento**: el segundo se reconoce por cuenta, fecha, importe y clave de rastreo (o, si no hay clave de rastreo, por referencia y concepto), se liga al primero como «confirmado por el estado oficial» y nunca produce otro pago.
- De quien paga se guarda lo necesario para identificarlo (banco, CLABE, nombre, clave de rastreo, referencia y concepto). El RFC no se guarda.
- Operación ve fecha, importe, referencia, concepto y nombre del pagador; la CLABE completa solo la ve quien concilia.
- Deshacer una aplicación bancaria es una reversión de pago por el motor de aprobaciones; el movimiento vuelve a la cola.

**Continuidad y revisión de importaciones.** Quien puede importar podría subir un archivo fabricado para acreditar pagos que no existieron. El sistema no puede comprobar un archivo contra el banco, así que lo acota de tres formas:

- *Continuidad.* Un estado de cuenta en PDF cuyo periodo empieza al día siguiente del último estado importado de esa cuenta debe abrir con el saldo con que aquel cerró; si no, se rechaza completo. Cada importación queda clasificada: `verificada` (encadena con la anterior), `primera`, `con_hueco` (hay días sin importar entre ambas) o `no_verificable` (archivo genérico de Excel o CSV, que cualquiera puede editar).
- *Revisión por otra persona.* Toda importación `con_hueco` o `no_verificable` que haya aplicado pagos aparece como pendiente en el inicio de quien puede ver la bitácora, hasta que alguien distinto de quien la importó la marca como revisada. Marcarla queda en la bitácora.
- *Cruce con el estado oficial.* El corte mayor (Fase 4) compara lo aplicado por banco contra el estado de cuenta en PDF del mes.

Riesgo que queda: dos personas de acuerdo, una que importa y otra que revisa, pueden acreditar un pago inexistente; lo delata el cruce con el estado oficial.

## 9. Cortes y reportes

Un **corte** es una definición configurable: nombre, tipo, frecuencia, quién lo cierra, si cierra periodo y a qué destinos va, con qué nivel de detalle. La plantilla «escuela» trae tres.

| Corte | Cuándo | Quién | Cierra periodo | Contenido |
|---|---|---|---|---|
| Diario de caja | Cada día, antes de la hora límite (18:00 por defecto) | Operación, al cerrar su turno | No | Solo su caja: recibos del día uno por uno, devoluciones, total cobrado, lo contado, la diferencia y los traslados |
| Mayor | Mensual | Supervisión | Sí | Ingresos por medio y concepto, una fila por titular con el estado de cada concepto, antigüedad de saldos, altas y bajas, caja y banco |
| Lista de cobranza | Semanal y a demanda | Automático | No | Adeudos vencidos, uno por renglón |

### 9.1 Corte diario de caja

- Es el cierre del turno: primero el arqueo ciego, después se genera el corte. Así el corte nunca revela lo esperado antes de contar.
- Cada persona ve solo el suyo; Supervisión y Dirección ven todos. No incluye ingresos por banco ni lo cobrado por otras personas.
- Si a la hora límite hay un turno con cobros del día sin cerrar, Supervisión ve una alerta. No se bloquea nada: quien cobra puede cerrarlo después y el corte queda marcado como **tardío**.
- Un día sin cobros en efectivo no genera corte.

### 9.2 Corte mayor

- El sistema lo genera solo el día configurado del mes siguiente y lo deja como borrador. Supervisión lo revisa y lo cierra con un clic. Si nadie lo cierra en el plazo configurado, se entrega marcado «sin revisar».
- Contenido:
  - ingresos por medio de pago y por concepto;
  - una fila por titular con el estado de cada concepto (pagado, parcial, adeudo), becas y prórrogas;
  - cartera vencida por antigüedad; altas y bajas;
  - **caja:** efectivo cobrado frente a efectivo en custodia y depositado, diferencias de arqueo, depósitos sin conciliar;
  - **banco:** lo aplicado por banco frente al estado de cuenta oficial del mes; pagos que vinieron de importaciones no verificables y que no aparecen en el estado oficial; importaciones pendientes de revisión; movimientos por identificar;
  - reversos, cancelaciones y condonaciones del mes, con quién los autorizó.
- **Un corte cerrado es una fotografía.** Sus archivos y sus cifras se guardan tal como quedaron, con su hash; nada posterior los recalcula.
- **Cómo se cuenta.** Cada asiento tiene una fecha contable (el pago, cuando se registró; el cargo, cuando nació; el reverso, cuando se hizo). El corte incluye los asientos cuya fecha contable cae en el periodo. *Ingresos* son los pagos vigentes del periodo por medio de pago y, por concepto, sus aplicaciones. *Esperado* es el importe final, menos cancelaciones, de los cargos que vencen en el periodo; *cobrado de lo esperado*, lo aplicado a esos cargos hasta el día del corte. *Cartera vencida* son los saldos de cargos vencidos al día del corte, en tramos de 1 a 30, 31 a 60, 61 a 90 y más de 90 días.
- **Cierre de periodo.** Al cerrarlo, el mes queda bloqueado: ningún cargo, pago ni reverso puede fecharse dentro de él. Lo que llegue después (un pago bancario tardío, la corrección de un error) se registra con fecha del periodo abierto y conserva como referencia la fecha original.

### 9.3 Lista de cobranza

Los adeudos vencidos a la fecha, uno por renglón, con lo necesario para que una persona o un agente externo avise a quien debe: titular o familia, concepto, importe, vencimiento, días de atraso y, según el nivel de detalle del destino, matrícula y contacto. El encabezado lleva los datos de pago del negocio (§5.4). El sistema no envía mensajes: entrega la lista.

### 9.4 Destinos y entrega

- **Destinos** enchufables: `carpeta` y, más adelante, `correo`. Cada combinación de corte y destino define su nivel de detalle: `completo` (nombre, matrícula y contacto), `solo_nombres` (nombre, sin matrícula ni contacto) o `sin_nombres` (solo matrícula).
- **Carpeta.** La ruta se elige en el asistente y se puede cambiar después; el sistema comprueba que puede escribir en ella. Cada entrega deja PDF, CSV y JSON con nombres fijos por tipo y fecha, escritos de forma atómica, y actualiza un `manifiesto.json` con la lista de archivos, su hash, una firma con la clave de la instalación y el ancla de la bitácora (§10.1). Los nombres de archivo los genera el sistema; nada que escriba un usuario llega a una ruta.
- **Reintento.** Si la carpeta no está disponible, la entrega queda pendiente y el trabajador la reintenta; no detiene el corte.
- Todo corte incluye en su JSON las cifras que un análisis externo necesita sin recalcularlas: esperado y cobrado por concepto, cartera vencida por antigüedad, altas y bajas. El sistema no trae tablero de indicadores propio.

### 9.5 Estado de cuenta

Por titular o por familia, en PDF: cargos, pagos, becas, prórrogas y saldo a una fecha, con los datos de pago de §5.4. Lo genera quien puede ver titulares; cada emisión queda en la bitácora.

## 10. Seguridad

| Capa | Medida |
|---|---|
| Red | El servicio escucha solo en la red local; regla de firewall limitada a esa subred; TLS con un certificado único del servidor, sin autoridad de certificados, que se instala en cada computadora autorizada (§11). |
| Dispositivos | Solo entran **computadoras aprobadas**. Un navegador nuevo queda «pendiente» hasta que Supervisión o Dirección lo aprueba; recibe una credencial de dispositivo de larga duración (cookie `HttpOnly`, `Secure`, `SameSite=Strict`; en la base solo su hash). Se puede revocar. La primera se aprueba desde el propio servidor al instalar. |
| Identidad | Una cuenta por persona, activada con código de un solo uso (§6.6). Nadie otorga ni modifica lo que excede sus propios permisos. Argon2id. Bloqueo progresivo tras intentos fallidos. Cierre por inactividad configurable por rol. TOTP obligatorio para quien aprueba. Reingreso de contraseña antes de acciones delicadas. |
| Aplicación | Permiso verificado en el servidor en cada vista y sobre cada objeto. CSRF activo. CSP sin scripts en línea ni orígenes externos. Solo ORM. Límite de peticiones en inicio de sesión y códigos. |
| Archivos | Los archivos subidos se leen, nunca se ejecutan; tamaño y tipo limitados; se guardan fuera de la carpeta pública. Las exportaciones neutralizan celdas que empiezan con `=`, `+`, `-`, `@`. |
| Integridad | Libro inmutable. Bitácora sellada con clave y anclada fuera de la base (§10.1). Periodos cerrados bloqueados. |
| Secretos | Carpeta `instancia/` fuera del repo, con permisos restringidos a la cuenta del servicio: clave de Django, clave de matrícula, clave de respaldo. |
| Respaldo | Copia diaria cifrada hacia una carpeta sincronizada fuera del equipo, con prueba de restauración mensual (§10.2). |
| Secretos en la base | El secreto del autenticador de cada usuario se guarda cifrado con una clave de la instalación; una copia suelta de la base no lo revela. |
| Privacidad | Datos mínimos; vistas limitadas por rol; toda exportación queda registrada; aviso de privacidad y consentimiento del tutor fuera del sistema, con casilla de constancia en el alta. |

### 10.1 Bitácora

**Qué se graba.** Toda alta, edición y cambio de estado de titulares y contactos, y todo cambio de agrupaciones, conceptos, planes, usuarios, roles, políticas y configuración. Cada evento guarda: momento, **usuario que lo hizo**, equipo, acción, y el valor **anterior y nuevo** de cada dato cambiado. También inicios de sesión, aprobaciones, códigos y accesos denegados.

**Dónde se ve.**
- **Historial del titular:** en la ficha de cada titular, una lista en lenguaje llano de quién cambió qué y cuándo, incluidos sus contactos y solicitudes. Lo ve quien puede ver titulares.
- **Bitácora general:** todos los eventos, con filtros. Solo Dirección.

**Cómo se protege.**
- Solo inserción y numeración consecutiva sin huecos.
- **Sello con clave:** `sello = HMAC-SHA256(clave_auditoria, sello anterior ‖ contenido)`. La clave vive en `instancia/`, fuera de la base; sin ella no se pueden recalcular los sellos tras alterar un evento.
- **Ancla externa:** tras cada evento confirmado se escribe en `instancia/` el número y el sello del último evento, firmados. Si se borran los eventos finales o se restaura una copia vieja de la base, la verificación lo detecta porque la base queda por detrás del ancla.
- **Verificación:** a demanda y por tarea diaria; un fallo aparece como alerta en el inicio de Dirección. A partir de la Fase 4 el ancla viaja también en cada corte y en cada respaldo, de modo que existe fuera del equipo.

### 10.2 Respaldo y restauración

- **Qué se respalda.** Una copia consistente de la base (tomada con el mecanismo de respaldo de SQLite, no copiando el archivo en uso) más las claves de la instalación y el ancla de la bitácora, en un solo paquete.
- **Cifrado.** AES-256-GCM con una **clave de recuperación** aleatoria generada al instalar. Se muestra una sola vez para imprimirla y guardarla fuera del equipo; sin ella un respaldo no se puede abrir. El paquete cifrado se verifica solo: cualquier alteración se detecta al abrirlo.
- **Destino.** Una carpeta elegida en el asistente, pensada para una carpeta sincronizada con la nube. El sistema comprueba que puede escribir en ella.
- **Cuándo.** Una vez al día a la hora configurada, y siempre antes de actualizar el programa.
- **Retención.** 30 diarios y 12 mensuales; lo demás se borra.
- **Prueba de restauración.** Una vez al mes el sistema abre el último respaldo en una carpeta temporal, verifica la integridad de la base y de la bitácora, compara conteos y borra la copia. Un fallo es una alerta para Dirección.
- **Alerta.** Si el último respaldo correcto tiene más de 48 horas, Dirección lo ve en su inicio.
- **Restaurar.** Un comando (y una opción del instalador en un equipo nuevo) toma el archivo de respaldo y la clave de recuperación y deja la instalación como estaba.

Pruebas de seguridad previstas antes de cada entrega: matriz completa URL × rol, acceso a objetos ajenos, CSRF, fijación de sesión, fuerza bruta, autoaprobación, reutilización de código, delegación vencida, manipulación del libro, archivos maliciosos, inyección en exportaciones y concurrencia en contador de matrícula, folios e importaciones.

## 11. Configuración e instalación

- **Asistente de primer uso:** nombre del negocio, vocabulario (cómo se llama al titular, a la matrícula, a las agrupaciones), plantilla, conceptos e importes, roles, políticas de aprobación, cajas, datos de pago, cortes y destinos, respaldo. Crea al primer usuario de Dirección y aprueba el primer dispositivo.
- **Moneda.** El asistente pregunta la moneda del negocio (por defecto MXN) de un catálogo incluido con código, símbolo y decimales. Todo importe se captura y se muestra con su símbolo y su código. La moneda no se puede cambiar una vez que existe el primer cargo o pago. Las denominaciones de caja incluidas son las de MXN; para otra moneda se capturan en el catálogo.
- **Captura guiada.** Cada campo solo deja teclear lo que acepta y hasta el largo que acepta: dígitos en CLABE, teléfono, matrícula y códigos; importes con el símbolo de la moneda ya puesto; porcentajes con el signo `%` ya puesto. Es una ayuda de pantalla: el servidor valida igual todo lo que recibe.
- **Autenticador.** Las pantallas que lo piden explican qué es y nombran aplicaciones gratuitas que sirven (Google Authenticator, Microsoft Authenticator, Authy, 2FAS, entre otras): cualquier aplicación de códigos de 6 dígitos estándar funciona.
- **Plantillas.** Una plantilla es la configuración completa sin datos: vocabulario, conceptos, recargos, roles y permisos, políticas, campos de contacto, cortes. El asistente ofrece:
  - `generico`: pensada para servir tal cual a la mayoría de los negocios que cobran a clientes recurrentes;
  - `escuela`;
  - **importar** un archivo de plantilla;
  - partir de cualquiera y **personalizar** cada parte antes de terminar.

  Desde configuración, Dirección puede **guardar la configuración actual como plantilla** (un archivo) para usarla en otra sede o compartirla. Una plantilla importada se trata como dato no confiable: se valida contra un esquema y nunca contiene código, usuarios, claves ni datos de titulares.
- **Todo editable después** por quien tenga el permiso: Supervisión administra conceptos de cobro; Dirección lo demás.
- **Importación inicial.** Para empezar con un padrón existente, Dirección sube un Excel o CSV. El sistema no exige un formato: propone qué columna es cada dato (nombre, apellidos, agrupación, responsable, teléfono, saldo por concepto), deja corregir la correspondencia, muestra una vista previa con los errores renglón por renglón y no escribe nada hasta confirmar. Al confirmar crea titulares activos con su matrícula, sus contactos, sus vínculos de familia (renglones con el mismo responsable y teléfono se proponen como familia; cada titular recibe su propia matrícula) y su saldo inicial. Detecta duplicados si se repite. Entrega la lista de matrículas asignadas y las fichas de pago para repartir. Todo queda en la bitácora.
- **Repo sin datos:** `instancia/`, bases, respaldos y documentos internos están en `.gitignore`. Descargar el repo da el motor, las plantillas y el asistente, nada más.
- **Instalación en Windows:** un **instalador `.exe`** («Ariasmos») que trae todo incluido (no hay que instalar Python).
  - Programa en `C:\Program Files\Ariasmos`; datos (base, claves, registros, certificados) en `C:\ProgramData\Ariasmos`, con permisos solo para la cuenta del servicio y los administradores.
  - Tres servicios de Windows con arranque automático y reinicio ante fallas: web (escucha solo en el propio equipo), trabajador y TLS (proxy que atiende a la red local por HTTPS).
  - **Certificado del servidor.** Al instalar se genera un certificado único para este servidor, válido 10 años, que solo sirve para su nombre de equipo y para `localhost`. No hay autoridad de certificados: con ese certificado no se puede emitir ninguno más, de modo que quien lo robara solo podría suplantar a este servidor y a ningún otro sitio. Al actualizar se conserva; solo se genera otro si cambia el nombre del equipo o está por vencer, y entonces hay que volver a instalarlo en las demás computadoras. La aplicación avisa 60 días antes del vencimiento y muestra su huella para comprobarla al instalarlo.
  - Regla de firewall que abre el puerto HTTPS solo a la red local.
  - Al terminar genera las claves, muestra el token del asistente y abre el asistente en el navegador.
  - Actualizar con un instalador nuevo detiene los servicios, hace un respaldo, reemplaza el programa, migra la base y los arranca. Desinstalar conserva los datos salvo que se pida borrarlos.
  - Las demás computadoras no instalan el programa: entran por el navegador, después de instalar una sola vez el certificado del servidor, que el sistema ofrece junto con sus instrucciones.
  - El instalador se compila de forma automática en el repo, con una prueba de instalación y arranque, y queda como archivo de la compilación junto con su hash; no se publica como versión.

## 12. Estructura del repo

```
nucleo/            matrícula, dinero, cadena de hash (Python puro)
sistema/           proyecto Django y sus apps (§5)
plantillas/        escuela.json, generico.json
pruebas/           pytest
instalacion/       scripts de Windows, Caddyfile de ejemplo
docs/              esta arquitectura, guía de instalación, guía de uso
instancia/         (ignorada) claves, base, configuración local
```

## 13. Fases

| Fase | Entrega |
|---|---|
| 1 | Proyecto base, matrícula, usuarios, roles, dispositivos, titulares, solicitudes con las tres vías, conceptos de cobro, asistente, auditoría |
| 1b | Datos de pago por campos, catálogo de bancos, plantillas propias |
| 2 | Familias, cargos automáticos, recargos, becas y prórrogas, pagos en efectivo, recibos, caja y traslados |
| 3 | Estado de cuenta en PDF, importación inicial desde Excel, importación bancaria, identificación y conciliación |
| 4a | Cortes (diario, mayor, lista de cobranza), destinos, cierre de periodo, respaldo y cifrado de secretos |
| 4b | Instalador `.exe`, HTTPS en la red local, compilación automática y guías |
| 5a | Calendario de cortes, piezas por denominación, retiros de caja, QR en recibos, carpeta vigilada del banco (§15) |
| 5b | Interfaz nueva: marca Ariasmos y marca del negocio, pantallas rediseñadas, transiciones |

## 14. Pendientes de decisión

1. Formato real del archivo de movimientos del banco: hace falta una muestra para afinar el adaptador.
2. Si el negocio contrata cobranza referenciada: longitud y dígito verificador que exija el banco.
3. Facturación (CFDI): en investigación; se diseña cuando se conozcan requisitos y costos.
6. Inventario opcional por negocio: en definición.
7. Avisos de abono del banco por correo como «depósito por confirmar»: se diseña cuando exista una muestra real del aviso.
8. Reflejo de transferencias en minutos sin intervención (proveedor de cobranza SPEI u otra vía): por evaluar con costos.
4. Varias sedes: hoy una instalación por sede con `sede` distinta; la consolidación central se diseña cuando exista la segunda.
5. El programa es propietario: sin licencia de código abierto, el instalador se publica sin firma digital salvo que se compre un certificado.

## 15. Versión 0.16: cambios de motor de la fase 5a

Donde este apartado contradiga a uno anterior, manda este. Nada de aquí cambia `nucleo/`.

### 15.1 Calendario de cortes de caja

- Cada negocio decide **qué días de la semana** hay corte de caja y **la hora límite de cada día**. Parámetro `calendario_corte`: un mapa de día de la semana (0 = lunes … 6 = domingo) a `HH:MM`; un día ausente no pide corte. Sustituye a `hora_limite_corte_diario`.
- Migración: el valor anterior se copia a los siete días, para no cambiar el comportamiento de una instalación existente. El asistente propone lunes a sábado.
- Un turno abierto en un día con corte debe cerrarse antes de la hora límite de ese día; si se abrió en un día sin corte, antes de la hora límite del siguiente día que sí tenga. Con esa regla se calculan `tardío` y la alerta «corte diario pendiente».
- Validación: horas `HH:MM` reales; al menos un día con corte si el negocio usa caja; se guarda con su evento de bitácora (valor anterior y nuevo).

### 15.2 Piezas por denominación y arqueo con reconteo

Objetivo: saber cuántas piezas de cada denominación debe haber en la caja sin perder el arqueo ciego.

- Parámetro del negocio `control_denominaciones` (sí/no). Apagado, todo sigue como en §7.
- Encendido:
  - **Apertura.** El fondo inicial se captura por denominación; la suma es el fondo.
  - **Cobro en efectivo.** Además del importe se capturan las piezas **recibidas** (su suma debe ser mayor o igual al importe). El cambio es la diferencia. El sistema **propone las piezas del cambio** con las que la caja debería tener (cambio con existencias acotadas; si no hay combinación exacta lo dice) y pide entregar exactamente esas. Si la persona entrega otras, las corrige en pantalla antes de confirmar: la suma del cambio capturado debe ser exactamente el cambio. No se bloquea un cobro por existencias: la realidad manda y el desajuste aparece en el corte.
  - **Retiros, devoluciones y traslados** que salen de la caja capturan sus piezas igual.
  - Cada movimiento de piezas es un renglón inmutable (`MovimientoPiezas`: turno, origen, denominación, piezas con signo, referencia al pago, retiro o traslado). Una reversión agrega renglones contrarios; nada se edita.
- **Arqueo.** El conteo sigue siendo ciego. Antes de que el conteo quede cerrado, **ninguna respuesta del servidor** (página, fragmento, mensaje de error, PDF, corte, exportación) revela el total esperado del turno ni las piezas esperadas a quien lo tiene abierto.
  1. La persona captura su conteo. Se guarda como «primer conteo» y ya no se puede editar.
  2. Si coincide con lo esperado, el turno se cierra.
  3. Si no coincide, el sistema solo dice **que no coincide**, sin importe ni sentido, y ofrece **un único reconteo** o cerrar con el primer conteo.
  4. Con el reconteo (o al cerrar sin él) el turno queda cerrado y **entonces** se muestra: esperado, contado y diferencia, en total y por denominación. Ambos conteos quedan en el arqueo y en la bitácora.
- Las piezas son una guía: el umbral, la nota obligatoria y las alertas se siguen calculando con el **total**.

### 15.3 Retiros de caja

Sacar efectivo de la caja para un gasto del negocio. Operación los hace sin esperar a nadie mientras respete los topes; Supervisión los controla después.

- **Datos:** folio propio (serie de retiros), turno, importe, motivo (catálogo `MotivoRetiro` que administra Supervisión), nota, piezas si §15.2 está encendido, y **comprobante** (foto o PDF del ticket o recibo).
- **Topes**, definidos en el asistente y editables por Dirección: importe máximo por retiro; periodo de conteo (`dia` o `semana`, de lunes a domingo, en la zona horaria del negocio); importe máximo del periodo; número máximo de retiros del periodo; efectivo máximo en caja (solo aviso para entregar). Los topes se cuentan **por caja**.
- **Dentro de los topes** el retiro se registra de inmediato. **Fuera de ellos** se convierte en una solicitud (`retiro_caja`) que usa el motor de aprobaciones con sus tres vías; valen las reglas fijas: nadie aprueba su propia solicitud.
- La comprobación de topes y el registro ocurren en la misma transacción (`BEGIN IMMEDIATE`): dos retiros simultáneos no pueden rebasar juntos un tope.
- **Solo se retira efectivo que el turno tiene** (la custodia nunca queda negativa). El rechazo por este motivo no dice cuánto hay. Cada rechazo queda en bitácora; al tercero en un mismo turno, los retiros de ese turno pasan a requerir autorización, para que no sirvan de sonda del total esperado.
- **Comprobante.**
  - Se puede adjuntar al registrar o después («pendiente»). Un turno con comprobantes pendientes **no se puede cerrar** hasta adjuntarlos o declarar cada uno «sin comprobante» con su motivo; esa declaración avisa a Supervisión.
  - Solo JPEG, PNG o PDF, hasta 5 MB. El tipo se decide por el contenido, no por el nombre ni por lo que diga el navegador. Las imágenes se vuelven a codificar (se pierden metadatos como la ubicación). Un PDF con contenido activo (JavaScript, acciones de lanzamiento, archivos incrustados) o cifrado se rechaza.
  - Se guarda fuera de cualquier carpeta que el servidor sirva, con nombre aleatorio, y su SHA-256 queda en el retiro y en la bitácora. Se entrega solo por una vista con sesión y permiso, como descarga (`Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox`). Entra en los respaldos cifrados.
  - Lo ven quien lo registró, Supervisión y Dirección.
- **Revisión.** Cada retiro nace «por revisar». Quien tenga el permiso `revisar_retiros` lo marca «revisado» u «observado» con nota; **nadie revisa un retiro propio**. Avisos en el tablero de Supervisión: periodo al 80 % de un tope, retiro sin comprobante, retiros por revisar con más días de los configurados.
- **Sin borrado.** Un retiro solo se revierte por solicitud aprobada por otra persona; la reversión regresa el efectivo al turno abierto de quien la ejecuta.
- Entra en el esperado del arqueo, en el corte diario y el corte mayor (como salida de efectivo con folio, motivo e importe) y en la bitácora.
- Permisos nuevos: `retirar_efectivo` (Operación), `revisar_retiros` (Supervisión), `administrar_motivos_retiro` (Supervisión).

### 15.4 Recibos con QR

- El recibo (pantalla, impresión y PDF) lleva un QR además del código. El QR contiene **solo** el texto `AR1|<serie>|<folio>|<código>`: ni nombre, ni matrícula, ni importe, ni una dirección web.
- La pantalla «Verificar recibo» acepta el código tecleado o el texto del QR (un lector USB lo escribe como teclado). Busca por serie y folio, compara el código en tiempo constante y comprueba el recibo contra el libro; responde válido, cancelado o no reconocido.
- La verificación exige sesión, equipo aprobado y permiso de ver titulares. Los intentos fallidos se limitan por usuario y por equipo y quedan en bitácora.
- El código no cambia: sigue derivándose con HMAC de serie, folio, importe, fecha y titular.

### 15.5 Carpeta vigilada del banco

- Parámetro `carpeta_banco`: una carpeta donde alguien deja el archivo descargado del banco. El trabajador la revisa cada pocos minutos e importa lo nuevo con el **mismo camino y las mismas defensas** que una importación manual (continuidad con el estado anterior, revisión de importaciones, un movimiento que llega por dos vías cuenta una vez).
- Quien importa es el actor de sistema «carpeta vigilada». Como nadie responde por ese archivo, una importación de la carpeta que no se pueda encadenar con un estado anterior **no aplica pagos** hasta que la revise una persona con permiso de conciliación.
- Solo se toman archivos regulares (sin seguir enlaces), con extensión admitida por algún adaptador, hasta el tamaño máximo de importación y cuyo tamaño no cambió entre dos revisiones. Un archivo ya visto (por SHA-256) no se vuelve a importar.
- Lo importado se mueve a `procesados/` y lo rechazado a `rechazados/` con un archivo de texto que dice por qué. La carpeta no puede estar dentro del programa ni de sus datos.
- Cada importación automática queda en bitácora y aparece en el inicio de quien concilia.

### 15.6 Asistente

Ocho pasos. El nuevo paso 5, «Caja: cortes y retiros», pide el calendario de cortes (§15.1), si se capturan piezas por denominación (§15.2) y los topes de retiros (§15.3). El paso 6, «Entrega y respaldo», conserva las carpetas, los niveles de detalle y la clave de recuperación, y agrega la carpeta vigilada del banco (§15.5). Las plantillas y su esquema incluyen los valores nuevos.

