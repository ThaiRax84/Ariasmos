# Formato: estado de cuenta en PDF, cuenta Santander PyME

Descripción del formato para el adaptador `estado_pdf`, obtenida de un estado de cuenta real de 2026. Todos los ejemplos de este documento son ficticios.

## Archivo

- PDF con texto (no escaneado), tamaño carta, sin contraseña. El texto se extrae conservando la disposición en columnas.
- Un PDF por mes; se genera unos días después del cierre del mes.
- Puede traer más de un producto (cuenta de cheques e inversión). Solo interesa la sección **«Detalle de movimientos cuenta de cheques»**.

## Encabezado útil

| Dato | Dónde |
|---|---|
| Periodo | `PERIODO DEL 01-AGO-2026 AL 31-AGO-2026` |
| Cuenta y CLABE | `CUENTA SANTANDER PYME 00-00000000-0   CUENTA CLABE: 014…` |
| Saldo inicial, depósitos, retiros, saldo final | Bloque «Cuenta de cheques» de la primera página |
| Saldo inicial de la sección | `SALDO FINAL DEL PERIODO ANTERIOR: $9,999.99` (la primera aparición es la de cheques; hay otra por cada producto) |

## Renglón de movimiento

```
  FECHA      FOLIO      DESCRIPCION                              DEPOSITO      RETIRO       SALDO
03-AGO-2026 1234567 ABONO TRANSFERENCIA SPEI HORA 10:53:26        1,000.00                11,675.49
```

- Fecha `DD-MMM-AAAA` con el mes en español abreviado y en mayúsculas.
- Folio numérico.
- Un solo importe y el saldo resultante. La posición de las columnas cambia de una página a otra, así que **no se debe decidir depósito o retiro por la columna**: se decide comparando con el saldo anterior (`saldo anterior + importe = saldo` es depósito; `saldo anterior − importe = saldo` es retiro).
- Las líneas siguientes con sangría y sin importes son la continuación del mismo movimiento.
- Entre movimientos se intercalan encabezados y pies de página que hay que ignorar.

## Comprobación

El lector debe cuadrar al centavo: saldo inicial + depósitos − retiros = saldo final, y las sumas de depósitos y de retiros deben coincidir con las del encabezado. Si no cuadra, la importación se rechaza completa.

## Tipos de abono y qué datos traen

| Descripción | Qué es | Datos para identificar al pagador |
|---|---|---|
| `ABONO TRANSFERENCIA SPEI HORA hh:mm:ss` | Transferencia desde otro banco | Completos (ver abajo) |
| `ABONO TRANSFERENCIA ENLACE <texto>` | Transferencia desde otra cuenta del mismo banco | **Solo el texto libre** que escribió quien paga, en la misma línea y a veces partido en la siguiente. Sin nombre, sin cuenta, sin referencia |
| `ABONO TRANSF RAPIDA SANTANDER <texto>` | Igual, desde la app | Solo el texto libre, que puede venir recortado |
| `DEPOSITO EN EFECTIVO` y `DEPOSITO EN EFECTIVO ATM` | Efectivo en ventanilla o cajero | **Ninguno** |
| `ABONO POR DEVOLUCIONES SPEI` | Devolución de un pago enviado | No es un cobro |
| `DEVOLUCION CONSUMO …` | Devolución de una compra con tarjeta | No es un cobro |

### SPEI recibido

```
03-AGO-2026 1234567 ABONO TRANSFERENCIA SPEI HORA 10:53:26        1,000.00                11,675.49
                    RECIBIDO DE BANCO EJEMPLO
                    DE LA CUENTA 000000000000000000
                    DEL CLIENTE NOMBRE APELLIDO APELLIDO
                    CLAVE DE RASTREO ABC1234567890
                    REF 4829173
                    CONCEPTO colegiatura agosto
                    RFC XAXX010101000
```

- `REF`: la referencia numérica, hasta 7 dígitos. Los ceros a la izquierda se conservan en unos casos y en otros no, por lo que una matrícula nunca debe empezar en cero.
- `CONCEPTO`: texto libre, hasta 40 caracteres.
- `DE LA CUENTA`: CLABE de quien paga. Es estable de un mes a otro, así que sirve para aprender a quién pertenece cada pagador.
- `DEL CLIENTE`: el nombre viene en formatos distintos según el banco de origen (`NOMBRE APELLIDO`, `APELLIDO APELLIDO NOMBRE`, `NOMBRE,APELLIDO/APELLIDO`).
- `CLAVE DE RASTREO`: de 10 a 30 caracteres; única por transferencia. Con el folio forma la huella contra duplicados.

## Consecuencias para identificar pagos

1. Quien paga por SPEI desde otro banco puede poner la matrícula en la referencia numérica, en el concepto o en ambos.
2. Quien paga desde el mismo banco **solo** puede ponerla en el concepto. La ficha de pago debe pedir siempre «en referencia y en concepto».
3. Un depósito en efectivo no se puede identificar por el estado de cuenta. O es un traslado de la propia caja (se empareja por importe y fecha con el traslado registrado) o va a la cola «por identificar».
4. Sin matrícula, la mejor pista es la CLABE del pagador: tras identificar un pago a mano, los siguientes de esa cuenta se sugieren solos.
5. Los cargos (retiros) se importan para cuadrar el saldo, pero no participan en la cobranza.
