# Arquitectura — Sistema de cobro y control de titulares

Versión 0.23 · 18/11/2026 · Estado: fases 1 a 11 construidas (0.10.0); fase 6b (facturación, §17) diseñada.

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
| Local primero | Todo funciona sin internet. Internet solo se usa para respaldo y, si se configura, correo, facturación (§17) y búsqueda de actualizaciones (§20). |
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
| 5b | Interfaz nueva según `docs/DISENO.md`: marca Ariasmos y marca del negocio configurable, todas las pantallas con el nuevo sistema de diseño, splash y transiciones |
| 6a | Carpeta del banco que aplica de inmediato salvo sospecha (§15.5); inventario opcional, venta a titular o sin matrícula, devoluciones y conteo mensual (§16) |
| 6b | Facturación electrónica opcional con proveedor intercambiable (§17) |
| 7a | Topes del banco por día y acumulado, configurables por quien concilia y por Dirección (§19); actualizaciones del programa: buscar, avisar y descargar con firma (§20) |
| 8a | Programa de escritorio: `Ariasmos.exe` con ventana propia en la computadora principal y en las adicionales (§21) |
| 8b | Nada fijo de un negocio: vocabulario completo, reportes, banco, reglas configurables y cobros semanales y quincenales (§22) |
| 9a | Configurador y caja más cómodos: zona horaria en lista, signo según el tipo, apertura de turno con piezas, orden en los buscadores, pantallas de caja como el diseño aprobado (§23) |
| 9b | Tarifas y cargos por agrupación, recargos tras el alta, límites de adeudo y rezagados con reglas propias (§24) |
| 10 | Conteo de piezas de fábrica en todo movimiento de efectivo, formularios que se adaptan a lo elegido, botones a prueba de clics repetidos y cobrar con la lista a la vista (§25.1 a §25.4 y §25.6). Las pantallas que se actualizan solas (§25.5) quedan diseñadas para la fase de transferencias |
| 11 | Interfaz interactiva aprobada sobre la interfaz actual: buscar o ir a, cobrar en una sola pantalla, inicio vivo, ficha, banco y configuración, textos llanos (§26) y pantallas que se actualizan solas (§25.5) |

## 14. Pendientes de decisión

1. Formato real del archivo de movimientos del banco: hace falta una muestra para afinar el adaptador.
2. Si el negocio contrata cobranza referenciada: longitud y dígito verificador que exija el banco.
3. Facturación (CFDI): diseñada en §17; falta elegir proveedor de timbrado y las decisiones fiscales del contador de cada negocio.
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
- **Topes**, definidos en el asistente y editables por Dirección: importe máximo por retiro; periodo de conteo (`dia` o `semana`, de lunes a domingo, en la zona horaria del negocio); importe máximo del periodo; número máximo de retiros del periodo; efectivo máximo en caja (solo aviso para entregar). Los topes se cuentan **por caja y por persona** (lo que resulte mayor): cambiar de caja no da topes nuevos.
- **Dentro de los topes** el retiro se registra de inmediato. **Fuera de ellos** se convierte en una solicitud (`retiro_caja`) que usa el motor de aprobaciones con sus tres vías; valen las reglas fijas: nadie aprueba su propia solicitud.
- La comprobación de topes y el registro ocurren en la misma transacción (`BEGIN IMMEDIATE`): dos retiros simultáneos no pueden rebasar juntos un tope.
- **Solo se retira efectivo que el turno tiene** (la custodia nunca queda negativa). El rechazo por este motivo no dice cuánto hay. Cada rechazo queda en bitácora; al tercero en un mismo turno, los retiros de ese turno pasan a requerir autorización, para que no sirvan de sonda del total esperado.
- **Comprobante.**
  - Se puede adjuntar al registrar o después («pendiente»). Un turno con comprobantes pendientes **no se puede cerrar** hasta adjuntarlos o declarar cada uno «sin comprobante» con su motivo; esa declaración avisa a Supervisión.
  - Solo JPEG, PNG o PDF, hasta 5 MB. El tipo se decide por el contenido, no por el nombre ni por lo que diga el navegador. Las imágenes se reconstruyen solo con sus píxeles (se pierden ubicación, comentarios, perfiles y cualquier otro metadato). Un PDF con contenido activo (JavaScript, acciones de lanzamiento, archivos incrustados) o cifrado se rechaza.
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
- Quien importa es el actor de sistema «carpeta vigilada».
- Solo se toman archivos regulares (sin seguir enlaces), con extensión admitida por algún adaptador, hasta el tamaño máximo de importación y cuyo tamaño no cambió entre dos revisiones. Un archivo ya visto (por SHA-256) no se vuelve a importar.
- Lo importado se mueve a `procesados/` y lo rechazado a `rechazados/` con un archivo de texto que dice por qué. La carpeta no puede estar dentro del programa ni de sus datos. Tampoco puede ser la carpeta de respaldo ni una de entrega de cortes, ni contenerlas o estar dentro de ellas.
- `procesados/` y `rechazados/` deben ser carpetas normales: si alguna es un enlace, la revisión se detiene sin mover nada y queda un aviso en bitácora, para que el servicio nunca escriba fuera de la carpeta vigilada.
- Cada importación automática queda en bitácora y aparece en el inicio de quien concilia.

**Qué se aplica solo y qué se retiene.** El objetivo es que el pago se refleje en cuanto llega el archivo, sin perder el control cuando algo se ve raro.

- Un **estado en PDF que continúa al anterior** aplica sus pagos de inmediato. Si no se puede encadenar, queda retenido completo.
- Un **archivo editable** (Excel o CSV de movimientos del día) no se puede comprobar por sí mismo. Sus movimientos identificados se **aplican de inmediato**, salvo los que tengan una señal de sospecha, que quedan **retenidos uno por uno** con su motivo hasta que los libere quien concilia. Lo ya aplicado se comprueba después contra el estado mensual.
- **Señales por movimiento** (retienen ese movimiento):
  1. El importe es mayor que el adeudo vigente de la familia del titular (dejaría saldo a favor).
  2. El importe pasa de `tope_pago_carpeta` (0 = sin tope individual).
  3. La fecha es futura, o cae en un periodo que ya cubre un estado en PDF importado y el movimiento no está en ese estado.
  4. El titular no está activo.
  5. La misma matrícula ya recibió otro pago en el mismo archivo.
- **Señales del archivo** (retienen todos sus movimientos):
  1. Trae columna de saldo y los saldos no cuadran renglón a renglón con los importes.
  2. Trae columna de saldo y no continúa el último saldo conocido de esa cuenta.
  3. **Tope acumulado** (§19): con los pagos de este archivo se rebasaría `tope_aplicado_sin_respaldo`. En 0 (valor inicial) todo archivo editable queda retenido.
- **Liberar.** Quien concilia libera un movimiento, varios o todos los retenidos de una importación; queda en bitácora con su nombre. Quien libera no puede marcar la importación como revisada.
- **Comprobación contra el estado.** Al importar un estado en PDF, cada pago aplicado desde un archivo editable con fecha dentro de ese periodo debe corresponder a un movimiento del estado. El que no aparezca queda marcado **«sin respaldo en el estado»**: alerta en el inicio de Supervisión y Dirección, evento en bitácora y acceso directo a solicitar su reversión. No se revierte solo.
- **Alerta de antigüedad:** pagos aplicados desde archivos editables que llevan más de `dias_sin_respaldo_alerta` (45) sin un estado que los cubra.
- El asistente (paso 6) y Configuración piden `tope_pago_carpeta` junto a la carpeta; los topes diario y acumulado se rigen por §19. Las plantillas no llevan importes.

### 15.6 Asistente

Ocho pasos. El nuevo paso 5, «Caja: cortes y retiros», pide el calendario de cortes (§15.1), si se capturan piezas por denominación (§15.2) y los topes de retiros (§15.3). El paso 6, «Entrega y respaldo», conserva las carpetas, los niveles de detalle y la clave de recuperación, y agrega la carpeta vigilada del banco (§15.5). Las plantillas y su esquema incluyen los valores nuevos.

## 16. Versión 0.17: inventario (opcional, fase 6a)

Pensado para inventarios pequeños. Se enciende con el parámetro `modulo_inventario` (asistente, paso 1, o Configuración). Apagado, nada de este apartado aparece. Nada de aquí cambia `nucleo/`.

### 16.1 Artículos y existencias

- **Artículo:** clave única, nombre, precio, existencia mínima, activo y el concepto de cobro al que pertenece.
- La existencia no es un campo editable: es la suma de **movimientos inmutables** (`MovimientoInventario`: artículo, tipo, cantidad con signo, usuario, fecha, nota y referencia a la venta, devolución, entrada o conteo). Tipos: carga inicial, entrada, venta, devolución, merma, ajuste por conteo.

### 16.2 Venta

- **A un titular.** Operación elige artículos y cantidades y **cómo se paga**:
  - **Lo paga ahora:** se crean los cargos de la venta y pasa al cobro; ese pago se aplica **primero a los cargos de esa venta** y el resto, si lo hay, por el reparto normal.
  - **Se va a su adeudo:** se crean los cargos y quedan pendientes; se cobran después con lo demás, por el reparto normal.
- **Sin matrícula.** Para quien no es titular. Solo «lo paga ahora». Se registra contra una cuenta interna del negocio, «Público en general», que no aparece en el padrón, en la cobranza ni en los cargos automáticos y **nunca puede quedar con adeudo**: los cargos y su pago ocurren en la misma transacción o no ocurre nada. Recibo, corte, bitácora y reversión funcionan igual que con cualquier pago.
- La venta (`Venta` con sus renglones: artículo, cantidad, precio unitario al momento) crea los cargos y los movimientos de inventario en la misma transacción. El precio lo pone el artículo; quien vende no lo teclea.
- Si la existencia del sistema no alcanza, la venta **no se bloquea**: avisa, el renglón queda marcado «sin existencia» y aparece en la revisión de Supervisión.

### 16.3 Devoluciones

- Parámetros del negocio: `devoluciones_inventario` (sí/no) y `dias_devolucion`.
- Se parte del recibo (código o QR) o de la venta: comprueba que la venta existe, que está dentro del plazo y cuánto de cada renglón no se ha devuelto. No se devuelve más de lo vendido.
- El artículo regresa a existencias si está en buen estado; si no, sale como merma en el mismo acto.
- El dinero regresa de una de dos formas:
  - **Saldo a favor** del titular: Operación lo hace al momento; nace «por revisar» para Supervisión.
  - **Efectivo:** siempre por solicitud que resuelve otra persona, y con las reglas fijas del efectivo (sale del turno abierto de quien la ejecuta y solo si ese turno tiene ese efectivo; captura piezas si §15.2 está encendido). Entra en el esperado del arqueo y en los cortes.
- Una venta sin matrícula solo se devuelve en efectivo. Una venta que se fue al adeudo y no se ha pagado se devuelve cancelando lo pendiente de ese cargo, sin mover dinero.
- **Nunca regresa más dinero del que entró.** Por cada renglón, el dinero que regresa es a lo más lo realmente pagado de su cargo (aplicaciones de pagos vigentes) menos lo ya regresado; lo cancelado, condonado o descontado no se regresa.
- Un pago en efectivo, o de una venta sin matrícula, que cubre artículos cuya devolución ya regresó dinero **no se puede revertir completo**: lo que falte se devuelve desde la venta. Así una misma venta no saca dinero dos veces.
- Revertir completo el pago de una venta sigue el camino de reversiones existente y pregunta, renglón por renglón, si el artículo regresó.

### 16.4 Entradas y mermas

- Operación registra entradas (compras) y mermas con cantidad, motivo y, si lo hay, comprobante (mismo manejo de adjuntos que §15.3).
- No piden permiso previo. Nacen «por revisar»; quien tenga `revisar_inventario` las marca revisadas u observadas. Nadie revisa lo propio.

### 16.5 Conteo mensual

1. Operación descarga la lista para contar, que **no trae existencias**, cuenta en físico y sube un Excel o CSV con clave y cantidad, o captura en pantalla.
2. Al subirlo, el conteo queda fijo. El sistema guarda, por artículo, lo contado y lo que debía haber **en ese momento**, y entonces muestra las diferencias.
3. El conteo es una solicitud (`conteo_inventario`) que aprueba otra persona por las tres vías del motor: una sola aprobación para todo el conteo. Nadie aprueba su propio conteo.
4. Mientras se aprueba se sigue vendiendo y recibiendo. Al aprobar se crea, por artículo con diferencia, un ajuste igual a la diferencia del momento del conteo; los movimientos posteriores al conteo no se tocan.
5. Solo puede haber un conteo en espera. Si pasan `dias_conteo_sin_aprobar` avisa a Dirección.

