import os
import sys
from pathlib import Path


def main():
    raiz = Path(__file__).resolve().parent.parent
    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "proyecto.ajustes")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
