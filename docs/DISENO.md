# Ariasmos — diseño de la interfaz (fase 5b)

Versión 1 · 13/11/2026. Este documento manda sobre el aspecto del programa. Las pantallas de referencia están en `docs/diseno/referencia/` (HTML estático que se abre directo en el navegador). Los datos de esas pantallas son de ejemplo.

## 1. Principios

1. **Cálida y directa.** Fondo claro cálido, tarjetas blancas de esquinas redondeadas, un solo color fuerte para la acción principal de cada pantalla.
2. **Una acción principal por pantalla**, grande y con verbo claro («Cobrar», «Confirmar y dar recibo», «Cerrar turno»). Las demás son secundarias.
3. **Dos marcas conviven.** Ariasmos (medallón del grifo y nombre en Cinzel) siempre a la izquierda de la barra; a su lado, el logo y el nombre del negocio. Los colores de la pantalla son los del negocio si los configuró; si no, los de Ariasmos.
4. **Nada de lo que protege el dinero se suaviza por estética:** el arqueo sigue ciego, los importes no se animan, los avisos de control se ven.
5. **Sin recursos de internet.** Fuentes, imágenes y estilos se sirven desde el propio programa. La política de contenido sigue siendo `style-src 'self'` y `script-src 'self'`: **ningún estilo ni script en línea**.

## 2. Marca Ariasmos

- **Splash:** escena de vasija griega (`estaticos/marca/escena-vasija.jpg`) sobre negro `#14100D`, grecas terracota arriba y abajo, «ARIASMOS» en Cinzel 700 del ancho de la escena y «Iniciando el sistema…». Es una **ventana de 720 × 450** centrada sobre un fondo oscuro, más chica que la ventana del programa. Aparece al abrir el programa (una vez por sesión del navegador, antes del inicio de sesión) y se desvanece hacia el inicio de sesión. Referencia: `referencia/splash.html` y `referencia/prototipo-transiciones.html`.
- **Ícono del menú:** medallón negro con el grifo (`grifo-medallon.jpg`), circular, con aro terracota de 2 px, 46 px.
- **Logo del programa** (ícono del instalador, del acceso directo y favicon): medallón negro con el jinete (`jinete-medallon.png`, `favicon.png`, `instalacion/ariasmos.ico`).
- **Nombre:** «ARIASMOS» en Cinzel 700 con espaciado amplio. En el pie del recibo, «Hecho con ARIASMOS» con el nombre en Metamorphous.

## 3. Colores

Todos los colores son variables CSS. Hay dos juegos; la estructura es la misma.

| Variable | Ariasmos (por omisión) | Ejemplo de negocio |
|---|---|---|
| `--fondo` | `#F6EDE3` | `#FFF8F1` |
| `--tinta` (texto) | `#1F1813` | `#1F1A4E` |
| `--suave` (texto secundario) | `#5C5047` | `#4E4A72` |
| `--primario` (acción principal, menú activo) | `#9E431C` | `#1F1A4E` |
| `--acento` (subrayados, barras, detalles) | `#C4662E` | `#F58634` |
| `--franja` (franja superior de 6 px) | `#14100D` | `#F58634` |
| `--borde` | `#E2D6C6` | `#F2DCC6` |
| `--tinte` (fondos suaves, selección) | `#F6E3D6` | `#FFE9D6` |
| `--aviso-fondo` / `--aviso-texto` | `#FCEBCF` / `#7A3E00` | `#FFE2C4` / `#8A3D00` |
| `--bien-fondo` / `--bien-texto` | `#E1EEDD` / `#2F5A2A` | `#DDF3E4` / `#1B5E3A` |
| Tarjetas | `#FFFFFF` | `#FFFFFF` |

**Marca del negocio (configurable por Dirección):** logo y dos colores, principal y acento.

