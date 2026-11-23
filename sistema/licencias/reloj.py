import time

from django.utils import timezone


def ahora():
    return timezone.now()


def transcurrido():
    return time.monotonic()
