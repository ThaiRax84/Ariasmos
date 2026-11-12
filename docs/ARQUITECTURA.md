# Arquitectura — Sistema de cobro y control de titulares

Versión 0.1 · 12/11/2026 · Estado: base aprobada para construir la Fase 1.

Este documento es la especificación. Quien construye sigue lo que dice aquí; cualquier cambio de diseño se propone primero y se implementa después.

## 1. Qué es

Un sistema local, multiusuario y configurable que:

1. Lleva el padrón de **titulares** (en una escuela: alumnos) y le da a cada uno una **matrícula única** que sirve como referencia de pago.
2. Genera **cargos** (inscripción, mensualidad, recargos, extras…) según categorías que el negocio define.
3. Registra **pagos** en efectivo y por banco, y los aplica solos a la cuenta del titular cuando la matrícula viene en la transferencia.
4. Controla el **efectivo** con caja, arqueo ciego y cadena de custodia.
5. Emite **cortes** periódicos (menor y mayor) y los entrega a los destinos configurados.

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

- Numérica y de **7 dígitos** por defecto, porque la referencia numérica de un SPEI admite hasta 7. Longitud configurable de 5 a 12 al instalar.
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
| `cuentas` | Usuario, Rol, PermisoRol, Dispositivo, Delegacion, CodigoUsado | §6. |
| `titulares` | Titular, Contacto, Agrupacion, MotivoBaja | Estados: `pendiente`, `activo`, `baja`, `rechazado`. |
| `solicitudes` | Solicitud, PoliticaAccion | Motor genérico de aprobación. |
| `cobros` | ConceptoCobro, ReglaRecargo, PlanCobro, Cargo, Pago, Aplicacion, Recibo | Libro inmutable. |
| `caja` | Caja, Turno, Arqueo, Traslado | Custodia del efectivo. |
| `banco` | CuentaBancaria, Importacion, MovimientoBancario, ReglaPagador | Adaptadores de entrada. |
| `reportes` | DefinicionCorte, Corte, Destino | Frecuencias y destinos configurables. |
| `auditoria` | Evento | Solo inserción, encadenado por hash. |
| `respaldo` | Respaldo | Bitácora de copias y pruebas de restauración. |

### 5.1 Libro de cobros

- **ConceptoCobro** (categoría): nombre, tipo (`unico`, `recurrente`, `por_evento`), importe por defecto, periodicidad, día de vencimiento, regla de recargo, a quién aplica (`nuevos`, `todos`, `agrupacion`, `manual`), prioridad de aplicación, activo.
- **ReglaRecargo**: fijo o porcentaje, días de gracia, se repite o no, tope.
- **PlanCobro**: liga un concepto recurrente a un titular, con importe o descuento propio y vigencia.
- **Cargo**: titular, concepto, periodo, importe, vencimiento, origen (`automatico`, `manual`, `recargo`), estado derivado (`pendiente`, `parcial`, `pagado`, `cancelado`).
- **Pago**: titular, importe, medio (`efectivo`, `banco`, otros configurables), fecha, origen (turno de caja o movimiento bancario), estado (`aplicado`, `revertido`).
- **Aplicacion**: reparte un pago entre cargos. Lo que sobra queda como saldo a favor.
- **Recibo**: folio consecutivo por serie, inalterable, con código de verificación.

Orden de aplicación por defecto (configurable): recargos, luego cargos por vencimiento más antiguo, luego por prioridad del concepto.

Nada se edita ni se borra: una cancelación crea el asiento inverso y deja ambos visibles.

### 5.2 Plantilla «escuela»

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
| Ver cortes / cerrar cortes | ver | ✓ | ✓ |
| Aprobar dispositivos | — | ✓ | ✓ |
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

## 7. Efectivo

Objetivo: que Operación cobre sin esperar a nadie y que cada billete tenga dueño en todo momento.

1. **Turno.** Quien cobra abre un turno en su caja. Un turno, una persona.
2. **Cobro.** Registra el pago; el sistema lo aplica al titular de inmediato y emite un recibo foliado. El pago queda como «efectivo en caja».
3. **Arqueo ciego.** Al cerrar, captura lo que contó por denominación **sin ver** lo esperado. El sistema calcula la diferencia. Si supera el umbral configurado, pide una nota y avisa a Supervisión. No bloquea el cierre.
4. **Traslado.** El efectivo sale de la caja de dos formas:
   - **Entrega** a Supervisión: quien recibe confirma el importe con su propia sesión (doble firma).
   - **Depósito** bancario: se registra con su importe y fecha; la conciliación lo cierra cuando aparece en el banco.