- Los colores se guardan solo como `#RRGGBB` validado con expresión exacta; cualquier otra cosa se rechaza. Nunca se escriben en una hoja de estilos sin validar.
- De esos dos colores se derivan `--primario`, `--acento`, `--franja`, `--tinte` (acento al 15 % sobre blanco), `--borde` y `--fondo` (acento al 6 % sobre blanco). `--tinta` es el principal si su contraste con blanco es de 7:1 o más; si no, la tinta de Ariasmos.
- Si el texto blanco sobre el color principal no alcanza contraste 4.5:1, los botones principales usan la tinta como fondo. El cálculo de contraste va en un módulo propio con pruebas.
- La hoja con las variables del negocio se sirve como archivo CSS desde una vista (`/marca.css`), con caché que se invalida al cambiar la marca. No hay estilos en línea.
- **Logo:** solo JPEG o PNG, hasta 1 MB; pasa por el mismo módulo seguro de imágenes de los comprobantes (tipo por contenido, se reconstruye solo con píxeles); se guarda fuera de lo servido directamente y se entrega por una vista con `nosniff`. Sin logo, se muestra solo el nombre del negocio.
- Las plantillas de negocio no llevan logo ni colores.

## 4. Letra

- **Nunito** (400, 600, 700, 800) para todo el programa. **Cinzel** (500, 700) solo para la marca Ariasmos. **Metamorphous** solo para «ARIASMOS» en el pie del recibo.
- Archivos en `estaticos/fuentes/` con su licencia; se declaran con `@font-face` y `font-display: swap`.
- Tamaños: título de pantalla 34 px/800; título de tarjeta 19 px/800; texto 15–16 px; ayuda y etiquetas 13 px/700; importes grandes 28–40 px/800. Los importes llevan siempre el símbolo y la moneda.
- Ninguna otra familia. Si una fuente no carga, la de reserva es `system-ui, sans-serif`.

## 5. Estructura

- **Franja** de 6 px del color `--franja` arriba de todo.
- **Barra superior** blanca, fija: marca Ariasmos · separador · logo y nombre del negocio · menú · a la derecha, el contexto de la sesión (rol, caja y turno, o el nombre) con «Contraseña» y «Salir».
- **Menú:** pastillas; la activa con fondo `--primario` y texto blanco. A lo más siete entradas visibles según permisos, en este orden de prioridad: Inicio, Cobrar, Padrón (con el vocabulario del negocio), Inventario (si está encendido), Mi caja, Banco, Efectivo, Solicitudes, Cortes. Lo demás (Familias, Conceptos, Delegaciones, Equipos, Usuarios, Roles, Políticas, Configuración, Respaldos, Auditoría) va en un menú **«Más»** desplegable, accesible con teclado. Ninguna entrada actual desaparece: solo se reordena.
- **Contenido:** ancho máximo de 1120 px centrado, relleno de 32 px, separación de 24 px entre bloques.
- **Encabezado de pantalla:** antetítulo de 13 px (dónde estoy), título de 34 px y, a la derecha, la cifra o la acción más importante.
- Diseñado para computadora de escritorio (1280 px o más). En pantallas angostas las columnas se apilan; no hay versión de teléfono.

## 6. Componentes

