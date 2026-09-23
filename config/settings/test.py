"""Configuracion para ejecutar la suite de pruebas."""
from .base import *  # noqa: F401,F403

DEBUG = False
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}

# WhiteNoise no es necesario en pruebas (evita el aviso de staticfiles ausente).
MIDDLEWARE = [m for m in MIDDLEWARE  # noqa: F405
              if m != "whitenoise.middleware.WhiteNoiseMiddleware"]
