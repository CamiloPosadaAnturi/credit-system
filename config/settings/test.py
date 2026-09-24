"""Settings used by the test suite."""
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
MIDDLEWARE = [m for m in MIDDLEWARE  # noqa: F405
              if m != "whitenoise.middleware.WhiteNoiseMiddleware"]

# Assertions in the suite are written against the English source strings.
LANGUAGE_CODE = "en"
USE_I18N = False