- **Tarjeta:** fondo blanco, borde 1 px `--borde`, radio 16 px, relleno 24 px.
- **Botón principal:** pastilla (radio 999 px), fondo `--primario`, texto blanco 16 px/800, alto mínimo 48 px (54 px el de la acción principal de la pantalla). **Secundario:** fondo blanco, borde 2 px `--borde`. Estados: al pasar el cursor, al enfocar (anillo de 3 px `--acento` separado 2 px), presionado y deshabilitado.
- **Campo:** etiqueta de 13 px/700 arriba, caja con borde 2 px `--borde` y radio 12 px, texto 16 px; al enfocar, borde `--tinta` y halo suave del acento. La ayuda va debajo en 13 px. Los errores se muestran junto al campo y arriba del formulario, con texto, no solo con color.
- **Importe:** símbolo a la izquierda y moneda a la derecha dentro de la caja; el importe principal de una pantalla va en 28 px/800 con borde `--tinta`. Se conserva la captura guiada existente (solo caracteres aceptados).
- **Etiqueta de estado:** pastilla de 13 px/700 en tres tonos: aviso, calma (neutra) y bien. Siempre con texto.
- **Tabla:** encabezados de 13 px/700 `--suave`, renglones con línea inferior `--borde`, importes alineados a la derecha, el saldo en 800.
- **Opción (radio o casilla en tarjeta):** borde 2 px; seleccionada con borde `--primario` y fondo `--tinte`.
- **Pestañas:** texto de 15 px con subrayado de 3 px `--acento` en la activa.
- **Aviso de pantalla:** bloque con fondo `--aviso-fondo`, título en 800 y la acción a la derecha.
- **Cifra de tablero:** tarjeta pequeña con etiqueta, número grande y una línea de detalle.
- **Diálogo de confirmación** propio (no los del navegador) para acciones que mueven dinero o no se deshacen, y **aviso breve** abajo al terminar.
- **Selector de piezas** (billetes y monedas): botones con la denominación y el contador.
- Los mensajes de Django (`messages`) se muestran como avisos con estos tonos.

## 7. Movimiento

- Entre pantallas: fundido con deslizamiento leve del contenido, unos 200 ms, con las transiciones de vista del navegador entre documentos (`@view-transition { navigation: auto; }`) y, donde no existan, sin animación. La barra superior no se mueve; la pastilla activa del menú se desliza.
- Dentro de la pantalla: cambios de estado de botones, campos y pestañas en unos 150 ms; diálogos y avisos entran con fundido.
- El splash se desvanece hacia el inicio de sesión.
- **Nunca se animan importes ni se retrasa una confirmación de cobro.** Con «reducir movimiento» del sistema operativo no hay animaciones.
- Solo CSS y funciones del navegador; ninguna librería.

## 8. Pantallas de referencia

En `docs/diseno/referencia/`:

- `ariasmos/` — todas las pantallas con los colores de Ariasmos: inicio de recepción, cobrar, cobrar con billetes, recibo, corte (conteo, no coincide, resultado), retiro de caja, inventario (vender, conteo), padrón, ficha, solicitudes, inicio de coordinación, inicio de dirección.
- `negocio-ejemplo/` — las mismas ideas con una marca de negocio de ejemplo (inicio, cobrar, recibo, padrón).
- `instalacion/` — los ocho pasos del asistente. El asistente usa siempre los colores de Ariasmos, porque todavía no hay negocio.
- `splash.html` y `prototipo-transiciones.html` — splash y prototipo navegable con las transiciones.

Las referencias usan estilos en línea porque son maquetas; el programa usa clases en `estaticos/css/`. Las pantallas que no tienen referencia (configuración, banco, cortes, usuarios, auditoría y demás) se arman con los mismos componentes y la misma estructura.

Reglas que las referencias no deben contradecir:

- **Recibo:** lleva el logo y el nombre del negocio; Ariasmos solo en la línea del pie. QR y código de verificación juntos. La versión impresa y el PDF siguen el mismo diseño.
- **Corte:** el conteo no muestra lo esperado; «no coincide» no dice cuánto ni hacia dónde; el resultado aparece hasta que el turno está cerrado.
- **Retiro de caja:** no muestra el efectivo que hay en la caja.
- **Cobro con billetes:** el recuadro «Entrega exactamente estas piezas» y el enlace para capturar otras.
- **Inventario, venta:** muestra el número de existencias de cada artículo; cuando es cero no muestra nada; marca «pocas» cuando están en 20 % o menos (ver arquitectura §16.6).

## 9. Accesibilidad

- Todo se puede usar con teclado; el foco siempre se ve.
- Contraste de texto de 4.5:1 o más; objetivos de clic de 44 px o más.
- Cada campo tiene su etiqueta; los estados nunca dependen solo del color; las imágenes con significado llevan texto alternativo.
- El orden de lectura sigue el orden visual.
