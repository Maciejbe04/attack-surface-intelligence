"""Settings for running the test suite without Docker.

    python manage.py test apps --settings=config.settings_test
"""

from .settings import *  # noqa: F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only, never in prod

# Throwaway test key, not used anywhere else.
APP_DATA_KEY = "test-only-app-data-key-0123456789abcdefghijklmnop"
CELERY_TASK_ALWAYS_EAGER = True
