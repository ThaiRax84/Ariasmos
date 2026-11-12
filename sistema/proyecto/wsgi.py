import os
import sys
from pathlib import Path

_raiz = Path(__file__).resolve().parents[2]
for _ruta in (_raiz, _raiz / "sistema"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "proyecto.ajustes")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