- La carga inicial del inventario es un primer conteo aprobado.
- Los archivos subidos son datos no confiables: límites de tamaño y de filas, tipo por contenido, sin evaluar fórmulas, claves desconocidas o repetidas se rechazan con su renglón. Lo exportado a CSV neutraliza las celdas que empiezan con `=`, `+`, `-` o `@`.

### 16.6 Avisos, reportes y permisos

- **Quien vende ve el número de existencias** de cada artículo; cuando es cero no se muestra nada. La lista para contar sigue sin traer existencias.
- **Existencia baja:** un artículo está bajo cuando su existencia es de 20 % o menos (`porcentaje_existencia_baja`) de su nivel de referencia, que es la existencia que tenía justo después de su última entrada o de su último conteo aprobado; también cuando está en o bajo su mínimo, si se le fijó uno. Avisa a quien vende (marca «pocas» en la venta) y a Supervisión en su inicio. Resumen de existencias, ventas, devoluciones, mermas y ajustes del periodo en el corte mayor, en los tres niveles de detalle.
- Permisos: `vender_articulos`, `registrar_movimientos_inventario`, `subir_conteo_inventario`, `devolver_articulos` (Operación); `revisar_inventario`, `administrar_articulos` (Supervisión). Aprobar el conteo y las devoluciones en efectivo se define en las políticas, como las demás solicitudes.
- Todo queda en bitácora. Las plantillas llevan permisos, políticas y parámetros sin importes; no llevan artículos.

## 17. Versión 0.17: facturación electrónica (opcional, fase 6b; no construir en 6a)

Primer módulo que necesita internet; el resto del sistema funciona sin él. Nada aquí es asesoría fiscal: los valores los decide el contador de cada negocio.

- **Configuración, toda editable:** emisor (RFC, nombre, régimen, código postal de expedición, serie); por concepto de cobro, clave de producto o servicio y de unidad del SAT, objeto de impuesto, tratamiento de IVA y si el precio ya lo incluye; políticas (plazo para pedir factura, periodicidad de la global, qué hacer con un pago que ya entró en una global, equivalencia entre medio de pago y forma de pago del SAT).
- **Proveedor de timbrado por adaptador intercambiable** (timbrar, consultar, cancelar, descargar XML y PDF), más un adaptador simulado para pruebas. Proveedor real sin elegir.
- **Alcance inicial:** una factura por pago ya recibido. Sin parcialidades ni complemento de pago. La factura global se prepara como reporte y se timbra con confirmación de Supervisión o Dirección.
- **Flujo:** desde un recibo se elige o captura el perfil fiscal del receptor (por familia); validación local de formato y dígito verificador del RFC (aviso, no bloqueo: existen RFC válidos que no lo cumplen), código postal y compatibilidad de régimen y uso; la solicitud entra a una cola que envía el trabajador, de modo que nadie espera y sin internet queda «en espera»; timbrada, se guardan folio fiscal, XML y PDF; si el pago se revierte se genera la cancelación con su motivo sin detener la reversión.
- Un pago tiene a lo más una factura vigente; cada envío lleva una clave propia que impide timbrar dos veces ante un reintento.
- **Seguridad:** de preferencia el sello digital no vive en el servidor local y solo se guarda la llave de la API, cifrada como los demás secretos; si se termina sellando en local, el sello se guarda cifrado igual. Solo conexiones salientes HTTPS con verificación de certificado al proveedor configurado; respuestas tratadas como no confiables (XML sin entidades externas). Datos fiscales de receptores con acceso por permiso, bitácora y respaldo cifrado. Modo de pruebas visible.

## 18. Negocios que no usan matrícula (idea en trabajo; no construir)

Un negocio sin matrícula puede querer que las transferencias de sus clientes se reflejen solas. La matrícula del motor serviría como «referencia de pago» de cada cliente con otro nombre (el vocabulario ya lo permite). Faltaría una opción que la mantenga fuera de las pantallas diarias y la muestre solo en la ficha de pago.

## 19. Versión 0.19: topes del banco configurables (fase 7a)

Sustituye la regla del «tope de exposición» de §15.5 y la última línea de esa sección. Lo demás de §15.5 sigue igual.

### 19.1 Dos topes

Un archivo editable aplica solo sus pagos mientras no rebase **ninguno** de los dos topes. Al llegar a un tope nada se rechaza: el pago queda **retenido** con su motivo y quien concilia lo libera, como cualquier otro retenido.

- **Tope diario por día de la semana** (`TopeDiarioBanco`, siete renglones, importe en centavos). Cuenta la suma de pagos **aplicados solos** desde archivos editables en ese día calendario local (el día en que se aplican, no la fecha del movimiento). Un día en 0 retiene todo lo de ese día. Se evalúa movimiento por movimiento, en el orden del archivo: el que no cabe queda retenido («tope del día») y se sigue con el siguiente, que sí puede caber.
- **Tope acumulado** (`tope_aplicado_sin_respaldo`, ya existente): máximo de pagos aplicados desde archivos editables que todavía no respalda un estado. Baja solo cuando un estado en PDF confirma esos pagos. Sigue siendo señal del archivo: si con los pagos del archivo se rebasa, quedan retenidos todos.
- Los pagos **liberados a mano** no consumen el tope diario (son una decisión de una persona), pero sí cuentan en el acumulado mientras no los respalde un estado. Liberar nunca se bloquea por un tope.
- Valores iniciales: todo en 0. Aplicar solo es una decisión que el negocio toma al fijar los topes. Las plantillas no llevan importes.
- `tope_pago_carpeta` (importe máximo por pago) no cambia.

### 19.2 Quién los cambia y qué queda registrado

- Permiso nuevo `configurar_topes_banco`, que la plantilla da a Supervisión y a Dirección. Pantalla «Topes» en la sección de Banco, con reingreso de contraseña. El asistente (paso 6) pide los mismos valores.
- Cada cambio guarda en bitácora el evento `topes_banco_cambiados` con los valores de antes y de después.
- El inicio de quien tiene `ver_auditoria` lista los cambios de topes de los últimos 7 días hechos por otra persona, con quién, cuándo y de cuánto a cuánto. Motivo: quien concilia también libera pagos, así que Dirección debe enterarse sin tener que buscarlo.
- La pantalla muestra cuánto se ha aplicado hoy contra el tope del día y cuánto hay acumulado sin respaldo contra el tope acumulado.
- El asistente y Configuración → Carpetas dejan de pedir `tope_aplicado_sin_respaldo`; vive solo en «Topes» y en el asistente.

## 20. Versión 0.19: actualizaciones del programa (fase 7a)

Primera entrega: **buscar, avisar y descargar**. La instalación de un clic queda para después. Es opcional y viene apagada: es la primera conexión saliente del sistema fuera de respaldo.

### 20.1 Canal de versiones

- El código vive en un repositorio privado. Las versiones se publican en un **canal** aparte que solo contiene, por versión: el instalador, el aviso de versión (`version.json`), su firma (`version.json.firma`) y, si hace falta, un cambio de llave (`cambio-de-llave.json` y su firma). Nunca código.
- El canal se alcanza con un **adaptador** (`actualizaciones/canales/`). El primero es `github`: las publicaciones de un repositorio privado, leídas con una **clave de solo lectura** propia de cada instalación. Otro adaptador (servidor propio con licencias) se podrá añadir sin tocar lo demás.
- Configuración (Dirección, con reingreso; también en el asistente): activar o apagar, repositorio del canal (`propietario/nombre`, validado por patrón) y la clave. La clave se guarda cifrada como los demás secretos y no se vuelve a mostrar. Evento `actualizaciones_configuradas`, sin la clave.
- Publicar es manual y lo hace el dueño: la integración continua compila el instalador y **no publica ni firma nada**. Guía en `docs/GUIA-PUBLICAR-VERSION.md`.

### 20.2 Conexión

- Solo HTTPS con verificación de certificado, sin tomar proxies del entorno, con límite de tiempo. Servidores permitidos fijos por adaptador (`api.github.com`; para la descarga se sigue **una** redirección a `*.githubusercontent.com`, sin reenviar la clave).
- Límites de tamaño: aviso y firmas hasta 64 KB; instalador hasta lo que declara el aviso y nunca más de 500 MB.
- No se envía ningún dato del negocio. Sin internet no pasa nada ni se muestra error a quien usa el sistema.

### 20.3 Aviso de versión y firma

- `version.json`: `producto` («ariasmos»), `version` (X.Y.Z), `contador` (entero que solo sube), `fecha`, `instalador` (`nombre`, `tamano`, `sha256`), `minimo` (versión desde la que se puede actualizar) y `cambios` (hasta 20 líneas de 200 caracteres, texto plano).
- Firma Ed25519 **sobre los bytes exactos** del archivo. La firma se comprueba antes de interpretar el contenido.
- Se acepta solo si: la firma es válida con la llave de uso vigente, `producto` coincide, `version` es mayor que la instalada, `contador` es mayor que el último aceptado y el formato es exacto (campos de más o de menos lo invalidan). Si `minimo` es mayor que la instalada se avisa que hay que pasar antes por esa versión y no se ofrece la descarga.
- Lo rechazado deja el evento `actualizacion_rechazada` con su motivo, como máximo uno cada 6 horas por motivo.

### 20.4 Llaves

- Dos pares Ed25519 que genera el dueño en su computadora con `herramientas/firma/`. Las privadas van cifradas con contraseña y **nunca** entran al repositorio, a la integración continua ni a la computadora del negocio.
- El programa trae las dos llaves **públicas** en `sistema/actualizaciones/llaves.json` (`uso` y `recuperacion`). Si el archivo viene vacío, las actualizaciones no se pueden activar.
- **Llave de uso:** firma cada versión. **Llave de recuperación:** solo firma un cambio de llave.
- `cambio-de-llave.json`: `producto`, `contador` (propio, solo sube) y `llave_uso` (la nueva pública). Se acepta solo con firma válida de la llave de recuperación que trae el programa y contador mayor al último aceptado. Queda guardado (`LlaveDeUso`) y desde ese momento la llave anterior deja de valer. Evento `llave_de_uso_cambiada`, visible en el inicio de Dirección.
- **Los contadores son por llave.** El de versiones cuenta dentro de la llave de uso vigente y el de cambios de llave dentro de la llave de recuperación que trae el programa. Así una llave de uso robada no puede dejar al programa sin actualizaciones publicando un contador enorme, y un programa instalado a mano con llaves nuevas empieza a contar de cero.
- Al cambiar la llave de uso, las versiones firmadas con la anterior dejan de ofrecerse, sus descargas se retiran y sus archivos se borran (`actualizacion_rechazada`, motivo `llave_de_uso_distinta`).
- Si se pierden las dos llaves, el programa deja de actualizarse solo; se instala a mano una versión con llaves nuevas.

### 20.5 Buscar, avisar y descargar

- El trabajador busca al arrancar y una vez al día a un minuto variable. Dirección tiene «Buscar ahora», con límite de frecuencia.
- Si hay versión aceptada, **todos los papeles** ven en su inicio «Hay una versión nueva: X.Y.Z» con la lista de cambios (texto escapado).
- **Descargar** lo puede pedir cualquier persona con sesión (POST). Una descarga a la vez y a lo más tres intentos por hora. La hace el trabajador: baja el instalador a `actualizaciones/` dentro de los datos de la instalación (no se sirve por la web, permisos solo para el servicio), calculando la huella mientras baja; si el tamaño o la huella no coinciden con el aviso firmado, lo borra, registra `actualizacion_rechazada` y avisa a Dirección.
- La descarga corre aparte de las demás tareas del trabajador, para que una conexión lenta no detenga la carpeta del banco, los cortes ni los respaldos. La firma del aviso se vuelve a comprobar con la llave vigente antes de dejar el archivo listo.
- Descarga correcta: evento `actualizacion_descargada` con quién la pidió; Dirección lo ve en su inicio. El aviso cambia a «Lista para instalar» con las instrucciones.
- **Instalar (esta entrega): a mano**, en la computadora del servidor, con el acceso directo «Instalar actualización» (`herramientas/instalar-actualizacion`), que **vuelve a comprobar** firma y huella justo antes de ejecutar el instalador y se niega si no coinciden. El aviso advierte si hay turnos de caja abiertos y recuerda hacer respaldo antes.
- La pantalla de inicio de sesión y el splash siguen mostrando la versión instalada.

### 20.6 Herramientas del dueño (`herramientas/firma/`)

Se ejecutan en la computadora del dueño, no en la del negocio.

- `generar-llaves`: crea las dos llaves privadas cifradas con contraseña en la carpeta que se indique y escribe el contenido para `llaves.json`.
- `firmar-version`: recibe el instalador, la versión, el contador y el archivo de cambios; escribe `version.json` y `version.json.firma`.
- `cambiar-llave`: con la llave de recuperación, escribe `cambio-de-llave.json` y su firma para una llave de uso nueva.
- `.gitignore` excluye los archivos de llaves privadas por extensión.

