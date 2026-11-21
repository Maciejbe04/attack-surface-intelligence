import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def read_secret(name: str, default: str = "") -> str:
    path = Path("/run/secrets") / name
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    env_key = name.upper()
    return os.environ.get(env_key, default)


SECRET_KEY = read_secret("django_secret_key", "dev-only-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "apps.health",
    "apps.scans",
    "apps.accounts",
    "apps.mfa",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

POSTGRES_DB = os.environ.get("POSTGRES_DB", "surfacex")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "surfacex")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_PASSWORD = read_secret("postgres_password", os.environ.get("POSTGRES_PASSWORD", ""))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": POSTGRES_DB,
        "USER": POSTGRES_USER,
        "PASSWORD": POSTGRES_PASSWORD,
        "HOST": POSTGRES_HOST,
        "PORT": POSTGRES_PORT,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Password checks go through a backend that refuses to run while the caller is
# locked out after repeated failures (apps/accounts/throttle.py).
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.ThrottledModelBackend"]
# nginx in front of the API overwrites X-Real-IP with the real client address.
TRUST_X_REAL_IP = os.environ.get("TRUST_X_REAL_IP", "1") == "1"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:8080,http://127.0.0.1:8080,http://localhost:18080,http://127.0.0.1:18080",
    ).split(",")
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CSRF_TRUSTED_ORIGINS",
        "http://localhost:8080,http://127.0.0.1:8080,http://localhost:18080,http://127.0.0.1:18080",
    ).split(",")
    if origin.strip()
]

SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "0") == "1"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://redis:6379/2"),
    }
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True
CELERY_TASK_SOFT_TIME_LIMIT = 270
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_DEFAULT_QUEUE = "scan"
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 360}
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_RESULT_EXPIRES = 900
CELERY_TASK_ROUTES = {
    "scans.execute_batch": {"queue": "scan"},
    "scans.reconcile_batches": {"queue": "scan"},
    "scans.dispatch_schedules": {"queue": "scan"},
}
SCAN_RECONCILE_INTERVAL_SECONDS = max(
    15,
    int(os.environ.get("SCAN_RECONCILE_INTERVAL_SECONDS", "60")),
)
SCAN_RECONCILE_STALE_SECONDS = max(
    360,
    int(os.environ.get("SCAN_RECONCILE_STALE_SECONDS", "600")),
)
SCAN_RECONCILE_BATCH_LIMIT = max(
    1,
    min(500, int(os.environ.get("SCAN_RECONCILE_BATCH_LIMIT", "100"))),
)
CELERY_BEAT_SCHEDULE = {
    "reconcile-stale-scan-batches": {
        "task": "scans.reconcile_batches",
        "schedule": float(SCAN_RECONCILE_INTERVAL_SECONDS),
        "options": {"queue": "scan"},
    },
    "dispatch-group-schedules": {
        "task": "scans.dispatch_schedules",
        "schedule": 60.0,
        # A missed tick is harmless: the next one dispatches everything still due.
        "options": {"queue": "scan", "expires": 55},
    },
}

# Global scan safety limits (apps.scans.runner.ScanLimits). Totals are split
# evenly between all worker processes that can scan at once (SCAN_WORKER_SLOTS),
# so parallel batches together never exceed them, whatever the UI filters say.
SCAN_MAX_RATE_TOTAL = int(os.environ.get("SCAN_MAX_RATE_TOTAL", "300"))  # nmap packets/s
SCAN_HTTP_RATE_TOTAL = int(os.environ.get("SCAN_HTTP_RATE_TOTAL", "100"))  # httpx requests/s
SCAN_WORKER_SLOTS = int(os.environ.get("SCAN_WORKER_SLOTS", os.environ.get("WORKER_CONCURRENCY", "2")))
# All commands of one batch must finish inside this budget; it stays 30 s below
# the Celery soft limit so the worker can still report the result.
SCAN_BATCH_TIME_BUDGET = CELERY_TASK_SOFT_TIME_LIMIT - 30

APP_DATA_KEY = read_secret("app_data_key")
# Old keys (comma separated) kept only to decrypt data during key rotation.
APP_DATA_KEY_PREVIOUS = read_secret("app_data_key_previous")
SESSION_HMAC = read_secret("session_hmac")
WORKER_TOKEN = read_secret("worker_token")
API_INTERNAL_URL = os.environ.get("API_INTERNAL_URL", "http://api:8000")
ROLE = os.environ.get("ROLE", "api")

APP_NAME = os.environ.get("APP_NAME", "SurfaceX")
APP_VERSION = os.environ.get("APP_VERSION", "0.1.0")
WEB_VERSION = os.environ.get("WEB_VERSION", APP_VERSION)
HTTPX_VERSION = os.environ.get("HTTPX_VERSION", "v1.6.9")
DEFECTDOJO_VERSION = os.environ.get("DEFECTDOJO_VERSION", "3.5.202")

DEFECTDOJO_URL = os.environ.get("DEFECTDOJO_URL", "").strip()
DEFECTDOJO_USERNAME = os.environ.get("DEFECTDOJO_USERNAME", "admin")
DEFECTDOJO_PASSWORD = read_secret(
    "defectdojo_admin_password",
    os.environ.get("DEFECTDOJO_PASSWORD", ""),
)
DEFECTDOJO_API_TOKEN = read_secret(
    "defectdojo_api_token",
    os.environ.get("DEFECTDOJO_API_TOKEN", ""),
)
DEFECTDOJO_PRODUCT_TYPE = os.environ.get(
    "DEFECTDOJO_PRODUCT_TYPE",
    "SurfaceX",
)
DEFECTDOJO_PRODUCT_NAME = os.environ.get(
    "DEFECTDOJO_PRODUCT_NAME",
    "Attack Surface",
)
DEFECTDOJO_ENGAGEMENT_NAME = os.environ.get(
    "DEFECTDOJO_ENGAGEMENT_NAME",
    "SurfaceX Discovery",
)
DEFECTDOJO_TEST_TITLE = os.environ.get(
    "DEFECTDOJO_TEST_TITLE",
    "SurfaceX Discovery",
)
DEFECTDOJO_TIMEOUT_SECONDS = max(
    5,
    min(120, int(os.environ.get("DEFECTDOJO_TIMEOUT_SECONDS", "30"))),
)

# MFA backend (apps.mfa) stays dormant until MFA_ENABLED=1. See docs/mfa-backend.md.
MFA_ENABLED = os.environ.get("MFA_ENABLED", "0") == "1"
MFA_ISSUER = os.environ.get("MFA_ISSUER", "SurfaceX")
