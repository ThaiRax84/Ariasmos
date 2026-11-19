from configuracion.models import con_vocabulario

PASOS = {
    "cobrar": (
        ("Elige a la persona.", "Toca su nombre en la lista o escríbelo arriba."),
        ("Marca lo que va a pagar", "y toca los billetes y monedas que te dio."),
        ("Entrega el cambio", "que te dice el programa y confirma. Sale el recibo."),
    ),
    "inicio": (
        ("Mira cómo va el día.", "Las cifras y la gráfica se ponen al día solas."),
        ("Atiende lo pendiente.", "Las solicitudes se aprueban o rechazan aquí mismo."),
        ("Cobra a quien va atrasado", "con el botón «Cobrar» de su renglón."),
    ),
    "caja": (
        ("Abre tu turno", "contando los billetes y monedas con que empiezas."),
        ("Cobra y registra lo que sale", "siempre diciendo qué piezas entran o salen."),
        ("Cierra tu turno", "contando lo que hay. El programa te dice al final si cuadra."),
    ),
    "banco": (
        ("Descarga el estado de cuenta", "desde la página de tu banco."),
        ("Súbelo aquí", "arrastrándolo o con «Elegir archivo»."),
        ("Revisa la lista y aplica.", "Los pagos seguros ya vienen marcados; tú decides."),
    ),
    "ficha": (
        ("Revisa lo que debe", "en «Estado de cuenta»."),
        ("Mira lo que ha pasado", "en «Historial», del más reciente al más viejo."),
        ("Corrige sus datos", "en «Datos». Lo que pide autorización se manda como solicitud."),
    ),
    "solicitudes": (
        ("Abre una solicitud", "para ver qué se pide y por qué."),
        ("Apruébala o recházala.", "Si la rechazas, escribe el motivo."),
        ("Quien la pidió se entera", "y todo queda anotado en la bitácora."),
    ),
    "configuracion": (
        ("Elige qué quieres cambiar", "de la lista."),
        ("Haz el cambio.", "Lo que tiene vista previa se ve al instante."),
        ("Guarda.", "Nada cambia hasta que lo guardas."),
    ),
}


def pasos(clave, voc=None):
    return [(con_vocabulario(titulo, voc), con_vocabulario(texto, voc)) for titulo, texto in PASOS.get(clave, ())]