## 21. Versión 0.20: programa de escritorio (fase 8a)

Corrige un error de las fases 4b y 5: el programa se abría en el navegador. El requisito del dueño es un programa que corra en la computadora, con su propia ventana. Esta sección **sustituye** en §11 todo lo que diga «navegador», el acceso directo a `https://localhost/` y la instalación del certificado en Windows.

El servidor no cambia: los tres servicios (web, trabajador, TLS) siguen en la computadora principal, porque varias personas en varias computadoras comparten una sola base y el trabajador corre aunque nadie tenga el programa abierto. Cambia cómo se abre y se ve.

### 21.1 `Ariasmos.exe`

- Programa nativo de Windows, pequeño, en `escritorio/` (C#, .NET Framework 4.8, que ya trae Windows 10 y 11; ventana WinForms con el componente WebView2 de Windows). Se compila en la integración continua y va dentro del instalador. No contiene lógica del negocio: es la ventana del programa.
- Se ve como programa propio: `Ariasmos.exe` en el administrador de tareas, ícono del medallón del jinete en la ventana y en la barra de tareas, sin barra de dirección, pestañas ni menús de navegador.
- Una sola ventana por usuario de Windows; abrirlo de nuevo trae al frente la que ya está. Recuerda tamaño y posición.
- No escribe datos del negocio en la computadora: solo su perfil (`%LOCALAPPDATA%\Ariasmos\`), donde vive la credencial del equipo aprobado, por usuario de Windows.
- Lleva la versión en su nombre de agente (`Ariasmos/X.Y.Z`) para que el servidor pueda avisar si esa computadora necesita actualizar el programa.

### 21.2 Splash

- Ventana real, sin marco, de 720 × 450, centrada: la escena aprobada, «ARIASMOS», «Iniciando el sistema…» y «ver. X.Y.Z». Se dibuja con los recursos del propio programa (imagen y letras incluidas), sin depender del servidor.
- Se muestra mientras arranca la ventana principal y hasta que carga la primera pantalla; después se desvanece. Si el servidor no responde, la ventana principal muestra el problema y «Reintentar».
- Mientras el splash está a la vista no se muestra ninguna otra ventana del programa.
- El splash que hoy vive dentro de la pantalla de inicio de sesión se elimina.

### 21.3 Dos formas de instalar, el mismo instalador

El instalador pregunta qué es esa computadora. Sirve para cualquier negocio, con una computadora o con muchas.

- **Computadora principal:** guarda los datos y da servicio a las demás. Instala los servicios y `Ariasmos.exe`.
- **Computadora adicional:** solo instala `Ariasmos.exe` y se conecta a la principal. No instala Python, servicios ni reglas de firewall. Pide el **archivo de conexión**.
- El **puerto** deja de ser fijo: se propone 443 y, si está ocupado, otro; se puede elegir. Queda en la configuración del servicio TLS, en la regla de firewall y en el archivo de conexión.
- Si falta el componente WebView2 (Windows 10 antiguos), el instalador lo instala con el instalador oficial de Microsoft, cuya firma se comprueba al compilar.

### 21.4 Archivo de conexión

- Lo genera la computadora principal en «Conectar otra computadora» (mismo permiso que hoy): dirección del servidor (nombre o IP), puerto y **huella SHA-256 del certificado** del servidor. No es secreto, pero debe llegar por un medio de confianza (USB o en persona): quien lo altere podría apuntar una computadora a otro servidor. Evento en bitácora al generarlo.
- Formato estricto y tamaño acotado; el programa rechaza cualquier campo de más o de menos.
- El instalador lo guarda en `%ProgramData%\Ariasmos\conexion.json`, que solo un administrador puede cambiar. En la computadora principal lo escribe el propio instalador.
- Si el certificado del servidor cambia (cambio de nombre del equipo o vencimiento), hace falta un archivo de conexión nuevo en las adicionales.
- La aprobación de equipos no cambia: una computadora nueva sigue quedando «pendiente» hasta que alguien con permiso la aprueba.

### 21.5 Identidad del servidor

- **Ya no se instala ningún certificado en Windows**, ni en la principal ni en las adicionales. El programa acepta únicamente el certificado cuya huella coincide con la del archivo de conexión, y solo para la dirección configurada. La huella se comprueba siempre, también si Windows confiara en el certificado; si no se puede comprobar, no se conecta.
- Conectarse por IP funciona aunque el certificado sea para el nombre del equipo, porque se compara el certificado exacto.
- Sin certificado instalado, un navegador común muestra advertencia: el camino soportado es el programa.

### 21.6 Ventana cerrada a todo lo que no sea el programa

- Solo navega a la dirección configurada. Enlaces a otros sitios, ventanas nuevas hacia fuera y protocolos externos se bloquean.
- Apagados: herramientas de desarrollador, menú contextual del navegador, teclas de navegador (recargar, abrir, ver código), barra de estado, guardado de contraseñas, autocompletado, gestos de navegación y los objetos del anfitrión. Entre la página y el programa solo existen los dos mensajes de §21.10. Siguen las teclas de edición y el zoom.
- Permisos de cámara, micrófono, ubicación, notificaciones y portapapeles: negados.
- **Descargas** (recibos, cortes, exportaciones, respaldos): siempre con «Guardar como»; nunca se abren solas.
- **Impresión** de recibos y subida de archivos funcionan dentro de la ventana.
- Si el componente falla, la ventana se recupera sola o lo dice; nunca cae a un navegador.
- Corre sin permisos de administrador.

### 21.7 Pruebas y compilación

- La integración continua compila `Ariasmos.exe`, corre sus pruebas (huella, formato del archivo de conexión, lista de direcciones permitidas) y la prueba de humo instala en modo principal y ejecuta `Ariasmos.exe --verificar`, que carga la primera pantalla comprobando la huella y termina con un código de resultado. También prueba la instalación en modo adicional.
- La prueba de humo deja de depender de que Windows confíe en el certificado.

### 21.8 Atrás y adelante

- Dos botones de flecha en la barra del programa, a la izquierda de la marca, con el estilo del sistema (pastilla, estado apagado cuando no hay a dónde ir). También Alt+← y Alt+→ y los botones laterales del ratón.
- Viven en la página (historial de la ventana), no en un marco aparte, para que se vean igual en todas las pantallas.
- **Regla de seguridad: atrás, adelante o recargar nunca repiten una operación.** Toda operación que mueve dinero o cambia datos se envía con una ficha de un solo uso y termina en redirección; volver a un paso ya terminado muestra su resultado (por ejemplo el recibo), no lo vuelve a ejecutar. Las pantallas con datos no se guardan en la memoria del historial (`no-store`): al volver se piden de nuevo.
- Una prueba recorre los flujos de cobro, venta, retiro, corte, devolución y conciliación reenviando cada paso y comprueba que nada se duplica.

### 21.9 Elegir carpetas y archivos con la ventana de Windows

- **Archivos** (importar clientes, logo, comprobantes, respaldos por restaurar): el botón abre la ventana normal de Windows para buscar el archivo.
- **Carpetas** (carpeta vigilada del banco, destino de los cortes, carpeta de respaldo): cada campo de ruta lleva «Examinar…», que abre la ventana de Windows para elegir la carpeta y llena el campo. Escribir la ruta a mano sigue siendo posible.
- Las carpetas son del disco de la **computadora principal**. «Examinar…» solo aparece ahí; en una adicional el campo explica que la carpeta se elige desde la principal.
- Si el servicio no tiene permiso sobre la carpeta elegida, la pantalla ofrece «Dar permiso»: Windows pide la confirmación de administrador y se concede sobre esa carpeta únicamente. Sustituye al paso manual de hoy.

### 21.10 Puente mínimo entre la página y el programa

Solo para §21.9, y solo estos dos mensajes, con formato estricto:

- `elegir_carpeta`: el programa abre la ventana de Windows y devuelve la ruta elegida, o nada si se cancela.
- `dar_permiso`: el programa muestra qué carpeta es, pide confirmación y lanza la herramienta elevada (control de cuentas de Windows). La herramienta valida la ruta por su cuenta.

Reglas: el programa acepta mensajes únicamente del documento principal de la dirección configurada y solo en la computadora principal; cualquier otro mensaje se descarta y se registra. La página nunca recibe más que la ruta que la persona eligió. No hay objetos del anfitrión ni ejecución de código pedida por la página.

### 21.11 Lo que queda para después

- **Firma de código.** `Ariasmos.exe` y el instalador van sin firma: Windows muestra una advertencia al instalar y, en equipos con Smart App Control activo, puede bloquearlo. Comprar un certificado de firma es una decisión del dueño.
- Las computadoras adicionales se actualizan a mano con el mismo instalador; el aviso de §20 les indica cuándo.

## 22. Versión 0.20: nada fijo de un negocio (fase 8b)

El programa es para cualquier negocio que cobra a clientes recurrentes. Una auditoría del código (17/11/2026) encontró textos y reglas que suponen un tipo de negocio. Esta fase los quita. Regla general: **lo que depende del negocio viene de la configuración** (asistente, plantilla, parámetros, vocabulario, marca) y nunca del código ni de las plantillas de pantalla.

### 22.1 Vocabulario completo

- Todo texto que nombre al titular, la matrícula, la agrupación o la familia usa el vocabulario del negocio: mensajes, etiquetas de formularios, PDF, exportaciones, encabezados de cortes y nombres de archivos. No queda ninguno escrito a mano.
- Claves nuevas: **padrón** (la lista de titulares), **descuento** (lo que la escuela llama «beca») y **público** (la venta sin matrícula). La plantilla de escuela conserva «Beca»; la genérica dice «Descuento».
- Formas en singular, plural y minúsculas se derivan en un solo lugar.
- Los sinónimos de la importación inicial incluyen el vocabulario configurado.
- Una prueba recorre todas las pantallas con un vocabulario inventado y falla si aparece una palabra del vocabulario de fábrica.

### 22.2 Roles por permiso, también en los textos

- Ningún texto nombra un rol fijo («Supervisión», «Dirección»). Donde hay que decir quién puede hacer algo, se muestran los nombres de los roles que hoy tienen ese permiso.
- Se corrige el permiso mal escrito que oculta el menú «Solicitudes» a quien solo aprueba.

### 22.3 Cortes y reportes

- Cada corte usa el **nombre** que le dio el negocio; los encabezados salen del vocabulario.
- Los tramos de antigüedad de la cartera son configurables (de fábrica 30, 60 y 90 días).
- Tamaño de hoja de los PDF configurable (Carta o A4).

### 22.4 Banco

- El lector de estados en PDF se elige por **adaptador** según el banco de la cuenta. Hoy existe uno (Santander PyME). Con otro banco el programa lo dice con claridad y ofrece el camino que sirve para cualquiera: Excel o CSV con correspondencia de columnas.
- La cuenta de depósito admite **CLABE** (con su dígito verificador) u **otra cuenta** (número y banco escritos), para negocios o países sin CLABE.
- Los medios de pago iniciales vienen de la plantilla, no del código.

### 22.5 Reglas que pasan a configuración

- Consentimiento de datos al dar de alta: se puede apagar y su texto es del negocio.
- Apellidos obligatorios o no (un cliente puede ser una empresa).
- Retención de respaldos (diarios y mensuales), horas para la alerta de respaldo y días entre pruebas de restauración.
- Avisos de retiros de caja (rechazos antes de pedir autorización, porcentaje de aviso del tope).
- El asistente pregunta lo que hoy solo está en parámetros: prefijo y dígitos del teléfono, tamaño de hoja y consentimiento. El formato del teléfono usa esos valores.
- Si la moneda elegida no es la de la plantilla, el asistente pide las denominaciones en lugar de dejar la caja sin ellas.
- Se unifican los valores de fábrica del calendario de cortes.

### 22.6 Cobros semanales y quincenales

Hoy se pueden elegir pero nunca generan cargos. Pasan a funcionar:

- **Semanal:** un cargo por semana. El periodo es la semana ISO (`AAAA-Sww`); vence el día de la semana que fije el concepto.
- **Quincenal:** dos cargos por mes (`AAAA-MM-1` y `AAAA-MM-2`, del 1 al 15 y del 16 al fin de mes); la primera vence el día que fije el concepto (1 a 15) y la segunda quince días después.
- Las reglas de unicidad, becas o descuentos, prórrogas, recargos y cierre de periodo aplican igual que en los mensuales. Las pruebas cubren cambio de año, semana 53, febrero y altas a mitad de periodo.

### 22.7 Marca del negocio desde la instalación, con colores tomados del logo

- El asistente tiene un paso de **marca**: subir el logo (opcional) y elegir los dos colores. Lo mismo sigue en Configuración → Marca del negocio.
- Al subir el logo, el programa **propone** los dos colores a partir de él y los muestra en una vista previa del programa. La persona puede aceptarlos o elegir los suyos; con o sin logo, los colores siempre se pueden cambiar. «Usar los colores del logo» queda disponible después.
- Cómo se calculan (determinista: el mismo logo da siempre los mismos colores):
  1. Se parte del logo ya saneado (§15, solo píxeles, 512 px como máximo) y se reduce a 96 px de lado mayor.
  2. Se descartan los píxeles transparentes. Si no hay transparencia, se descarta el color de fondo: el que domina el borde de la imagen cuando ocupa más del 60 % de ese borde.
  3. Se apartan los neutros: saturación menor a 0.15, o luminosidad mayor a 0.93 o menor a 0.07.
  4. Los demás se agrupan en hasta 8 colores (corte por mediana). El peso de cada grupo es su fracción de píxeles por (0.5 + saturación).
  5. Se toman el grupo de mayor peso y el siguiente de mayor peso cuyo tono difiera al menos 25° del primero. De los dos, el **más oscuro** es el **color principal** (es el de los botones y el texto, y así conserva el tono de la marca) y el otro es el **color de acento**. Si no hay segundo, el principal es el primero y el acento es su mismo tono con luminosidad 0.55 y saturación de al menos 0.6.
  6. Se ajustan con las reglas de contraste que ya usa la marca: el principal se oscurece por pasos hasta leerse sobre el fondo y con texto blanco encima; el acento hasta distinguirse del fondo.
  7. Si todo el logo es neutro (blanco y negro), el principal es el neutro más oscuro ya ajustado y el acento es el de fábrica.
- El cálculo no ejecuta nada del archivo: trabaja sobre los píxeles ya reconstruidos.

### 22.8 Importar y actualizar clientes desde Excel o CSV, también desde los niveles bajos

- La hoja sirve para **dar de alta** titulares nuevos y para **actualizar** los que ya existen. Un renglón actualiza a un titular solo si trae su matrícula; nunca se empareja por nombre.
- Se puede actualizar: datos de contacto, agrupación, responsable y nombre. Nunca cambia desde la hoja: la matrícula, los saldos, los cargos, los pagos ni el estado de alta o baja.
- **Dos permisos.** `importar_padron`: aplica la hoja directamente (el que hoy tiene la importación). `solicitar_importacion_padron` (nuevo; las plantillas lo dan al rol de operación): la hoja completa se vuelve **una sola solicitud** con su vista previa; quien aprueba ve cuántas altas y cuántos cambios trae y el detalle campo por campo, y la aprueba por cualquiera de las tres vías. Nadie aprueba la suya. Una aprobación para toda la hoja: sin cuello de botella.
- Al aprobar se vuelve a comparar contra los datos del momento: un renglón cuyo dato «antes» ya no coincide se salta y se lista; lo demás se aplica en una sola transacción.
- Las reglas que ya existen se respetan dentro del lote: el cambio de nombre sigue necesitando aprobación (la del lote la cubre), y cada cambio queda en la bitácora por titular, con quién lo pidió y quién lo aprobó.
- La hoja es dato no confiable: mismas defensas de la importación actual (tamaño y renglones acotados, celdas como texto, nada se ejecuta); el archivo se guarda fuera de lo que se sirve y se borra al resolverse la solicitud.
- La vista previa solo muestra los campos que el papel de quien sube puede ver.
- Se ofrece como paso opcional al final del asistente, como acción principal del padrón cuando está vacío y como «Importar o actualizar desde una hoja» en el padrón para quien tenga cualquiera de los dos permisos. El archivo se elige con la ventana de Windows desde cualquier computadora.

### 22.9 Plantillas incluidas y tienda de plantillas

- Además de la genérica y la de escuela se incluyen plantillas de arranque para: **gimnasio o club** (membresías), **academia o talleres**, **rentas** y **servicios con cuota**. Cada una trae su vocabulario, conceptos y periodicidades; todo se puede cambiar en el asistente.
- **Tienda de plantillas (fase futura; no construir):** un sitio web aparte donde se publican plantillas para descargar e importar con lo que ya existe. Las plantillas de la tienda irán firmadas como las versiones (§20) y se seguirán tratando como dato no confiable al importarlas.

### 22.10 Menos fricción

Regla de diseño para esta fase y las siguientes: el programa no pide lo que puede deducir ni obliga a lo que puede esperar.

- Todo paso opcional del asistente se puede saltar y completar después desde Configuración.
- Los valores de fábrica sirven para empezar a trabajar el mismo día.
- Una pantalla vacía dice cuál es el siguiente paso y lo ofrece con un botón.
- Las rutas se eligen con la ventana de Windows (§21.9); los colores salen del logo (§22.7); los clientes se importan de una hoja (§22.8).

### 22.11 Lo que no cambia en esta fase

- El idioma (español), el formato de fechas y de números, y el catálogo de bancos de México. Otro país es una fase aparte.
- La marca «Ariasmos» del programa.

## 23. Versión 0.21: configurador y caja más cómodos (fase 9a)

Regla de la fase: quien configura o cobra no escribe lo que puede elegir, y no ve lo que no aplica.

### 23.1 Zona horaria en lista

- La zona horaria se **elige de una lista con buscador**, nunca se escribe. La lista sale de la base de zonas horarias IANA que ya trae el programa (`zoneinfo` con `tzdata`), solo las zonas canónicas con región (`América/…`, `Europa/…`), agrupadas por región y mostradas como «Ciudad (UTC−06:00)» con el desfase vigente.
- El asistente propone la zona de la computadora principal si se reconoce; si no, ninguna.
- El servidor valida contra la misma lista.

### 23.2 El signo sigue al tipo

- Donde se elige entre **porcentaje** e **importe fijo** (recargos, descuentos y cualquier otro), el campo del valor muestra solo el signo que corresponde (`%` o el símbolo de la moneda) y cambia al cambiar el tipo, con sus límites y su captura guiada. Sin JavaScript se ven los dos campos con su etiqueta.
- El servidor sigue validando el valor según el tipo recibido.

### 23.3 Abrir turno contando las piezas

- Con el control de piezas activo, abrir turno con efectivo **pide cuántas piezas hay de cada denominación**, con los mismos mosaicos del cobro; el fondo inicial es la suma y no se escribe aparte. Abrir en cero sigue siendo un solo paso.
- Sin control de piezas se pide solo el importe.
- Las piezas de apertura entran al registro de piezas de la caja, para que el cambio propuesto las tome en cuenta. La apertura es declaración de quien abre; el arqueo ciego no cambia.

### 23.4 Orden en los buscadores y listas

- Toda lista o buscador de titulares (padrón, buscar para cobrar, vender, conciliar) ofrece **ordenar por**: nombre, apellidos, matrícula, agrupación o familia, ascendente o descendente. Las demás listas largas (artículos, usuarios, solicitudes, cortes) ofrecen los órdenes que les sean naturales.
- El orden elegido se recuerda por persona y por lista.
- El servidor solo acepta claves de una lista cerrada por pantalla; nunca un campo recibido tal cual.

### 23.5 Pantallas de caja como el diseño aprobado

- «Mi caja» (abrir turno, turno abierto, cerrar con conteo, reconteo, resultado) y el retiro siguen las referencias aprobadas `docs/diseno/referencia/` de corte, reconteo, resultado y retiro: mosaicos de piezas, suma en vivo, pasos claros y una sola acción principal por pantalla. Las reglas del arqueo ciego (§15.2) no cambian.

### 23.6 Configurador más amable

- Cada paso del asistente: una idea por pantalla, texto breve que dice para qué sirve, valores de fábrica ya puestos, elegir en lugar de escribir (listas, interruptores, mosaicos), ejemplos junto al campo, errores junto al campo que los causa y en palabras llanas, y «Atrás» sin perder lo capturado.
- Lo avanzado va plegado bajo «Más opciones».
- El paso de caja del asistente usa los mismos componentes que las pantallas de caja.
- Las mismas reglas aplican a las pantallas de Configuración.

## 24. Versión 0.21: tarifas por agrupación, límites de adeudo y rezagados (fase 9b)

### 24.1 Tarifas y cargos por agrupación

- Un concepto de cobro puede tener **tarifas por agrupación** (`TarifaAgrupacion`: concepto, agrupación, importe y, si el concepto es recurrente, periodicidad y vencimiento propios; activa o no). Sin tarifa para la agrupación del titular vale lo general del concepto.
- Un concepto puede ser **por cantidad** (libros, materiales, sesiones): al cargarlo se pide la cantidad (entero de 1 al máximo configurado) y el importe es cantidad × tarifa. El cargo guarda cantidad e importe unitario.
- Los cargos automáticos toman la tarifa de la agrupación que el titular tiene al generarse. Cambiarlo de agrupación aplica desde el siguiente periodo; los cargos ya generados no cambian.
- Un concepto recurrente puede aplicar **solo a ciertas agrupaciones**: sin tarifa activa y con «solo con tarifa» marcado, no se genera cargo.
- Lo configura quien administra conceptos, en Conceptos y, opcional, en el asistente. Cada cambio de tarifa queda en bitácora con antes y después.
- Plantillas: la de escuela trae «Libros» por cantidad con tarifa por grupo; las demás traen un ejemplo equivalente con su vocabulario. Ninguna trae importes.
- El inventario no cambia: un artículo sigue teniendo su precio; la tarifa por agrupación es de conceptos de cobro.

### 24.2 Recargos tras el alta

- Parámetro `recargos_tras_alta`: `siguiente_periodo` (de fábrica) o `desde_alta`.
- Con `siguiente_periodo`, los cargos cuyo vencimiento cae dentro del periodo (según la periodicidad del concepto) en que el titular se dio de alta no generan recargo por atraso. Desde el periodo siguiente, todo normal.
- Reactivar una baja cuenta como alta nueva para esta regla. La fecha que cuenta es la de activación, no la de la solicitud.
- La regla se aplica al decidir si un cargo genera recargo, fuera de `nucleo/`.

### 24.3 Límite de adeudo

- Dos límites independientes: **importe máximo** de adeudo vencido y **días máximos** de atraso (días desde el vencimiento más antiguo con saldo). Cada uno se elige entre **«Ilimitado»** (opción explícita, de fábrica) o un valor.
- Hay un valor del negocio y **excepciones por titular** (con su propio «Ilimitado», valor, motivo y vigencia opcional).
- Permiso nuevo `configurar_limites_adeudo`; las plantillas lo dan a los niveles superiores. Cambios en bitácora con antes y después, y a la vista de quien tiene `ver_auditoria` en su inicio, como los topes del banco.
- Rebasar cualquiera de los dos deja al titular **rezagado** y con la restricción «sin crédito» (§24.4).
- **Nunca se bloquea recibir un pago** ni consultar el estado de cuenta.

### 24.4 Rezagados: reglas y acciones

- El negocio define **reglas** (`ReglaRezago`): nombre, a quién aplica, cuándo se cumple y qué acciones dispara.
  - **A quién:** todos, una agrupación o un titular.
  - **Cuándo:** a partir de N días de atraso, a partir de un importe vencido, al rebasar el límite de adeudo, o combinación (basta una condición).
  - **Acciones** (una o varias):
    - `aviso_inicio`: aparece en el inicio de **todos los papeles** con nombre, matrícula, agrupación, días de atraso y, solo para quien puede ver saldos, el adeudo.
    - `marca`: una marca con **texto propio del negocio** (por ejemplo «No puede pasar») en la ficha, en los buscadores y al cobrar.
    - `sin_credito`: las ventas al adeudo, los cargos manuales nuevos y las prórrogas para ese titular pasan a solicitud.
    - `cobranza`: entra en la lista de cobranza.
- **Reglas propias:** además de las de la plantilla, el negocio crea las suyas sin límite de cantidad, con su nombre y su texto. Si varias aplican a un titular, valen todas sus acciones; en el aviso se muestra el texto de la regla más grave (más días).
- Una regla dirigida a un titular o a una agrupación tiene prioridad sobre la general del mismo tipo: permite ser más estricto o más tolerante con alguien en particular.
- La condición se evalúa al momento con los saldos reales: al ponerse al corriente, el titular deja de estar rezagado sin que nadie haga nada. No se guarda un estado que pueda quedar viejo.
- Permiso nuevo `configurar_rezagos`, a los niveles superiores en las plantillas. Bitácora de cambios.
- El texto de la marca es dato del negocio: se muestra siempre escapado y con largo acotado.
- Cada plantilla trae reglas de arranque con su vocabulario (escuela: aviso a los pocos días y «No puede pasar» más adelante; gimnasio: «Acceso suspendido»; etcétera), sin importes y todas editables.
- El aviso del inicio lista como máximo los 20 más atrasados y enlaza a la lista completa, que se puede ordenar y exportar con el permiso de ver saldos.

### 24.5 Rendimiento

El cálculo de atraso y adeudo vencido de todos los titulares se hace con consultas agregadas (nunca una por titular) y debe responder con 5,000 titulares y 100,000 cargos sin que el inicio lo note; se prueba con el número de consultas.

## 25. Versión 0.22: lo que el cliente ve desde el primer día (fase 10)

Estado: construida en 0.9.2; §25.5 construida en 0.10.0 (fase 11, §26.6).

Origen: pruebas del dueño sobre una instalación real. Regla de la fase: **todo se prueba como lo recibe un cliente**, con los valores de fábrica de cada plantilla, sin encender nada a mano.

### 25.1 El efectivo siempre se cuenta por piezas

- `control_denominaciones` pasa a venir **encendido de fábrica**: en el valor por omisión del parámetro y en todas las plantillas. El asistente lo pregunta en el paso de caja con palabras llanas («¿Contar billetes y monedas en cada movimiento de efectivo?»), ya marcado en sí.
- Al actualizar una instalación existente que lo tenga apagado, la migración lo enciende y deja un evento que Dirección ve en su inicio, con el enlace para apagarlo si así lo decide.
- Con el control encendido, **todo movimiento de efectivo pide las piezas** con los mismos mosaicos: abrir turno, cobrar (lo recibido y el cambio), venta de contado y venta sin matrícula, retiro de caja, devolución en efectivo, entrega y recepción de efectivo entre personas, depósito al banco y cierre. Ninguno acepta solo un importe.
- Si faltan denominaciones para la moneda del negocio, el programa lo dice y lleva a capturarlas, en lugar de pedir un importe.
- El arqueo ciego (§15.2) no cambia.

### 25.2 Formularios que se adaptan a lo elegido

- Ningún campo queda a la vista si una elección anterior lo hace innecesario, y ninguno conserva una forma fija si la elección la cambia: aparece, desaparece o cambia de signo, de límites o de etiqueta según lo elegido. Aplica a **todos** los formularios (ejemplos: «Hasta un valor» en los límites de adeudo; «A quién aplica» en las reglas de rezago; periodicidad y vencimiento; tipo de cuenta de depósito; tipo de destino).
- Un solo mecanismo declarativo (atributos de datos en el campo que dicen de qué elección depende y con qué valores se muestra) y un solo JS propio. Sin JavaScript se ven todos los campos con su etiqueta condicional.
- El servidor ignora lo que venga en un campo que no aplica a la elección recibida y valida el que sí aplica.
- Una prueba recorre todos los formularios y falla si encuentra una etiqueta condicional («si elegiste…», «si aplica…») en un campo sin dependencia declarada.

### 25.3 Botones a prueba de clics repetidos

- Todo botón que envía un formulario se bloquea al primer clic y muestra que está trabajando; se libera si la página vuelve con errores. Los enlaces de acción hacen lo mismo.
- En el servidor, envíos repetidos o simultáneos del mismo formulario nunca producen un error: el segundo espera o recibe el resultado del primero (§21.8). La base ocupada se reintenta en lugar de fallar.
- Prueba: diez envíos simultáneos de cada operación principal (abrir turno, cobrar, vender, retirar, cerrar, aprobar una solicitud) producen una sola operación y ninguna respuesta de error.

### 25.4 Cobrar con la lista a la vista

- Al entrar a Cobrar aparece la lista de titulares activos, paginada, con el orden que eligió la persona (§23.4), su agrupación, su marca de rezago y su adeudo si quien mira puede ver saldos. Un clic lleva a cobrarle.
- Arriba, un filtro que reduce la lista mientras se escribe (nombre, apellidos, matrícula, agrupación o familia); la búsqueda completa queda para cuando el filtro no encuentra a nadie.
- Lo mismo en Vender a un titular.
- Con muchos titulares la lista no se carga entera: página de 50 y consultas agregadas (sin una consulta por renglón).

### 25.5 Pantallas que se actualizan solas (construida en la fase 11)

- Cuando en cualquier computadora aprobada se registra un movimiento (pago, venta, retiro, alta, solicitud, importación del banco), las demás pantallas abiertas lo reflejan en segundos sin recargar: inicio, lista de cobrar, ficha, solicitudes, banco y existencias.
- Mecanismo: cada página consulta cada pocos segundos una ruta ligera (`/pulso`) que devuelve solo contadores de cambio por tema; cuando un contador cambia, la página vuelve a pedir **la misma pantalla** y sustituye sus regiones marcadas como vivas. No hay conexión permanente ni puente nuevo.
- Reglas:
  - `/pulso` exige sesión y equipo aprobado y no devuelve datos: solo números que suben. No revela importes ni quién hizo qué.
  - Lo que se muestra al actualizar pasa por la misma vista y los mismos permisos que al abrir la pantalla.
  - Nunca se sustituye una región donde la persona está escribiendo, un formulario a medias ni una pantalla de conteo; ahí aparece un aviso discreto «Hay cambios — Actualizar».
  - Las pantallas de cobrar con piezas, conteo y cierre no se actualizan solas.
  - Sin JavaScript todo funciona como hoy.
  - La consulta se pausa cuando la ventana no está a la vista y tiene límite de frecuencia.
- Los contadores suben dentro de la misma transacción que el movimiento.

### 25.6 Pruebas de fábrica

- Una prueba de punta a punta por cada plantilla: corre el asistente con los valores de fábrica y recorre un día completo (abrir turno, cobrar con cambio, vender, retirar, devolver, cerrar), comprobando que cada paso pide las piezas y que ninguna pantalla falla.
- Las pruebas de pantallas dejan de encender parámetros a mano, salvo cuando prueban justo el caso apagado.

## 26. Versión 0.23: interfaz interactiva (fase 11)

Estado: construida en 0.10.0 (ver §26.8 para lo que quedó fuera).

Origen: prototipo aprobado por el dueño el 18/11/2026. Se parte de la interfaz actual, que le gusta: se mejora, no se reemplaza. Debe verse y comportarse como el prototipo (mismas pantallas, distribución y animaciones, con sus duraciones y curvas), respetando todo lo que el programa ya tiene; donde el prototipo no muestra algo, manda el programa.

### 26.1 Reglas de interfaz (valen para todo cambio de interfaz)

- Toda interfaz se enseña al dueño antes de implementarla.
- **Los logotipos se ven como hoy**: el del negocio y el de Ariasmos, tal cual, en su lugar y a su tamaño. No se sustituyen por iniciales ni se rediseñan.
- **Textos para gente que no sabe de tecnología**: palabras llanas, preguntas en lugar de etiquetas técnicas, una frase por pantalla que diga qué hacer, sin jerga. Todo texto pasa por el vocabulario (§22).
- **Mejora progresiva**: cada pantalla funciona sin JavaScript como hoy; el JS propio la enriquece. Sin dependencias, con la CSP estricta (sin estilos ni scripts en línea; los estilos dinámicos se ponen por CSSOM).
- Respeta `prefers-reduced-motion`. Objetivos de clic de 44 px o más. Todo se alcanza con teclado.
- «Deshacer» nunca en pagos ni en movimientos de caja. En aprobaciones solo como envío en espera (§26.4) y en datos de la ficha como cambio nuevo auditado (§26.5).

### 26.2 Buscar o ir a

- Un botón en la barra y `Ctrl K` abren una caja única: personas, pantallas y acciones.
- Ruta `GET /ir/?q=` que devuelve JSON. Exige sesión y equipo aprobado. Solo devuelve pantallas y acciones que la persona puede abrir, y titulares que puede ver; el adeudo solo si tiene permiso de ver saldos. Tope de resultados y límite de frecuencia. No se guarda lo buscado.
- Flechas, Enter y Esc. Sin JS, el botón lleva al buscador de siempre.

### 26.3 Cobrar en una sola pantalla

- La lista (§25.4) queda a la vista; al elegir a alguien se abre un panel al lado (cajón en ventanas angostas) con sus cargos, lo que paga, los mosaicos y la confirmación. `Esc` lo cierra. Flechas y Enter recorren la lista; al escribir se resalta la coincidencia.
- Mosaicos: un toque suma; «−» resta sin que la pantalla brinque; con la pieza enfocada se puede escribir la cantidad. Lo recibido y lo que falta se calculan al instante en el navegador **solo como ayuda**.
- El servidor sigue siendo la autoridad: valida el importe, las piezas y el cambio como hoy. **Las existencias de la caja nunca viajan al navegador**: el cambio a entregar lo propone el servidor con la misma regla y los mismos permisos que el paso de cambio actual.
- El flujo por pasos actual se conserva como camino sin JS.
- Al confirmar: botón bloqueado (§25.3), confirmación con el recibo y «Siguiente cobro».
- El arqueo ciego (§15.2) no cambia.
- Cómo quedó: el panel es la misma vista de cobro con `?panel=1`; el navegador la pide, toma la región `#panel-cobro-region` con `DOMParser` y envía sus formularios por `fetch`. Un solo paso (`paso=panel`) lleva el importe y las piezas recibidas: si el pago es exacto se registra de una vez; si hay cambio, el servidor lo propone con `proponer_cambio` (mismo límite de propuestas por turno) y la persona confirma. Los cargos se muestran en el orden en que el pago los cubre (§23.4) y las casillas solo ayudan a llenar el importe: quitar uno quita también los que van después, porque el reparto lo decide el orden configurado.
- Método «Transferencia» (cambio del dueño): selector Efectivo / Transferencia; en Transferencia, «Esperando la transferencia…», la cuenta principal del negocio con «Copiar» y la matrícula como referencia, todo de la configuración. Sin cuenta configurada se dice en palabras llanas y quien puede configurarla recibe el enlace. Cuando llega un pago por banco del titular o su familia, el panel pasa solo a «Transferencia recibida y aplicada».
- Puerta de llegada (`banco/llegadas.py`): toda transferencia aplicada, venga de donde venga (estado de cuenta subido, carpeta vigilada, confirmación en la cola o un origen nuevo), pasa por `conciliacion.aplicar`, que avisa a `llegadas.transferencia_aplicada` y sube el contador `transferencias` de `/pulso`. Los orígenes nuevos se registran por configuración en `ORIGENES_TRANSFERENCIA` (rutas a clases que heredan de `llegadas.Origen`, con `consultar()` para consulta periódica y `leer_aviso()` para avisos entrantes) y entregan `llegadas.Aviso`; `llegadas.recibir` los convierte en movimientos y los pasa por `conciliacion.importar` con el origen `aviso`, que aplica las mismas reglas que la carpeta vigilada (topes del día y de exposición, retenciones, bitácora). El comando `consultar_transferencias` recorre los orígenes registrados. No hay ningún proveedor implementado; las pruebas usan un origen que solo existe en `pruebas/`.

### 26.4 Inicio

- Cifras que cuentan hasta su valor, gráfica de cobranza de los últimos siete días (efectivo y transferencia) con detalle al pasar el cursor o enfocar, y avance del periodo. Cada dato respeta el permiso que hoy lo protege; quien no puede ver importes no los recibe.
- Solicitudes: se abren, aprueban o rechazan ahí mismo (el rechazo pide motivo), con los mismos permisos y la misma bitácora. Sin «Deshacer».
- Rezagados con «Cobrar» directo.
- Campana con lo último que entró.
- Cambio del dueño: aprobar o rechazar desde el inicio muestra «Solicitud aprobada / rechazada · Deshacer» unos 5 segundos y funciona como envío en espera: nada se manda al servidor hasta que el aviso se agota, la persona hace otra acción o sale de la página (`pagehide` con `fetch` y `keepalive`). «Deshacer» solo cancela el envío pendiente, así la bitácora registra únicamente lo que pasó. Si el servidor rechaza la acción, se avisa y la solicitud vuelve a la lista. Sin JS, el flujo de siempre.
- La gráfica y el avance del mes los ve quien tiene «ver cortes» y no tiene un turno abierto (arqueo ciego). «Lo último que entró» muestra importes solo a quien ve saldos o a quien registró el pago, y a nadie con turno abierto.

### 26.5 Ficha, banco y configuración

- **Ficha**: pestañas (estado de cuenta, historial, datos), historial como línea de tiempo, y corrección en su lugar solo de los datos que esa persona ya puede cambiar directo; lo que hoy pide aprobación la sigue pidiendo. La corrección en su lugar es de los datos de contacto y usa el mismo formulario y la misma bitácora que «Editar contacto»; «Deshacer» guarda de inmediato un cambio nuevo, también auditado, con el valor anterior.
- **Banco**: zona para soltar el archivo, avance de lectura, «¿De quién es?» y «¿Qué tan seguro?» en palabras, elegir varios y aplicarlos juntos. Topes, retenciones y permisos (§19) sin cambio. «Aplicar pagos» (`/banco/cola/aplicar/`, permiso de conciliar) confirma cada movimiento elegido con la misma función que la confirmación de uno solo.
- **Configuración**: vista previa al instante de colores y logotipo (§22.9), listas que se ordenan arrastrando o con botones donde ya exista un orden configurable, y barra de «cambios sin guardar».
- **«¿Cómo se usa?»**: en las pantallas principales, tres pasos en palabras llanas, plegables.
- **Trucos de teclado**: ayuda en «?», presentados como opcionales.

### 26.6 Pantallas en vivo

- Se construye §25.5 tal como está escrita: ruta `/pulso` con contadores por tema, sin datos; la página vuelve a pedirse a sí misma y sustituye sus regiones vivas; nunca sobre un formulario a medias ni en pantallas de conteo.
- En la interfaz: la campana, «Lo último que entró», las cifras del inicio, la lista de cobrar y las solicitudes se ponen al día solas, con un destello discreto en lo que cambió y un aviso breve.
- La llegada automática de transferencias desde un proveedor **no** entra en esta fase; sí la puerta de llegada para conectarla (§26.3).
- Cómo quedó: modelo `vivo.Contador` con un renglón por tema (cobros, transferencias, titulares, solicitudes, caja, banco, inventario); señales al guardar o borrar los modelos de cada tema suben su contador dentro de la misma transacción. `/pulso` (sesión, equipo aprobado, 40 consultas por minuto) devuelve solo esos números y no cuenta como actividad de la sesión; las páginas consultan cada 5 segundos con la ventana a la vista, piden la misma dirección con la cabecera `X-Ariasmos-Vivo` (tampoco cuenta como actividad) y sustituyen las regiones con `data-vivo`. Con un formulario tocado, un panel de cobro abierto o un «Deshacer» pendiente, aparece «Hay cambios — Actualizar». `/ultimo/` da «Lo último que entró» con los mismos permisos.

### 26.7 Pruebas

- Pruebas de servidor para cada ruta nueva: permisos, equipo aprobado, saldos ocultos a quien no puede verlos, límites de frecuencia.
- Pruebas en navegador real que se omiten solas si no hay navegador: flujo de fábrica de abrir turno, cobrar en el panel, clics repetidos, buscar o ir a, dependencias y filtro en vivo, sin errores de consola ni de política de contenido.

### 26.8 Lo que quedó fuera de la fase 11

- Ninguna ruta de avisos entrantes de proveedores: la interfaz `leer_aviso` existe, pero abrir una ruta pública se decide cuando haya proveedor.

### 26.9 Cierre para quedar igual que el prototipo

- **Filtros de Cobrar** («Todos / Con adeudo / Rezagados» con su cuenta): parámetro `estado` por GET en `titulares/lista.py`, también con el filtro en vivo y con los renglones que se reacomodan. «Rezagados» son quienes tienen aviso o marca de rezago visible para esa persona y lo ve todo el que cobra. «Con adeudo» y su cuenta solo para quien ve saldos; a los demás no se les muestra y el parámetro se ignora. Consultas agregadas, sin una por renglón.
- **Billete o moneda** es un dato de cada denominación (`Denominacion.tipo`), con migración que deja «billete» en lo existente. Va en las seis plantillas, se edita en Configuración › Denominaciones («¿Es billete o moneda?») y el asistente lo pregunta cuando la moneda no es la de la plantilla. Los mosaicos de moneda son redondos y, sin piezas, dicen «billete» o «moneda».
- **Buscar o ir a** con la caja vacía muestra los tres primeros rezagados; el adeudo solo a quien ve saldos.

## Versión 1.0: licencias y Ariasmos Central (fase 1a)

### Qué se construye

- **Ariasmos Central**: servidor pequeño y aparte (carpeta `central/`), que da de alta negocios, entrega códigos de activación y emite, renueva y revoca licencias. Solo API y comandos del dueño. Sin pantallas, sin sesiones, sin administrador web.
- **En el programa** (app nueva `sistema/licencias/`): identidad de la instalación, verificación de licencia, renovación automática, protección contra retroceso del reloj y candado de solo consulta. **Sin pantallas ni rutas nuevas** (van en la fase 1b).
- La conexión siempre la inicia el programa. Central nunca llama al negocio.
- `central/` no entra al instalador (este solo copia `sistema`, `nucleo`, `datos`, `plantillas`).

### Documento firmado: `nucleo/licencia.py` (puro, sin Django)

Un **documento** es `{"carga": "<base64>", "firma": "<base64>"}`. `carga` son los bytes exactos de un JSON; `firma` es Ed25519 (64 bytes) sobre esos bytes.

```
FORMATO = 1
PRODUCTO = "ariasmos"
LIMITE = 8192                      # bytes de la carga ya decodificada
CAMPOS = {
  "licencia":   ("formato","producto","tipo","negocio","instalacion","plan","modulos","serie","emitida","vence","dias_gracia"),
  "revocacion": ("formato","producto","tipo","negocio","instalacion","emitida"),
  "renovacion": ("formato","producto","tipo","instalacion","momento","sello","version"),
  "activacion": ("formato","producto","tipo","instalacion","momento","sello","version"),
}
class LicenciaInvalida(Exception):  # atributo .motivo
serializar(carga: dict) -> bytes    # json sort_keys, separadores (",",":"), ensure_ascii=False, UTF-8
firmar(carga: dict, llave_privada) -> dict                 # Ed25519PrivateKey de cryptography
abrir(documento, llaves_publicas, tipo: str) -> dict        # llaves: iterable de bytes crudos (32)
huella(llave_publica: bytes) -> str                         # sha256 en hex (64) de los 32 bytes
texto_de(momento: datetime) -> str                          # "YYYY-MM-DDTHH:MM:SSZ" (UTC, sin fracción)
momento_de(texto: str) -> datetime                          # estricto, devuelve aware en UTC; si no, ValueError
```

`abrir`, en este orden, y cualquier fallo lanza `LicenciaInvalida(motivo)`:
1. `documento` es dict con exactamente `carga` y `firma`, ambos texto; base64 estricto (`validate=True`); carga ≤ `LIMITE`; firma de 64 bytes → si no, motivo `formato`.
2. La firma verifica con alguna de las llaves → si no (o si no hay llaves), motivo `firma`. **Nada se interpreta antes de verificar.**
3. JSON estricto (objeto; rechaza claves repetidas) → `formato`.
4. Claves exactamente `CAMPOS[tipo]`; `formato == 1`; `producto == "ariasmos"`; `tipo` igual al pedido; textos son `str`; `serie` y `dias_gracia` enteros ≥ 0 (no `bool`), con `dias_gracia` ≤ 366, `serie` ≤ 2**53 y, en la licencia, `vence` ≥ `emitida`; `modulos` lista de `str`; `instalacion` 64 hex minúsculas; `sello` 32 hex minúsculas; `version` `^\d+\.\d+\.\d+$`; `emitida`, `vence`, `momento` pasan `momento_de` → si no, motivo `campos`.
Devuelve la carga como dict (fechas como texto).

Cargas:
- licencia: `{"formato":1,"producto":"ariasmos","tipo":"licencia","negocio":"<uuid>","instalacion":"<huella>","plan":"base","modulos":[],"serie":7,"emitida":"…Z","vence":"…Z","dias_gracia":14}`
- revocacion: `{…,"tipo":"revocacion","negocio":"<uuid>","instalacion":"<huella>","emitida":"…Z"}`
- renovacion / activacion (las firma la instalación): `{…,"tipo":"renovacion","instalacion":"<huella>","momento":"…Z","sello":"<32 hex al azar>","version":"X.Y.Z"}`

### Programa: app `licencias` (`sistema/licencias/`)

Se agrega a `INSTALLED_APPS` y su candado al **final** de `MIDDLEWARE` (en `base.py`).

| Archivo | Contenido |
|---|---|
| `llaves.json` | `{"licencias": []}` (lista de llaves públicas de Central en base64; se entrega vacía) |
| `llaves.py` | `RUTA` (ruta de `llaves.json`); `publicas() -> tuple[bytes, ...]` lee `RUTA` en cada llamada. Estricto: solo la clave `licencias`, máx. 4 llaves de 32 bytes, archivo < 4 KB; si no, `ImproperlyConfigured`. Si falla, `situacion()` no lanza: devuelve `solo_consulta` con motivo `llaves` (falla cerrada) |
| `politica.py` | `DIAS_PARA_ACTIVAR = 14`, `HORAS_ENTRE_RENOVACIONES = 12`, `TOLERANCIA_RELOJ = timedelta(hours=1)`, `PASO_RELOJ = timedelta(minutes=5)`. Son política del programa: **no** van en `PARAMETROS` (el negocio no debe poder cambiarlas) |
| `reloj.py` | `ahora()` → `timezone.now()`. Única fuente de hora de la app; se llama siempre como `reloj.ahora()` |
| `models.py` | `Instalacion` (única, pk=1): `llave_cifrada`, `huella` (64), `activada` (bool, falso), `primer_arranque`, `mayor_momento` (la cuenta propia del programa), `ultimo_reloj` (última lectura del reloj del equipo), `documento` (texto JSON, vacío si no hay), `revocacion` (texto JSON, vacío si no hay), `ultimo_intento` (nulo), `ultimo_resultado` (≤40, vacío) |
| `cliente.py` | `class SinConexion(Exception)`; `enviar(ruta: str, cuerpo: dict) -> tuple[int, dict]` |
| `servicios.py` | ver abajo |
| `middleware.py` | `Candado` |
| `management/commands/licencia_activar.py`, `licencia_estado.py` | comandos |
| `migrations/0001_initial.py` | solo la tabla nueva |

La llave privada de la instalación (Ed25519) se genera al crear la fila y se guarda cifrada con el mismo mecanismo que ya cifra secretos en el programa (el de `CLAVE_SECRETOS`, usado para TOTP). Nunca sale del equipo ni se registra.

#### `servicios.py`

```
@dataclass(frozen=True)
class Situacion: estado: str; motivo: str; vence: datetime | None; limite: datetime | None

instalacion() -> Instalacion          # la crea si falta: llave nueva, primer_arranque = mayor_momento = ultimo_reloj = reloj.ahora()
identidad() -> tuple[str, Ed25519PrivateKey]     # (huella, llave privada)
momento_efectivo() -> datetime
situacion() -> Situacion
permite_escribir() -> bool            # situacion().estado != "solo_consulta"
instalar(documento: dict) -> Situacion
anotar_revocacion(documento: dict) -> None
activar(codigo: str) -> str
renovar() -> str
tarea_renovar(...)                    # con la firma que usan las funciones de TAREAS
```

**Reloj propio** (`momento_efectivo`): el programa lleva su propia cuenta del tiempo, `mayor_momento`, que suma solo avances del reloj del equipo. `a = reloj.ahora()`, `avance = a - ultimo_reloj`, `efectivo = mayor_momento + max(avance, 0)`. Un atraso no resta ni congela: la cuenta sigue desde donde iba. Si `avance < -TOLERANCIA_RELOJ`, auditoría `reloj_atrasado` (a lo más una cada 6 h). Si `avance != 0` (`PASO_RELOJ` vale cero: se guarda en cada lectura con hora distinta, con actualización condicional para que dos lecturas a la vez no se pisen), guarda `mayor_momento = efectivo` y `ultimo_reloj = a`. Devuelve `efectivo`. Así, atrasar el reloj nunca regala tiempo ni lo congela.

**`situacion()`**, en orden (sin caché entre llamadas; vuelve a verificar la firma de lo guardado cada vez):
1. `llaves.publicas()` vacío → `libre` (programa sin llaves: las licencias están apagadas).
2. Hay `revocacion` guardada, válida (`abrir(..., "revocacion")`), con `instalacion == huella` local y `emitida` ≥ la `emitida` de la licencia guardada (si hay) → `solo_consulta`, motivo `revocada`.
3. Hay `documento` válido (`abrir(..., "licencia")`) con `instalacion == huella` local. Con `t = momento_efectivo()`, `vence`, y `limite = vence + dias_gracia días`: `t ≤ vence` → `vigente`; `t ≤ limite` → `gracia`; si no → `solo_consulta`, motivo `vencida`.
4. Sin documento válido: `limite = primer_arranque + DIAS_PARA_ACTIVAR días`; `t ≤ limite` → `por_activar`; si no → `solo_consulta`, motivo `sin_licencia`.
`motivo` es `""` fuera de `solo_consulta`. Un documento guardado que ya no verifica (alterado en la base) cuenta como que no hay.

**`instalar(documento)`**: `abrir(documento, llaves.publicas(), "licencia")`; además `LicenciaInvalida("ajena")` si `instalacion` no es la huella local y `LicenciaInvalida("antigua")` si su `emitida` es anterior a la de la licencia ya guardada. Si se rechaza: no cambia nada guardado y registra `licencia_rechazada` con `{"motivo": …}`. Si se acepta: guarda el documento, `mayor_momento = max(mayor_momento, emitida)` (y, si la cuenta sube, `ultimo_reloj = reloj.ahora()`), borra la `revocacion` guardada si su `emitida` es anterior, registra `licencia_instalada` y devuelve `situacion()`.

**`anotar_revocacion(documento)`**: `abrir(..., "revocacion")`; `ajena` si no es de esta instalación; `antigua` si su `emitida` es anterior a la de la licencia guardada. Rechazo: nada cambia y `licencia_rechazada`. Aceptada: se guarda y `licencia_revocada`.

**`cliente.enviar(ruta, cuerpo)`**: POST JSON a `settings.CENTRAL_URL + ruta` con `urllib.request` y `ssl.create_default_context()`, tiempo límite 15 s, respuesta ≤ 64 KB y debe ser un objeto JSON. `CENTRAL_URL` sale de la clave `central` de `configuracion.json` de la instancia (por omisión `""`); solo se acepta `https://`. Vacía, sin https, error de red, tiempo, tamaño o JSON inválido → `SinConexion`. En `ajustes_pruebas`: `CENTRAL_URL = "https://central.invalid"`. `servicios` lo llama siempre como `cliente.enviar(...)` (las pruebas lo sustituyen).

**Petición firmada** (para ambas rutas): carga de tipo `renovacion` o `activacion` con `instalacion = huella`, `momento = texto_de(momento_efectivo())` (la cuenta propia), `sello = secrets.token_hex(16)`, `version` = versión instalada; se firma con la llave de la instalación.

**`renovar()`** devuelve uno de: `apagada` (sin llaves públicas), `sin_conexion`, `renovada`, `pago_pendiente`, `revocada`, `rechazada`. Envía a `/v1/renovar` `{"instalacion": huella, "carga": …, "firma": …}`. Guarda `ultimo_intento` y `ultimo_resultado`. Respuesta 200 con `resultado`: `renovada` → `instalar(documento)`; `revocada` → `anotar_revocacion(documento)`; `pago_pendiente` → nada. Si el documento recibido no pasa (`LicenciaInvalida`) o el estado no es 200 → `rechazada`. Nunca deja salir una excepción.

**`activar(codigo)`** devuelve `apagada`, `sin_conexion`, `activada`, `pago_pendiente` o `rechazada`. Envía a `/v1/activar` `{"codigo": codigo, "llave_publica": "<base64 de los 32 bytes>", "carga": …, "firma": …}` (carga de tipo `activacion`). `activada` → `instalar(documento)`. Con `activada` o `pago_pendiente` se guarda `Instalacion.activada = True`.

**`tarea_renovar`**: se agrega a `TAREAS` de `configuracion/trabajador.py` como `("licencia", …, False)`. Llama a `renovar()` solo si la instalación ya se activó en Central (`activada`) y `ultimo_intento` es nulo o tiene más de `HORAS_ENTRE_RENOVACIONES`.

#### Candado: `licencias.middleware.Candado`

Si el método no es `GET`, `HEAD` ni `OPTIONS`, la ruta resuelta no está en `LIBRES` y `not permite_escribir()` (en ese orden: entrar, salir y respaldar funcionan aunque la licencia o sus llaves estén dañadas): responde **403**, `Content-Type: text/plain; charset=utf-8`, cabecera **`X-Ariasmos-Licencia: solo-consulta`** y un texto en palabras llanas (la licencia venció; se puede consultar y exportar; no se pueden registrar movimientos; cómo reactivar). En cualquier otro caso deja pasar y no añade la cabecera.

`LIBRES` (conjunto de nombres de ruta, en `middleware.py`): solo lo indispensable para entrar y salir (inicio de sesión, segundo paso con código, cerrar sesión, confirmar contraseña, registro del equipo si hace falta para entrar) y para sacar los datos: `respaldos:respaldar` y `respaldos:probar`. Nada de cobros, altas, ediciones, caja, banco, inventario ni configuración. Todo lo que se descarga por GET sigue funcionando.

#### Trabajador

En `configuracion/trabajador.py`: si `not licencias.servicios.permite_escribir()`, el ciclo **omite** (sin marcarlas como falla) las tareas que escriben datos del negocio: `generar_cargos`, `generar_recargos`, `carpeta_banco`, `generar_cortes_mayores`, `cerrar_cortes_vencidos`, `entregar_cortes`, `caducar_solicitudes`. Siguen corriendo: `respaldo`, `prueba_respaldo`, `verificar_bitacora`, `actualizaciones`, `licencia`, `depurar_*`, `cifrar_secretos`, `lista_cobranza`.

#### Auditoría (con `auditoria.servicios.registrar`)

`licencia_instalada` (`serie`, `vence`), `licencia_rechazada` (`motivo`), `licencia_revocada`, `reloj_atrasado`. Nunca llaves, códigos ni documentos completos.

#### Comandos

- `python manage.py licencia_activar <código>`: llama a `activar` y dice el resultado en palabras llanas.
- `python manage.py licencia_estado`: estado, vencimiento y fin de la gracia en palabras llanas.

### Ariasmos Central: carpeta `central/`

Proyecto Django aparte. `central/manage.py` mete la raíz del repo en `sys.path` (para `nucleo`) igual que `sistema/manage.py`. `pytest.ini`: `pythonpath = . sistema central`.

| Ruta | Contenido |
|---|---|
| `central/proyecto_central/` | `ajustes.py`, `ajustes_pruebas.py`, `urls.py`, `wsgi.py`, `instancia.py` |
| `central/emision/` | app: `models.py`, `ajustes.py`, `llave.py`, `reloj.py`, `origen.py`, `servicios.py`, `views.py`, `urls.py`, `migrations/`, `management/commands/` |
| `central/requirements.txt` | Django, cryptography y waitress con las mismas versiones fijas del programa (más sus dependencias) |

**Ajustes.** `INSTALLED_APPS = ["emision"]`; middleware mínimo (`SecurityMiddleware`, `CommonMiddleware`); sin sesiones, sin auth, sin admin, sin CSRF (no hay cookies; todo va firmado). `DEBUG = False` siempre. La instancia vive en la carpeta de la variable `CENTRAL_INSTANCIA`, con `configuracion.json`: `clave_django`, `base_datos`, `hosts`, `proxies_confiables` (vacía en una instancia nueva), `llave_licencias` (ruta del archivo PEM PKCS8 de la llave privada; por omisión `<instancia>/llave-licencias.pem`, permisos 0600). SQLite con los mismos ajustes que el programa (WAL, IMMEDIATE, llaves foráneas). Ajustes expuestos: `RUTA_LLAVE_LICENCIAS`, `PROXIES_CONFIABLES`. `ajustes_pruebas.py`: base temporal por PID, llave efímera generada al importar en carpeta temporal, `ALLOWED_HOSTS = ["testserver"]`, `PROXIES_CONFIABLES = []`.

**`emision/llave.py`**: `privada()` (lee `settings.RUTA_LLAVE_LICENCIAS`), `publica() -> bytes` (32 crudos). **`emision/reloj.py`**: `ahora()`, única fuente de hora, llamada siempre como `reloj.ahora()`.

**`emision/ajustes.py`**: modelo `Ajuste(clave, valor)` + catálogo `AJUSTES = {"dias_vigencia": 30, "dias_gracia": 14, "dias_codigo": 7, "minutos_tolerancia": 10, "rechazos_por_hora": 30}`; `valor(clave) -> int` (guardado o el de catálogo). Cada ajuste tiene un rango válido junto a su valor por omisión (`dias_vigencia` 1–366, `dias_gracia` 0–90, `dias_codigo` 1–90, `minutos_tolerancia` 1–60, `rechazos_por_hora` 1–10000); un valor guardado fuera de rango se ignora y se usa el del catálogo. Nada de esto va fijo en otra parte.

**Modelos (`emision/models.py`)**

| Modelo | Campos |
|---|---|
| `Negocio` | `id` UUID (pk), `nombre` (≤120), `contacto` (≤200, vacío), `plan` (≤40, `"base"`), `modulos` (JSON, lista), `instalaciones_permitidas` (entero, 1), `pagado_hasta` (fecha, nulo), `revocado` (bool), `creado` |
| `CodigoActivacion` | `negocio` FK, `resumen` (sha256 hex del código normalizado, único), `vence`, `usado` (nulo) |
| `Instalacion` | `negocio` FK, `huella` (64, única), `llave_publica` (base64), `activada`, `revocada` (bool), `serie` (entero, 0), `ultima_renovacion` (nulo), `ultima_version` (≤20, vacío) |
| `Sello` | `instalacion` FK, `valor` (32), `momento`; único (`instalacion`, `valor`) |
| `Rechazo` | `origen` (≤64, con índice), `momento` (con índice) |
| `Bitacora` | `momento`, `accion` (≤40), `negocio` FK nulo, `origen` (≤64, vacío), `datos` JSON |
| `Ajuste` | `clave` única, `valor` entero |

**`emision/servicios.py`**

```
crear_negocio(nombre, contacto="", plan="base", modulos=(), instalaciones=1) -> Negocio
crear_codigo(negocio) -> str            # devuelve el código una sola vez; guarda solo su resumen
registrar_pago(negocio, hasta: date) -> None
revocar(negocio, huella=None, deshacer=False) -> None   # sin huella: todo el negocio
emitir(instalacion) -> dict             # documento de licencia firmado
```

- **Código de activación**: 20 caracteres del alfabeto `0123456789ABCDEFGHJKMNPQRSTVWXYZ` generados con `secrets`, mostrados `XXXXX-XXXXX-XXXXX-XXXXX`. Normalizar = mayúsculas y quitar guiones y espacios. Vence a los `dias_codigo` días. Un solo uso, salvo la repetición del mismo equipo (ver «Activación repetible»).
- **`emitir`**: `serie = instalacion.serie + 1` (se guarda); `emitida = reloj.ahora()`; `vence = min(emitida + dias_vigencia días, las 23:59:59 UTC de pagado_hasta)`; `dias_gracia` del ajuste; `plan` y `modulos` del negocio; firma con `llave.privada()`; anota `licencia_emitida` en la bitácora.
- **Pago al corriente** = `pagado_hasta` no nulo y ≥ la fecha UTC de hoy.

**API (`emision/views.py`, `urls.py`)** — todas responden JSON con `Cache-Control: no-store`.

| Ruta | Qué hace |
|---|---|
| `GET /v1/salud` | 200 `{"estado":"ok","hora":"…Z"}` (hora de Central, sin firma) |
| `POST /v1/activar` | activa una instalación con un código |
| `POST /v1/renovar` | renueva la licencia de una instalación |

Reglas comunes a las dos POST, en este orden:
1. Otro método → 405.
2. Origen (`origen.de(request)`: `REMOTE_ADDR`; si es un proxy de `PROXIES_CONFIABLES`, el último salto no confiable de `X-Forwarded-For`, solo si es una dirección válida; si no, `REMOTE_ADDR`; las direcciones IPv6 se agrupan por su red /64) con `rechazos_por_hora` o más filas en `Rechazo` en la última hora → **429** `{"error":"espera"}`, sin procesar nada más.
3. Cuerpo > 16 KB → **413** `{"error":"peticion"}`. No es un objeto JSON, faltan o sobran campos, o tipos equivocados → **400** `{"error":"peticion"}`.
4. Cualquier otro rechazo → **403** `{"error":"rechazada"}`, **idéntico sea cual sea la causa**.
5. Toda respuesta 400, 403 y 413 agrega una fila a `Rechazo` y una entrada de bitácora con la causa (sin códigos, llaves ni cuerpos). En cada POST se borran las filas de `Rechazo` con más de una hora. Un `Host` no permitido, una ruta inexistente o una variante con barra final responden también JSON `{"error":"peticion"}` (400 o 404), sin HTML, y agregan su fila a `Rechazo`.
6. Ninguna entrada hostil produce 500 ni devuelve trazas, rutas internas o la llave privada.

`POST /v1/renovar` — cuerpo `{"instalacion","carga","firma"}`:
- Busca `Instalacion` por `instalacion`; `abrir({"carga","firma"}, [su llave pública], "renovacion")`; la `instalacion` de la carga debe ser la misma; `momento` a no más de `minutos_tolerancia` minutos de `reloj.ahora()`; inserta el `Sello` (si ya existía → repetición). Cualquier fallo → 403. Borra sellos con más del doble de la tolerancia.
- Instalación o negocio revocados → 200 `{"resultado":"revocada","documento":<revocación firmada con emitida = ahora>}`.
- Sin pago al corriente → 200 `{"resultado":"pago_pendiente"}`.
- Si no → 200 `{"resultado":"renovada","documento":<licencia>}`; guarda `ultima_renovacion` y `ultima_version`.

`POST /v1/activar` — cuerpo `{"codigo","llave_publica","carga","firma"}` (`codigo` texto ≤ 40; `llave_publica` base64 de 32 bytes):
- `abrir({"carga","firma"}, [llave_publica], "activacion")`; la `instalacion` de la carga debe ser `huella(llave_publica)`; `momento` dentro de la tolerancia.
- El resumen del código normalizado existe, no está usado ni vencido; el negocio no está revocado; la huella no existe ya; las instalaciones no revocadas del negocio son menos que `instalaciones_permitidas`. Cualquier fallo → 403.
- En una sola transacción: marca el código usado (actualización condicional `usado IS NULL`, que debe afectar 1 fila) y crea la `Instalacion`. Dos peticiones a la vez con el mismo código: solo una gana.
- Con pago al corriente → 200 `{"resultado":"activada","documento":<licencia>}`; sin pago → 200 `{"resultado":"pago_pendiente"}` (la instalación queda creada y el código gastado).

**Comandos del dueño** (`central/emision/management/commands/`), con salida en palabras llanas:
`inicializar_central --carpeta <ruta>` (crea la instancia, la configuración y el par de llaves; imprime la llave **pública** en base64 para `sistema/licencias/llaves.json`; si ya existe, no la pisa) · `negocio_nuevo --nombre … [--contacto …] [--plan …] [--instalaciones N]` · `codigo_activacion <id del negocio>` · `registrar_pago <id> --hasta AAAA-MM-DD` · `revocar <id> [--instalacion <huella>] [--deshacer]` · `negocios` (lista: nombre, pagado hasta, instalaciones, última renovación, versión).

### Reloj propio, acuse y hora de Central

- **Acuse de Central**: documento firmado de tipo `acuse` con `("formato","producto","tipo","instalacion","sello","hora")`. Central lo incluye como `"acuse"` en toda respuesta 200 de `/v1/renovar` y `/v1/activar` (con la huella de quien pide, el sello de esa petición y su hora). Claves por resultado: `renovada` y `activada` traen `resultado`, `documento` y `acuse`; `pago_pendiente`, `resultado` y `acuse`; `revocada`, `resultado`, `documento` y `acuse`. Así un cliente que no paga también recibe la hora firmada. El programa aplica el acuse igual con cualquier resultado, antes de procesar el resto.
- **El programa aplica el acuse** antes de instalar el documento, solo si abre con la llave de Central, es de esta instalación y trae el mismo sello que se acaba de enviar: la cuenta propia pasa a la hora de Central (hacia adelante o hacia atrás) y, si el cambio supera `TOLERANCIA_RELOJ`, se registra `reloj_ajustado` con `{"antes","despues"}`. Sin acuse no cambia nada; con un acuse que no pasa no se toca la cuenta, se registra `licencia_rechazada` con motivo `acuse` y el resto de la respuesta se procesa igual. Solo un acuse puede bajar la cuenta.
- **Equipo con la hora mal puesta**: si Central contesta 403, el programa pide `cliente.hora_central()` (GET a `/v1/salud`, 5 s; cualquier falla da `None`). Si la hora difiere del `momento` enviado en más de `DESFASE_PARA_REINTENTO` (2 min), reenvía **una sola vez** con esa hora y un sello nuevo. Esa hora no está firmada: solo fecha la petición y nunca toca la cuenta.
- `renovar()` y `activar()` marcan `activada = True` cuando Central contesta 200. La tarea de renovación intenta si la instalación está activada y no hay `ultimo_intento`, o este está en el futuro, o pasaron `HORAS_ENTRE_RENOVACIONES`, o pasaron esas horas de **tiempo real** del proceso (`reloj.transcurrido()`, un reloj monotónico, contra `servicios.ultimo_intento_real`, que vale `None` al arrancar: la primera llamada solo lo fija). Así un reloj detenido no impide seguir preguntando a Central.
- Con `llaves.json` dañado, `renovar()`, `activar()` y la tarea responden `llaves`, y los comandos lo explican en palabras llanas.

### Activación repetible y límite de rechazos (Central)

- **Activación repetible**: `CodigoActivacion.instalacion` se llena al usarse el código. Si el mismo equipo (misma huella, firma y hora válidas) repite la activación con su código, aún no vencido, y ni la instalación ni el negocio están revocados, Central responde como la primera vez (licencia nueva con `serie` mayor y acuse, o `pago_pendiente`) sin crear otra instalación ni contar un rechazo. Otro equipo, código vencido o revocación: 403.
- **Una renovación auténtica no se frena por el límite**: en `/v1/renovar`, si el origen está sobre el límite se comprueba primero que la petición sea auténtica (cuerpo bien formado, instalación conocida, firma, hora y sello nuevo); si lo es, se atiende normal; si no, 429 sin escribir nada. `/v1/activar` conserva el 429 primero.
- **Deshacer una cancelación respeta el tope**: `revocar(..., deshacer=True)` de un equipo lanza `TopeDeInstalaciones`, sin cambiar nada, si el negocio quedaría con más equipos activos de los permitidos; el comando lo explica en palabras llanas.
- **Rutas ajenas** (inexistentes, variantes de barra, `Host` no permitido): bajo el límite, 4xx con una fila en `Rechazo` y nada en `Bitacora`; sobre el límite, 429 sin escribir nada.
- `inicializar_central` calcula la ruta de la llave igual que los ajustes (clave ausente o vacía: la ruta por omisión). Con configuración ilegible, JSON roto o una ruta que no es un archivo de llave, termina con un aviso en palabras llanas y no genera llaves.

### Límites conocidos

- Restaurar un respaldo en otra computadora copia la identidad del equipo (dos equipos, un cupo). Se avisará en el panel del dueño (fase 1b).
- Quien tiene permisos de administrador en la computadora (los mismos que hacen falta para cambiar la hora del sistema) puede todavía sincronizar regresos del reloj con las lecturas del programa, detener el servicio o vaciar el archivo de llaves. La defensa real es que Central deja de renovar y de dar actualizaciones.
- Quien controla por completo el equipo (base de datos, archivos del programa, red) puede saltarse la licencia o estirar el plazo sin conexión apagando el servicio y atrasando el reloj; con conexión, cada renovación vuelve a poner la hora de Central.

### Lista cerrada de ataques (la fase debe aguantar los 21)

1. **Licencia alterada**: cambiar `vence`, `plan` o `modulos` de una licencia válida → se rechaza y nada cambia.
2. **Licencia con otra llave**: bien formada pero firmada con una llave que no es de Central → se rechaza.
3. **Licencia ajena**: licencia auténtica de otra instalación u otro negocio → se rechaza.
4. **Reloj atrasado**: con la licencia vencida y la gracia agotada, atrasar el reloj del equipo no devuelve el permiso de escribir; queda en auditoría.
5. **Saltarse el candado**: en solo consulta, las rutas que escriben (cobro, alta, edición) llamadas directo responden 403 con la cabecera del candado y no escriben nada; consultar, descargar, entrar y respaldar siguen funcionando. En gracia todo funciona.
6. **Renovación falsificada**: firma inválida, firma de otra instalación, petición repetida (mismo sello) o con hora vieja → 403 sin emitir.
7. **Renovar sin derecho**: sin pago al corriente o revocado, Central no emite licencia; y una «revocación» sin firma válida de Central no bloquea al negocio.
8. **Código de activación**: inventado, vencido o reutilizado → 403; tras muchos rechazos desde el mismo origen → 429.
9. **Entradas hostiles a Central**: cuerpo gigante, JSON roto, tipos equivocados, campos de más, texto de inyección → 4xx, nunca 500, y la llave privada no aparece en respuestas ni en la bitácora.
10. **Más instalaciones de las permitidas**: un segundo equipo con otro código del mismo negocio, con el tope en 1 → 403.
11. **Congelar la licencia**: atrasar el reloj (una vez mucho o muchas veces poco) no impide que la licencia venza cuando el reloj vuelve a avanzar lo que faltaba.
12. **Acuse falso**: un acuse firmado con otra llave, de otra instalación o con un sello distinto al enviado no mueve la cuenta; uno auténtico sí cura un adelanto por error del reloj.
13. **Hora mal puesta**: un equipo con el reloj equivocado renueva al segundo intento con la hora de Central, y la tarea intenta aunque `ultimo_intento` esté en el futuro.
14. **Activación a medias**: el mismo equipo repite la activación con el mismo código y recibe la misma respuesta, sin instalación nueva; otro equipo con ese código sigue rechazado.
15. **Límite de rechazos**: desde un origen sobre el límite, una renovación auténtica pasa; una falsa recibe 429 y no escribe nada.
16. **Acuse de Central**: `renovada` y `activada` traen un acuse con la llave de Central, el sello de la petición y su hora; `pago_pendiente` no cambia; `/v1/salud` trae la hora.
17. **Llenar el disco**: las rutas inexistentes desde un origen sobre el límite reciben 429 sin filas nuevas; las rutas ajenas nunca escriben en `Bitacora`.
18. **Reloj oscilante**: regresar el reloj cada pocos minutos, muchas veces, no detiene la cuenta; lo que el reloj avanzó entre regresos se suma.
19. **Sin pago y en línea**: Central manda acuse en `pago_pendiente` y en `revocada`; un acuse auténtico pone la cuenta a la hora de Central y uno falso no la mueve.
20. **Reloj detenido**: con el reloj sin avanzar, la tarea vuelve a preguntar a Central cuando pasan las horas de tiempo real.
21. **Deshacer sobre el tope**: con tope 1, cancelar el equipo A, activar el B y deshacer la cancelación de A se rechaza y todo queda igual.

### Plan de datos

- No se mueve ni cambia ningún dato del MVP. Migración única: tabla nueva de `licencias`.
- Un programa sin llaves en `llaves.json` queda `libre`: actualizar el MVP no puede bloquear a nadie por accidente.
- La llave pública real de Central la pone Máximo después de correr `inicializar_central` en su servidor. La privada nunca sale de Central ni entra al repositorio.

## Versión 1.0: permiso para ver lo que entra (fase 13)

Los niveles bajos no ven cuánto entra salvo que un nivel superior se lo conceda. El permiso nuevo es `ver_ingresos` y se decide en un solo lugar: `cuentas.permisos.ve_ingresos(usuario)`, que usa `tiene_permiso` (cuenta delegaciones vigentes y no gasta usos).

- **Catálogo.** Está en `PERMISOS` y en `DELEGABLES`; la regla de no dar lo que no se tiene por el papel no cambia. Las seis plantillas lo dan a los papeles que ya tienen `ver_cortes`.
- **Instalaciones existentes.** La migración `cuentas/0011_ver_ingresos` lo agrega a todo papel con `ver_cortes` y registra un evento `permiso_agregado` por papel; la inversa lo quita de todos.
- **Lo último que entró** (`/ultimo/`, inicio, aviso y campana). Sin el permiso el servidor no manda el importe de cobros ajenos, ni en el HTML ni en `data-aviso`. El cobro propio sí lo muestra, salvo con turno abierto (conteo ciego).
- **Banco.** La cola, el detalle de un movimiento y proponer una identificación exigen `ver_ingresos` además del permiso que ya pedían (decorador `requiere_ingresos`); el menú no ofrece la cola a quien no puede abrirla.
- **Inventario.** Sin el permiso, la lista de ventas solo trae las propias; el detalle y la devolución de una venta ajena dan 403.
- No hay tablas, pantallas ni rutas nuevas. Totales, cortes, custodia, retiros e importaciones siguen protegidos por sus permisos de siempre.
- **Vuelta 1.** Sin el permiso, el recibo, su PDF y la reversión solo sirven para pagos que registró la propia persona (la verificación por código no cambia). La lista, el detalle y las acciones de importaciones del banco exigen `ver_ingresos`, y la pantalla de topes no muestra lo aplicado. `ver_ingresos` solo se presta por días, nunca solo por usos, y la migración inversa retira también sus delegaciones. El buscador y el tablero no ofrecen enlaces a la cola sin el permiso. El historial de pagos de un cliente no cambia.
- **Enter hace la acción principal.** En todo formulario con más de un botón de envío, el primero del documento es la acción principal (un botón `.envio-por-omision`, fuera de la vista, justo después del token), nunca «Atrás» ni «Omitir por ahora»; así Enter en un campo no regresa ni salta un paso. El asistente conserva el secreto del autenticador al ir y venir con la misma persona.
