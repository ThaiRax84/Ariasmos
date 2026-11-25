# Guía de WhatsApp

Con esta fase, el programa de cada negocio puede mandar el recibo por WhatsApp con un botón. El programa no habla con WhatsApp: le pide a Ariasmos Central que lo mande. Por ahora Máximo conecta el número de cada negocio; el negocio solo escribe sus mensajes y marca quién aceptó recibirlos.

## Lo que hace Máximo, una vez, en Central

1. Corre `python manage.py inicializar_central` (la misma carpeta de siempre). Agrega a `configuracion.json` los datos nuevos: `url_publica`, `proveedor_mensajes` y `clave_secretos`. No toca nada más.
2. Abre `configuracion.json` y escribe en `url_publica` la dirección https con la que se llega a Central, sin diagonal al final. Para mandar de verdad, cambia `proveedor_mensajes` de `simulado` a `twilio`. Con `simulado` nada sale a WhatsApp: sirve para probar.
3. Reinicia Central.

## Lo que hace Máximo por cada negocio

1. En la consola de Twilio, deja listos la cuenta del negocio, su número de WhatsApp y su servicio de mensajes.
2. También en la consola de Twilio, en la dirección que recibe las respuestas de ese número, escribe `{url_publica}/v1/twilio/entrante/<id del negocio>` (el id lo da `python manage.py negocios`). Así Central se entera cuando alguien contesta BAJA.
3. En Central corre:

   ```
   TWILIO_TOKEN=... python manage.py whatsapp_conectar <id del negocio> --numero +52... --cuenta AC... --servicio MG...
   ```

   El token se lee de la variable `TWILIO_TOKEN`; si no existe, se pide por teclado sin mostrarse. No se acepta como argumento. Se guarda cifrado y nunca se muestra.
4. Para ver cómo va cada negocio: `python manage.py whatsapp_estado`. Para fijar el máximo de mensajes al mes que podrá elegir: `python manage.py whatsapp_tope <id> --maximo 500`. Para quitar la conexión: `python manage.py whatsapp_desconectar <id>`.

## Lo que hace el negocio

- **Escribir sus mensajes.** En «Más», «Mensajes» (solo con el permiso de administrar mensajes). Cada mensaje se escribe una vez; los datos de cada persona se ponen con los botones (nombre, concepto, importe, adeudo, fecha, días de atraso, folio…). El texto no puede empezar ni terminar con un dato, ni tener dos datos pegados. Al guardar, el mensaje se manda a revisión de Meta; suele tardar de minutos a un día. Mientras no esté «Listo para usar», no se manda.
- **Marcar el consentimiento.** En la ficha del contacto, junto al teléfono, está la casilla «Aceptó recibir mensajes por WhatsApp». Sin ella no se manda nada. El cambio queda en la bitácora.
- **Mandar un recibo.** En la pantalla del recibo aparece el botón verde «Mandar por WhatsApp», con el nombre de la persona y los últimos dígitos de su teléfono. Si todavía no aceptó, el botón dice «Pedir permiso para mandar por WhatsApp» y lleva a su ficha. Un doble clic manda un solo mensaje.
- **Países.** Cada negocio solo manda a los países que Máximo active (de fábrica, México: `52`). Para verlos o cambiarlos: `python manage.py whatsapp_paises <id> 52 1`; sin prefijos solo los muestra. Un número de otro país no se manda y el programa lo explica. Si alguien escribe ALTA a ese WhatsApp, vuelve a recibir mensajes.
- **El tope.** En el panel de mensajes se ve cuántos se han mandado este mes y el tope. El negocio puede bajarlo o subirlo hasta el máximo que fijó Máximo. Al llegar al tope ya no se manda nada hasta el mes siguiente.
- **Las bajas.** Si la persona contesta BAJA, STOP o ALTO, no se le manda nada más y el programa la marca. Si contesta ALTA, Central vuelve a permitirlo.

## Si un mensaje no llega

1. En el recibo se ve el estado y el motivo en palabras llanas. «Intentar otra vez» aparece solo si falló.
2. Revisa que el mensaje del recibo esté «Listo para usar» en el panel y que el contacto tenga teléfono y haya aceptado.
3. Si dice que WhatsApp no está disponible, el equipo no está activado en Central o falta su dirección: revisa la licencia.
4. Si dice que el negocio no está conectado o que se llegó al tope, pídelo a Máximo (`whatsapp_conectar` o `whatsapp_tope`).
5. Si nada de eso, corre `python manage.py whatsapp_estado` en Central y revisa que el proveedor sea `twilio` y que la consola de Twilio no muestre un error en ese mensaje.