5. **Alertas.** Efectivo que lleva más días de los configurados sin entregar o depositar, depósitos que no aparecen en el banco, cancelaciones de recibos y diferencias repetidas aparecen en el tablero de Supervisión.

Cadena de custodia: `caja → resguardo → banco`. En todo momento el sistema sabe cuánto efectivo debería tener cada persona.

## 8. Banco y conciliación

### 8.1 Entrada de movimientos

Hoy no existe en México una API bancaria abierta y gratuita para leer los movimientos de una cuenta propia. Por eso la entrada es por **adaptadores**:

| Adaptador | Costo | Cómo llega | Estado |
|---|---|---|---|
| `archivo` | Gratis | Se sube el archivo de movimientos de la banca en línea, o se deja en una carpeta vigilada | Fase 3 |
| `estado_pdf` | Gratis | Estado de cuenta mensual en PDF | Fase 3, respaldo |
| `correo` | Gratis | Avisos de abono leídos del buzón | Posterior, si el banco los envía con concepto |
| `convenio` | De pago | Archivo diario de cobranza referenciada | Posterior |
| `clabe_virtual` | De pago | Una CLABE por titular vía proveedor, por consulta periódica | Posterior |

El adaptador `archivo` no depende de un formato fijo: detecta encabezados y columnas por nombre y contenido (fecha, descripción, referencia, cargo, abono, saldo) y guarda la correspondencia aprendida por cuenta. Subir el archivo es el único paso manual; todo lo demás es automático.

Cada movimiento lleva una **huella** (cuenta, fecha, importe, referencia, descripción normalizada y ordinal dentro del día) para que reimportar el mismo archivo no duplique nada.

### 8.2 Identificación

Para cada abono:

1. **Extraer.** Se buscan en referencia y concepto todas las secuencias de `L` dígitos (también partidas por espacios o guiones) que pasen el dígito verificador.
2. **Decidir.**
   - Una sola matrícula válida y existente → **aplicación automática**.
   - Ninguna válida → se buscan matrículas existentes a un error de distancia (dígito cambiado, faltante, sobrante o intercambiado) y se ordenan por coincidencia de importe con lo que debe el titular y por historial del pagador. Va a la cola «por identificar» como sugerencia.
   - Varias válidas o ninguna pista → cola «por identificar» sin sugerencia.
3. **Aprender.** Cuando una persona confirma a quién pertenece un abono, se guarda una `ReglaPagador` (cuenta u ordenante → titular). Tras el número de confirmaciones configurado, los siguientes abonos de ese pagador se sugieren en primer lugar; solo se aplican solos si la política lo permite.
4. **Aplicar.** El pago se reparte según §5.1.

Operación puede sugerir la identificación; Supervisión la confirma. Los depósitos de efectivo de §7 se emparejan contra los traslados registrados, no contra titulares.

## 9. Cortes y reportes

Un **corte** es una definición configurable: nombre, frecuencia, alcance, si cierra periodo y a qué destinos va. La plantilla «escuela» trae dos:

| Corte | Frecuencia | Cierra periodo | Contenido |
|---|---|---|---|
| Menor | Semanal | No | Ingresos por medio y concepto, estado de caja, movimientos por identificar, adeudos vencidos |
| Mayor | Mensual | Sí | Todo lo anterior, más una fila por titular con el estado de cada concepto (pagado, parcial, adeudo), antigüedad de saldos, altas y bajas, y conciliación banco–efectivo |

Flujo: el sistema genera el corte solo en la fecha indicada y lo deja como borrador. Supervisión lo revisa y lo cierra con un clic. Si nadie lo cierra en el plazo configurado, se entrega marcado «sin revisar» para no detener a nadie. Al cerrar un corte que cierra periodo, ese periodo queda bloqueado: los ajustes posteriores entran en el periodo siguiente.

