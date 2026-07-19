"""Local development settings."""

from .base import *  # noqa: F403

DEBUG = True

INTERNAL_IPS = ["127.0.0.1"]

# In dev, serve static files directly via the finders — no manifest, no
# collectstatic required (the manifest storage from base.py needs both).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# WhiteNoise otherwise warns on every request/test run that STATIC_ROOT does not
# exist. In dev the finders serve static files, so there is nothing to collect.
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True

# Relaxed cookies over plain HTTP in dev.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Show sent mail in the console.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