**Destinos** (enchufables): `carpeta` (PDF + CSV + JSON con un `manifiesto.json`), y `correo` más adelante. Cada destino define su nivel de detalle (`completo`, `sin_nombres`). Un agente externo puede leer la carpeta; el sistema no depende de ningún agente.

Cada archivo de corte lleva un hash firmado con la clave de la instalación para detectar alteraciones.

## 10. Seguridad

| Capa | Medida |
|---|---|
| Red | El servicio escucha solo en la red local; regla de firewall limitada a esa subred; TLS con autoridad interna cuyo certificado se instala en cada computadora autorizada. |
| Dispositivos | Solo entran **computadoras aprobadas**. Un navegador nuevo queda «pendiente» hasta que Supervisión o Dirección lo aprueba; recibe una credencial de dispositivo de larga duración (cookie `HttpOnly`, `Secure`, `SameSite=Strict`; en la base solo su hash). Se puede revocar. La primera se aprueba desde el propio servidor al instalar. |
| Identidad | Una cuenta por persona. Argon2id. Bloqueo progresivo tras intentos fallidos. Cierre por inactividad configurable por rol. TOTP obligatorio para quien aprueba. Reingreso de contraseña antes de acciones delicadas. |
| Aplicación | Permiso verificado en el servidor en cada vista y sobre cada objeto. CSRF activo. CSP sin scripts en línea ni orígenes externos. Solo ORM. Límite de peticiones en inicio de sesión y códigos. |
| Archivos | Los archivos subidos se leen, nunca se ejecutan; tamaño y tipo limitados; se guardan fuera de la carpeta pública. Las exportaciones neutralizan celdas que empiezan con `=`, `+`, `-`, `@`. |
| Integridad | Libro inmutable. Cada evento de auditoría guarda `hash(evento anterior ‖ contenido)`; una tarea diaria verifica la cadena. Periodos cerrados bloqueados. |
| Secretos | Carpeta `instancia/` fuera del repo, con permisos restringidos a la cuenta del servicio: clave de Django, clave de matrícula, clave de respaldo. |
| Respaldo | Copia diaria consistente de la base, cifrada con AES-256-GCM, hacia una carpeta sincronizada fuera del equipo. Retención 30 diarias y 12 mensuales. Prueba de restauración automática mensual. La clave de recuperación se imprime al instalar. |
| Privacidad | Datos mínimos; vistas limitadas por rol; toda exportación queda registrada; aviso de privacidad y consentimiento del tutor fuera del sistema, con casilla de constancia en el alta. |

Pruebas de seguridad previstas antes de cada entrega: matriz completa URL × rol, acceso a objetos ajenos, CSRF, fijación de sesión, fuerza bruta, autoaprobación, reutilización de código, delegación vencida, manipulación del libro, archivos maliciosos, inyección en exportaciones y concurrencia en contador de matrícula, folios e importaciones.

## 11. Configuración e instalación

- **Asistente de primer uso:** nombre del negocio, vocabulario (cómo se llama al titular, a la matrícula, a las agrupaciones), plantilla, conceptos e importes, roles, políticas de aprobación, cajas, cuenta bancaria, cortes y destinos, respaldo. Crea al primer usuario de Dirección y aprueba el primer dispositivo.
- **Todo editable después** por quien tenga el permiso: Supervisión administra conceptos de cobro; Dirección lo demás.
- **Repo sin datos:** `instancia/`, bases, respaldos y documentos internos están en `.gitignore`. Descargar el repo da el motor, las plantillas y el asistente, nada más.
- **Instalación en Windows:** script que crea el entorno, genera claves, registra los dos servicios (web y trabajador) con reinicio automático y abre el asistente.

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
| 2 | Cargos automáticos y recargos, pagos en efectivo, recibos, caja y traslados |
| 3 | Importación bancaria, identificación y conciliación |
| 4 | Cortes, destinos, respaldo, instalador y guías |

## 14. Pendientes de decisión

1. Formato real del archivo de movimientos del banco: hace falta una muestra para afinar el adaptador.
2. Si el negocio contrata cobranza referenciada: longitud y dígito verificador que exija el banco.
3. Facturación (CFDI): fuera del alcance de esta versión.
4. Varias sedes: hoy una instalación por sede con `sede` distinta; la consolidación central se diseña cuando exista la segunda.
